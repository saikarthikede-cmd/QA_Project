"""Shared PDF parsing, chunking, embedding, and retrieval utilities."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Globals – model loaded once per process
# ---------------------------------------------------------------------------

_MODEL: Optional[SentenceTransformer] = None

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
TOP_K = 5

# Coarse relevance gate: below this cosine score, treat retrieval as "no match"
# rather than trusting the LLM to notice the context is irrelevant.
MIN_RELEVANCE_SCORE = 0.20


def get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    text: str
    page: int          # 1-based
    source: str = ""   # filename for multi-doc apps
    embedding: Optional[np.ndarray] = field(default=None, repr=False)


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------

def extract_pages(pdf_bytes: bytes) -> List[tuple]:
    """Return list of (page_number_1based, text) pairs.

    Raises ValueError for scanned/image PDFs with no extractable text.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages: List[tuple] = []
    total_chars = 0
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        pages.append((i, text))
        total_chars += len(text)

    if total_chars < 50:
        raise ValueError(
            "No extractable text found. This appears to be a scanned/image PDF. "
            "Please upload a text-based PDF."
        )
    return pages


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_pages(
    pages: List[tuple],
    source: str = "",
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[Chunk]:
    """Slide a window over each page's text, tagging each chunk with its page number."""
    if overlap >= chunk_size:
        raise ValueError(f"overlap ({overlap}) must be smaller than chunk_size ({chunk_size})")
    chunks: List[Chunk] = []
    for page_num, text in pages:
        if not text:
            continue
        start = 0
        while start < len(text):
            chunk_text = text[start:start + chunk_size].strip()
            if chunk_text:
                chunks.append(Chunk(text=chunk_text, page=page_num, source=source))
            start += chunk_size - overlap
    return chunks


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def embed_chunks(chunks: List[Chunk]) -> List[Chunk]:
    model = get_model()
    texts = [c.text for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    for chunk, emb in zip(chunks, embeddings):
        chunk.embedding = emb
    return chunks


def embed_query(query: str) -> np.ndarray:
    return embed_queries([query])[0]


def embed_queries(queries: List[str]) -> np.ndarray:
    """Batch-encode multiple queries in a single model call."""
    model = get_model()
    return model.encode(queries, show_progress_bar=False, convert_to_numpy=True)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def retrieve(
    query: str,
    chunks: List[Chunk],
    top_k: int = TOP_K,
) -> List[RetrievedChunk]:
    if not chunks:
        return []
    return retrieve_with_embedding(embed_query(query), chunks, top_k)


def retrieve_with_embedding(
    query_embedding: np.ndarray,
    chunks: List[Chunk],
    top_k: int = TOP_K,
) -> List[RetrievedChunk]:
    """Same as retrieve(), but for a query already embedded (batch-encode many
    queries once with embed_queries() and reuse each vector across calls)."""
    scored = [
        RetrievedChunk(chunk=c, score=cosine_similarity(query_embedding, c.embedding))
        for c in chunks
        if c.embedding is not None
    ]
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------------------
# Context builder (for LLM prompt)
# ---------------------------------------------------------------------------

def is_grounded(retrieved: List[RetrievedChunk], min_score: float = MIN_RELEVANCE_SCORE) -> bool:
    """Code-level veto: is the top retrieved chunk relevant enough to generate from?

    A coarse pre-filter only — catches the totally-unrelated case. Deliberately
    not a judgment call left to the LLM.
    """
    return bool(retrieved) and retrieved[0].score >= min_score


def build_context(retrieved: List[RetrievedChunk], include_source: bool = False) -> str:
    parts = []
    for i, r in enumerate(retrieved, start=1):
        src = f" | file: {r.chunk.source}" if include_source and r.chunk.source else ""
        parts.append(
            f"[Chunk {i} | page {r.chunk.page}{src} | score {r.score:.3f}]\n{r.chunk.text}"
        )
    return "\n\n---\n\n".join(parts)
