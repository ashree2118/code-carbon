"""Retrieve green coding practices for the auditor (the "R" in RAG).

Primary retriever: Sentence Transformers embeddings stored in ChromaDB and
queried through LangChain (see vector_retriever.py). If that cannot be loaded
(for example offline before the embedding model was ever downloaded) and
RAG_BACKEND is "auto", BM25 keyword search is used instead, and the response
says which retriever answered.
"""

import logging
import threading
from pathlib import Path
from typing import Protocol

from app.config import settings
from app.schemas import PracticeResult
from app.services.keyword_retriever import KeywordRetriever, tokenize
from app.services.knowledge_base import PRACTICES_FILE, Practice, load_practices

__all__ = [
    "GreenCodingRAGService",
    "RAGUnavailableError",
    "get_rag_service",
    "load_practices",
    "tokenize",
]

logger = logging.getLogger(__name__)


class RAGUnavailableError(RuntimeError):
    """The knowledge base or retriever could not be loaded."""


class Retriever(Protocol):
    name: str

    def search(self, query: str, k: int) -> list[tuple[Practice, float]]: ...


def _build_vector_retriever(practices: list[Practice]) -> Retriever:
    from app.services.vector_retriever import VectorRetriever, sentence_transformer_embeddings

    persist_dir = Path(settings.rag_persist_dir) if settings.rag_persist_dir else None
    return VectorRetriever(
        practices,
        sentence_transformer_embeddings(settings.rag_embedding_model),
        persist_dir=persist_dir,
        embedding_id=settings.rag_embedding_model,
        min_relevance=settings.rag_min_relevance,
    )


class GreenCodingRAGService:
    def __init__(
        self,
        practices_file: Path = PRACTICES_FILE,
        backend: str | None = None,
        vector_factory=_build_vector_retriever,
    ) -> None:
        self._practices_file = practices_file
        self._backend = (backend or settings.rag_backend).lower()
        if self._backend not in {"auto", "vector", "keyword"}:
            raise ValueError(f"Unknown RAG backend {self._backend!r}")
        self._vector_factory = vector_factory
        self._retriever: Retriever | None = None
        self.fallback_reason: str | None = None
        self._lock = threading.Lock()

    def _load(self) -> Retriever:
        with self._lock:
            if self._retriever is not None:
                return self._retriever
            try:
                practices = load_practices(self._practices_file)
            except Exception as exc:
                raise RAGUnavailableError(f"Knowledge base is unavailable: {exc}") from exc

            if self._backend == "keyword":
                self._retriever = KeywordRetriever(practices)
                return self._retriever
            try:
                self._retriever = self._vector_factory(practices)
            except Exception as exc:
                if self._backend == "vector":
                    raise RAGUnavailableError(f"Vector store is unavailable: {exc}") from exc
                logger.warning("Vector retrieval unavailable, using keyword search: %s", exc)
                self.fallback_reason = f"Vector retrieval unavailable ({exc}); used keyword search."
                self._retriever = KeywordRetriever(practices)
            return self._retriever

    @property
    def retriever_name(self) -> str:
        return self._load().name

    def warm_up(self) -> None:
        """Load the embedding model and vector store now instead of on first search."""
        self._load()

    def search(self, query: str, top_k: int | None = None) -> list[PracticeResult]:
        """Best matches first, at most top_k (default RAG_TOP_K)."""
        if not query.strip():
            return []
        retriever = self._load()
        try:
            hits = retriever.search(query, top_k or settings.rag_top_k)
        except Exception as exc:
            raise RAGUnavailableError(f"Retrieval failed: {exc}") from exc
        return [
            PracticeResult(
                id=p.id,
                title=p.title,
                content=p.content,
                category=p.category,
                relevance_score=round(score, 4),
            )
            for p, score in hits
        ]


rag_service = GreenCodingRAGService()


def get_rag_service() -> GreenCodingRAGService:
    return rag_service
