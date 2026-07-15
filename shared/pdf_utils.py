"""Shared PDF parsing, chunking, embedding, and retrieval utilities.

Retrieval routes through LangChain's InMemoryVectorStore for the similarity
search step (same cosine-similarity math as before — verified equivalent),
while embeddings themselves still come from the local sentence-transformers
model via a thin LangChain Embeddings wrapper, so the model is loaded once
per process exactly as before.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
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


class _SentenceTransformerEmbeddings(Embeddings):
    """Thin LangChain Embeddings wrapper around the local sentence-transformers
    model, so retrieval can go through LangChain's vectorstore API without
    switching embedding models or adding a network-dependent embedder."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        model = get_model()
        return model.encode(texts, show_progress_bar=False, convert_to_numpy=True).tolist()

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


_EMBEDDINGS = _SentenceTransformerEmbeddings()


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
    texts = [c.text for c in chunks]
    embeddings = _EMBEDDINGS.embed_documents(texts)
    for chunk, emb in zip(chunks, embeddings):
        chunk.embedding = np.array(emb)
    return chunks


def embed_query(query: str) -> np.ndarray:
    return np.array(_EMBEDDINGS.embed_query(query))


def embed_queries(queries: List[str]) -> np.ndarray:
    """Batch-encode multiple queries in a single model call."""
    return np.array(_EMBEDDINGS.embed_documents(queries))


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
    queries once with embed_queries() and reuse each vector across calls).

    Builds a fresh InMemoryVectorStore per call, populated directly from each
    chunk's already-computed embedding (bypassing add_texts/add_documents,
    which would otherwise re-run the embedding model on every retrieval) —
    this is cheap dict bookkeeping, not re-embedding, so performance matches
    the previous hand-rolled cosine loop.
    """
    embedded = [c for c in chunks if c.embedding is not None]
    if not embedded:
        return []

    store = InMemoryVectorStore(embedding=_EMBEDDINGS)
    for i, c in enumerate(embedded):
        doc_id = str(i)
        store.store[doc_id] = {
            "id": doc_id,
            "vector": c.embedding.tolist(),
            "text": c.text,
            "metadata": {"_chunk_index": i},
        }

    q_vec = query_embedding.tolist() if hasattr(query_embedding, "tolist") else list(query_embedding)
    results = store.similarity_search_with_score_by_vector(q_vec, k=top_k)
    return [
        RetrievedChunk(chunk=embedded[doc.metadata["_chunk_index"]], score=score)
        for doc, score in results
    ]


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
