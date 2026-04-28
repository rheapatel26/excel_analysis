"""
pdf_rag.py – PDF ingestion, Gemini embedding, and semantic retrieval for ClaimIQ
Uses: google-generativeai (classic SDK) with models/embedding-001
"""

from __future__ import annotations
import json
import hashlib
import re
import os
from pathlib import Path
from dotenv import load_dotenv

import numpy as np

load_dotenv()

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


CACHE_DIR     = Path(__file__).parent / "rag_cache"
EMBED_MODEL   = "models/gemini-embedding-001"   # standard Gemini embedding model
CHUNK_CHARS   = 1800
OVERLAP_CHARS = 200


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _cache_path(store_id: str) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"{store_id}.json"


def _file_hash(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:16]


def _cosine_similarity(a, b) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom else 0.0


# ─── PDF extraction ──────────────────────────────────────────────────────────

def _extract_pages(pdf_path: str) -> list[dict]:
    if not HAS_PYPDF:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")
    pages = []
    reader = pypdf.PdfReader(pdf_path)
    for i, page in enumerate(reader.pages, 1):
        text = re.sub(r"\s+", " ", page.extract_text() or "").strip()
        if text:
            pages.append({"page": i, "text": text})
    return pages


def _chunk_pages(pages: list[dict]) -> list[dict]:
    chunks = []
    for p in pages:
        text, start = p["text"], 0
        while start < len(text):
            chunk = text[start : start + CHUNK_CHARS].strip()
            if chunk:
                chunks.append({"page": p["page"], "text": chunk})
            start += CHUNK_CHARS - OVERLAP_CHARS
    return chunks


# ─── Embeddings (classic google-generativeai) ────────────────────────────────

def _embed(texts: list[str], api_key: str | None = None, task_type: str = "retrieval_document") -> list[list[float]]:
    if not HAS_GENAI:
        raise RuntimeError("google-generativeai not installed.")
    
    final_key = api_key or os.getenv('GOOGLE_GENERATIVE_AI_API_KEY')
    if not final_key:
        raise ValueError("No Gemini API key provided for embeddings. Add 'GOOGLE_GENERATIVE_AI_API_KEY=...' to .env.")
        
    genai.configure(api_key=final_key)
    embeddings = []
    for text in texts:
        result = genai.embed_content(
            model=EMBED_MODEL,
            content=text,
            task_type=task_type,
        )
        embeddings.append(result["embedding"])
    return embeddings


# ─── Public API ──────────────────────────────────────────────────────────────

def ingest_pdf(pdf_path: str, api_key: str) -> str:
    store_id = _file_hash(pdf_path)
    cache    = _cache_path(store_id)
    if cache.exists():
        return store_id

    pages  = _extract_pages(pdf_path)
    chunks = _chunk_pages(pages)
    if not chunks:
        raise ValueError("Could not extract any text from the PDF.")

    texts      = [c["text"] for c in chunks]
    embeddings = _embed(texts, api_key, task_type="retrieval_document")

    store = [
        {"page": c["page"], "text": c["text"], "embedding": emb}
        for c, emb in zip(chunks, embeddings)
    ]
    cache.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    return store_id


def retrieve(question: str, api_key: str, store_id: str, top_k: int = 5) -> list[dict]:
    cache = _cache_path(store_id)
    if not cache.exists():
        return []
    store = json.loads(cache.read_text(encoding="utf-8"))
    q_emb = _embed([question], api_key, task_type="retrieval_query")[0]
    scored = [
        {"page": item["page"], "text": item["text"],
         "score": _cosine_similarity(q_emb, item["embedding"])}
        for item in store
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def list_stores() -> list[str]:
    if not CACHE_DIR.exists():
        return []
    return [p.stem for p in CACHE_DIR.glob("*.json")]


def delete_store(store_id: str) -> bool:
    cache = _cache_path(store_id)
    if cache.exists():
        cache.unlink()
        return True
    return False
