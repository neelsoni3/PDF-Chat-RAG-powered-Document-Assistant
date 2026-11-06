# 📄 PDF Chat — RAG-powered Document Assistant

A lightweight, self-hostable chatbot that lets you **upload PDF documents and ask questions about them**. It uses **retrieval-augmented generation (RAG)** to ground every answer in your own files, streams responses token-by-token from **Groq**, and stores embeddings locally in **ChromaDB**.

Built with Flask, LangChain text-splitters, Sentence-Transformers, and a clean vanilla-JS frontend — no build step, no framework, just `python app.py`.

---

## ✨ Features

- **📥 Upload multiple PDFs** — drag-and-drop or click to browse
- **🔍 Semantic retrieval** — top-K relevant chunks fetched per question using `all-MiniLM-L6-v2`
- **⚡ Streaming answers** — tokens appear as they are generated, no waiting for the full response
- **🔁 Automatic model fallback** — if the primary Groq model is retired or unavailable, the app tries the next candidate automatically
- **💬 Persistent chat UI** — clean two-pane layout with a collapsible sidebar
- **📱 Responsive design** — sidebar slides in as an overlay on mobile
- **🧹 Clear all** — one click wipes the vector store and chat history
- **🔒 Fully local embeddings** — your documents never leave your machine for vectorization
- **🩺 Health endpoint** — inspect which model is active and how many chunks are indexed

---


## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.10+, Flask 3, Flask-CORS |
| **LLM** | [Groq](https://console.groq.com/) (streaming chat completions) |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` (384-dim, runs on CPU) |
| **Vector Store** | [ChromaDB](https://www.trychroma.com/) (persistent, local) |
| **PDF Parsing** | `pypdf` |
| **Chunking** | `langchain-text-splitters` (`RecursiveCharacterTextSplitter`) |
| **Frontend** | Vanilla HTML / CSS / JS (no build step) |

---

## 📋 Prerequisites

- **Python 3.10+** (Python 3.12/3.14 also work)
- **pip**
- A **Groq API key** — get one free at [console.groq.com/keys](https://console.groq.com/keys)
- ~500 MB free disk space (for the embedding model + dependencies)

---

## 🚀 Installation

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/pdf-chat.git
cd pdf-chat

# 2. (Recommended) Create a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### `requirements.txt`

If you don't already have one, create it with:

```text
flask>=3.0.0
flask-cors>=4.0.0
python-dotenv>=1.0.0
groq>=0.11.0
langchain>=1.0.0
langchain-community>=0.4.0
langchain-text-splitters>=1.1.0
pypdf>=5.0.0
sentence-transformers>=3.2.0
chromadb>=0.5.0
numpy>=2.3.0
```

---

## ⚙️ Configuration

Create a `.env` file in the project root:

```env
# Required
GROQ_API_KEY=gsk_your_key_here

# Optional — override defaults
# GROQ_MODEL=openai/gpt-oss-120b
# CHROMA_PATH=./chroma_db
```

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | _(required)_ | Your Groq API key |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Primary chat model |
| `CHROMA_PATH` | `./chroma_db` | Where the vector DB is persisted |

> **Note on model names:** Groq retires models periodically. This app falls back to `qwen/qwen3.6-27b` automatically if the primary is unavailable. To see which models your key can access:
>
> ```bash
> python -c "from groq import Groq; import os; print([m.id for m in Groq(api_key=os.environ['GROQ_API_KEY']).models.list().data])"
> ```

---

## ▶️ Running

```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

On first run, the app will download `all-MiniLM-L6-v2` (~90 MB) from Hugging Face and cache it locally. Subsequent starts are instant.

---

## 🎯 Usage

1. **Upload** — click the upload zone in the sidebar (or drag PDFs onto the window). Each PDF is parsed, chunked, embedded, and stored in ChromaDB.
2. **Ask** — type a question in the composer. Press **Enter** to send or **Shift+Enter** for a new line.
3. **Read** — the assistant streams its answer token-by-token, grounded in the top-4 retrieved chunks from your documents.
4. **Clear** — click **Clear all** in the sidebar footer to wipe the vector store and start over.

---

## 🔌 API Reference

### `GET /`
Serves the chat UI (`templates/index.html`).

### `GET /api/health`
Returns runtime information.

```json
{
  "status": "ok",
  "model": "openai/gpt-oss-120b",
  "fallbacks": ["openai/gpt-oss-120b", "qwen/qwen3.6-27b"],
  "embedding_model": "all-MiniLM-L6-v2",
  "chunks_indexed": 42
}
```

### `POST /api/upload`
Upload one or more PDFs. Accepts `multipart/form-data` with one or more `file` fields.

```bash
curl -X POST http://127.0.0.1:5000/api/upload -F "file=@my-document.pdf"
```

**Response:**
```json
{
  "message": "Indexed 1 file(s).",
  "total_chunks": 42,
  "results": [
    { "file": "my-document.pdf", "chunks": 42, "chars": 31250 }
  ]
}
```

### `POST /api/upload?reset=true`
Wipes the entire collection. Used by the **Clear all** button.

```bash
curl -X POST "http://127.0.0.1:5000/api/upload?reset=true"
```

**Response:**
```json
{ "message": "Cleared all documents.", "total_chunks": 0 }
```

### `POST /api/ask`
Ask a question. Streams the answer back as `text/plain` chunks.

```bash
curl -N -X POST http://127.0.0.1:5000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main conclusion of the paper?"}'
```

**Response:** streamed plain text. Response header `X-Sources` lists the PDFs that were retrieved (comma-separated).

---

## 📁 Project Structure

```
pdf-chat/
├── app.py                  # Flask app — upload, retrieval, streaming
├── requirements.txt
├── .env                    # (create this — not committed)
├── .gitignore
├── README.md
├── templates/
│   └── index.html          # Chat UI
├── static/
│   ├── style.css           # Sidebar + chat styling
│   └── app.js              # Frontend logic (upload, streaming, sidebar)
└── chroma_db/              # (auto-created — persisted vector store)
```

Suggested `.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc
.env
chroma_db/
*.pdf
.DS_Store
```

---

## 🧠 How It Works

```
┌─────────┐   upload    ┌──────────────┐   embed   ┌──────────┐
│ Browser │ ──────────▶ │   /api/upload│ ────────▶ │ ChromaDB │
└─────────┘             └──────────────┘           └──────────┘
     │                                                    ▲
     │  ask                                       query (top-K)
     ▼                                                    │
┌─────────┐  stream      ┌──────────────┐   context  ┌───┴──────┐
│ Browser │ ◀─────────── │   /api/ask   │ ◀───────── │ Retrieve │
└─────────┘              └──────┬───────┘            └──────────┘
                                │ prompt
                                ▼
                        ┌──────────────┐
                        │  Groq (LLM)  │
                        └──────────────┘
```

1. **Ingest** — `PdfReader` extracts text page-by-page. `RecursiveCharacterTextSplitter` cuts it into ~900-character chunks with 150-character overlap. Each chunk is embedded by `all-MiniLM-L6-v2` and stored in ChromaDB with `{source, chunk}` metadata.
2. **Retrieve** — the user's question is embedded with the same model, and Chroma returns the top-4 nearest chunks (cosine distance).
3. **Generate** — retrieved chunks + question are formatted into a prompt with a system message that constrains the model to answer **only** from the context. The response streams from Groq directly to the browser.

---

## 🩺 Troubleshooting

| Symptom | Fix |
|---------|-----|
| `404 model_not_found` | The model was retired. Update `GROQ_MODEL` in `.env` or in `PRIMARY_MODEL`/`FALLBACK_MODELS` in `app.py`. Run `curl http://127.0.0.1:5000/api/health` to see the active model. |
| `RuntimeError: GROQ_API_KEY is not set` | Create `.env` with `GROQ_API_KEY=gsk_...` in the project root. |
| `No extractable text (scanned PDF?)` | The PDF is scanned images. OCR is not built in — run it through [ocrmypdf](https://ocrmypdf.readthedocs.io/) first. |
| HF model download is slow | Set `HF_TOKEN` in `.env` to raise rate limits. The model is cached after the first run in `~/.cache/huggingface/`. |
| Answers ignore the documents | Lower `temperature` or increase `TOP_K` in `app.py`. Also verify `/api/health` shows `chunks_indexed > 0`. |
| `Debugging middleware caught exception in streamed response` | You're on an older version where the Groq call happened after headers were sent. This version fixes it — pull the latest `app.py`. |
| Chroma DB corrupted | Delete `chroma_db/` and re-upload your PDFs. |

---

## 🧩 Configuration Reference

Tune these constants in `app.py`:

| Constant | Default | Effect |
|----------|---------|--------|
| `PRIMARY_MODEL` | `openai/gpt-oss-120b` | Chat model |
| `FALLBACK_MODELS` | `[...]` | Ordered fallbacks on 404 |
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | Swappable embedding model |
| `CHUNK_SIZE` | `900` | Larger = more context per chunk, fewer chunks |
| `CHUNK_OVERLAP` | `150` | Larger = better continuity across chunk boundaries |
| `TOP_K` | `4` | Chunks retrieved per question |

---

## 🤝 Contributing

Contributions are welcome. To contribute:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m "Add my feature"`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

Please keep PRs focused and include a short description of the change.

---

## 📜 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.

---

## 🙏 Acknowledgements

- [Groq](https://groq.com/) — blazing-fast LLM inference
- [Chroma](https://www.trychroma.com/) — embedded vector database
- [Sentence-Transformers](https://www.sbert.net/) — `all-MiniLM-L6-v2`
- [LangChain](https://www.langchain.com/) — text splitters
- [pypdf](https://pypdf.readthedocs.io/) — PDF text extraction
- [Flask](https://flask.palletsprojects.com/) — the whole backend

---

## ⚠️ Disclaimer

This project is for **educational and personal use**. It is **not** production-hardened — the Flask dev server is used directly, there is no authentication, and CORS is wide open. If you deploy it publicly, put it behind a reverse proxy with auth and switch to a WSGI server such as **gunicorn** or **waitress**. Do not upload confidential documents to a public instance.

---

## 👤 Author

**Neel Soni**


If this project helped you, consider giving it a ⭐!
