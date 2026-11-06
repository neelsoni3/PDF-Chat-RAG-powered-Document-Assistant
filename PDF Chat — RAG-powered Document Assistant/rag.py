import os
from typing import List, Tuple

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import chromadb
import numpy as np

# ---------- configuration ----------
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
TOP_K = 5
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "pdf_documents"

_embedder = SentenceTransformer(EMBEDDING_MODEL)


class PDFIndex:
    def __init__(self):
        # PersistentClient auto-loads existing data from disk on startup.
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.collection = self.client.get_or_create_collection(name=COLLECTION_NAME)

    # ---------- ingestion ----------
    def build(self, pdf_path: str):
        """Extract, chunk, embed and store a PDF. Replaces any existing data."""
        # Clear any previously indexed document so uploads don't accumulate.
        try:
            self.client.delete_collection(name=COLLECTION_NAME)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(name=COLLECTION_NAME)

        loader = PyPDFLoader(pdf_path)
        pages = loader.load()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        docs = splitter.split_documents(pages)

        if not docs:
            raise ValueError("No extractable text found in this PDF.")

        texts = [d.page_content for d in docs]
        metadatas = [d.metadata or {} for d in docs]
        ids = [f"id_{i}" for i in range(len(texts))]

        embeddings = _embedder.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        embeddings_list = [emb.tolist() for emb in np.array(embeddings, dtype="float32")]

        self.collection.add(
            embeddings=embeddings_list,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )

    # ---------- retrieval ----------
    def search(self, query: str, k: int = TOP_K) -> List[Tuple[dict, float]]:
        """Return the top-k most similar chunks with their distance scores."""
        if self.collection.count() == 0:
            return []

        q_emb = (
            _embedder.encode([query], normalize_embeddings=True)
            .astype("float32")
            .tolist()
        )

        results = self.collection.query(query_embeddings=q_emb, n_results=k)

        output: List[Tuple[dict, float]] = []
        if results.get("ids") and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                chunk = {
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] or {},
                }
                distance = (
                    results["distances"][0][i] if results.get("distances") else 0.0
                )
                output.append((chunk, float(distance)))
        return output