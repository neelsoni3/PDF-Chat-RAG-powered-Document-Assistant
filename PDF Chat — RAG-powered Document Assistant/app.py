"""
app.py — PDF chatbot with Groq streaming + ChromaDB retrieval.

Features:
  - PDF upload, extraction, chunking, embedding (all-MiniLM-L6-v2) → ChromaDB
  - Semantic retrieval (top-K chunks) for each question
  - Streaming answers from Groq with automatic model fallback
  - Safe streaming: model errors are caught BEFORE headers are sent
  - /api/upload?reset=true clears the vector store (used by the Clear all button)
"""

import os
import uuid
import traceback

from dotenv import load_dotenv
from flask import Flask, request, Response, jsonify, render_template, send_from_directory
from flask_cors import CORS
from groq import Groq
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from chromadb.utils import embedding_functions

load_dotenv()

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is not set. Add it to your .env file:\n  GROQ_API_KEY=gsk_..."
    )

# Primary model, then fallbacks tried in order (only on model-not-found errors).
PRIMARY_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
]

EMBED_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
TOP_K = 4
CHROMA_PATH = os.getenv(
    "CHROMA_PATH", os.path.join(os.path.dirname(__file__), "chroma_db")
)
COLLECTION_NAME = "pdf_docs"

app = Flask(__name__)
CORS(app)

groq_client = Groq(api_key=GROQ_API_KEY)

# --------------------------------------------------------------------------- #
# Vector store
# --------------------------------------------------------------------------- #
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=EMBED_MODEL
)
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)


def _get_collection():
    """Create/open the collection, tolerating chromadb API differences."""
    try:
        return chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_fn,
            configuration={"hnsw": {"space": "cosine"}},
        )
    except TypeError:
        # Older chromadb (<1.0) uses metadata instead of configuration
        return chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )


collection = _get_collection()

# --------------------------------------------------------------------------- #
# Groq streaming with model fallback
# --------------------------------------------------------------------------- #
def _is_model_not_found(err: Exception) -> bool:
    """True if the error means 'this model doesn't exist / was retired'."""
    status = getattr(err, "status_code", None)
    if status == 404:
        return True
    text = str(err).lower()
    markers = (
        "model_not_found",
        "does not exist",
        "decommissioned",
        "not have access",
    )
    return any(m in text for m in markers)


def groq_stream(messages, model: str | None = None):
    """
    Yield text tokens from Groq.

    The create() call is made *before* the first yield, so a bad model name is
    detected while we can still switch models. Once tokens have started flowing
    we never retry (that would duplicate output).
    """
    candidates = []
    for m in [model or PRIMARY_MODEL] + FALLBACK_MODELS:
        if m and m not in candidates:
            candidates.append(m)

    last_err = None
    for candidate in candidates:
        started = False
        try:
            stream = groq_client.chat.completions.create(
                model=candidate,
                messages=messages,
                temperature=0.2,
                max_tokens=2048,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                token = getattr(delta, "content", None)
                if token:
                    started = True
                    yield token
            return  # success
        except Exception as err:  # noqa: BLE001
            last_err = err
            if started:
                # We already emitted text; retrying would duplicate it.
                raise
            if _is_model_not_found(err):
                app.logger.warning(
                    "Model %s unavailable (%s); trying next fallback.",
                    candidate,
                    err,
                )
                continue
            raise

    raise last_err if last_err else RuntimeError("No Groq model available")


# --------------------------------------------------------------------------- #
# Retrieval helpers
# --------------------------------------------------------------------------- #
splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def extract_pdf_text(file_obj) -> str:
    reader = PdfReader(file_obj)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        if text.strip():
            pages.append(f"[page {i}]\n{text}")
    return "\n\n".join(pages)


def index_pdf(filename: str, text: str) -> int:
    """Split, embed and store. Returns number of chunks added."""
    chunks = [c for c in splitter.split_text(text) if c.strip()]
    if not chunks:
        return 0
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [{"source": filename, "chunk": i} for i in range(len(chunks))]
    collection.add(documents=chunks, ids=ids, metadatas=metadatas)
    return len(chunks)


def retrieve(question: str, k: int = TOP_K):
    try:
        total = collection.count()
    except Exception:  # noqa: BLE001
        total = 0
    if not total:
        return "", []

    try:
        res = collection.query(query_texts=[question], n_results=min(k, total))
    except Exception:  # noqa: BLE001
        app.logger.exception("Retrieval failed")
        return "", []

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    sources, seen = [], set()
    for meta in metas:
        src = (meta or {}).get("source")
        if src and src not in seen:
            seen.add(src)
            sources.append(src)
    return "\n\n---\n\n".join(docs), sources


def build_messages(context: str, question: str):
    system = (
        "You are a helpful assistant that answers questions about the user's "
        "uploaded PDF documents. Use ONLY the provided context. If the answer "
        "is not in the context, say you don't know and suggest what to check. "
        "Be concise and cite page markers like [page 3] when useful."
    )
    if context:
        user = f"Context:\n{context}\n\nQuestion: {question}"
    else:
        user = (
            "No document context is available (nothing uploaded yet, or no "
            f"relevant passages found). Question: {question}"
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    if os.path.exists(os.path.join(app.root_path, "templates", "index.html")):
        return render_template("index.html")
    static_index = os.path.join(app.static_folder or "", "index.html")
    if os.path.exists(static_index):
        return send_from_directory(app.static_folder, "index.html")
    return jsonify({"status": "ok", "message": "PDF chatbot API is running."})


@app.route("/api/health")
def health():
    try:
        count = collection.count()
    except Exception:  # noqa: BLE001
        count = -1
    return jsonify(
        {
            "status": "ok",
            "model": PRIMARY_MODEL,
            "fallbacks": FALLBACK_MODELS,
            "embedding_model": EMBED_MODEL,
            "chunks_indexed": count,
        }
    )


@app.route("/api/upload", methods=["POST"])
def upload():
    """
    Upload one or more PDFs. Passing ?reset=true (or form field reset=true)
    wipes the collection first — used by the "Clear all" button.
    """
    reset = (
        request.args.get("reset") == "true"
        or request.form.get("reset") == "true"
    )

    if reset:
        try:
            chroma_client.delete_collection(COLLECTION_NAME)
        except Exception:  # noqa: BLE001
            pass
        global collection
        collection = _get_collection()

    files = request.files.getlist("file") or request.files.getlist("files")
    files = [f for f in files if f and f.filename]

    if not files:
        if reset:
            return jsonify(
                {"message": "Cleared all documents.", "total_chunks": 0}
            )
        return jsonify({"error": "No file uploaded (expected field 'file')."}), 400

    results = []
    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            results.append({"file": f.filename, "error": "Not a PDF"})
            continue
        try:
            text = extract_pdf_text(f)
            if not text.strip():
                results.append(
                    {
                        "file": f.filename,
                        "error": "No extractable text (scanned PDF?)",
                    }
                )
                continue
            n = index_pdf(f.filename, text)
            results.append(
                {"file": f.filename, "chunks": n, "chars": len(text)}
            )
        except Exception as exc:  # noqa: BLE001
            app.logger.exception("Failed to index %s", f.filename)
            results.append({"file": f.filename, "error": str(exc)})

    ok = [r for r in results if "chunks" in r]
    if not ok:
        return (
            jsonify(
                {"error": "No documents were indexed.", "results": results}
            ),
            400,
        )

    return jsonify(
        {
            "message": f"Indexed {len(ok)} file(s).",
            "total_chunks": collection.count(),
            "results": results,
        }
    )


@app.route("/api/ask", methods=["POST"])
def ask():
    data = request.get_json(silent=True) or {}
    question = (
        data.get("question")
        or data.get("message")
        or data.get("query")
        or ""
    ).strip()
    if not question:
        return jsonify({"error": "Field 'question' is required."}), 400

    context, sources = retrieve(question)
    messages = build_messages(context, question)

    def generate():
        try:
            for token in groq_stream(messages):
                yield token
        except Exception as exc:  # noqa: BLE001
            app.logger.error(
                "Streaming failed: %s\n%s", exc, traceback.format_exc()
            )
            yield (
                "\n\n[Error] The model request failed: "
                f"{type(exc).__name__}: {exc}"
            )

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
        "Content-Type": "text/plain; charset=utf-8",
    }
    if sources:
        headers["X-Sources"] = ", ".join(sources)

    return Response(generate(), headers=headers)


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    print(f"[startup] primary model : {PRIMARY_MODEL}")
    print(f"[startup] fallbacks     : {FALLBACK_MODELS}")
    print(f"[startup] chroma path   : {CHROMA_PATH}")
    # use_reloader=False stops the double model load you saw in your logs
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
        threaded=True,
        use_reloader=False,
    )