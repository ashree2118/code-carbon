"""Retrieve green coding practices with embeddings stored in ChromaDB.

The knowledge base lives in knowledge_base/practices.json. On first use the
service syncs it into a persistent Chroma collection: new or edited practices
are (re)embedded, removed ones are deleted, and unchanged ones are left alone.
Each practice is stored under its own id, so syncing never creates duplicates.

Run `python -m app.services.rag_service` to sync ahead of time (this also
downloads the embedding model on first run).
"""

import hashlib
import json
import logging
import re
import threading
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from pydantic import BaseModel, TypeAdapter

from app.config import BACKEND_DIR, settings
from app.schemas import PracticeResult

logger = logging.getLogger(__name__)

PRACTICES_FILE = Path(__file__).resolve().parent.parent / "knowledge_base" / "practices.json"


class RAGUnavailableError(RuntimeError):
    """The vector store or embedding model could not be used."""


class Practice(BaseModel):
    id: str
    title: str
    category: str
    content: str

    def fingerprint(self) -> str:
        payload = json.dumps(self.model_dump(), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SyncReport(BaseModel):
    added: int
    updated: int
    removed: int
    total: int


def load_practices(path: Path = PRACTICES_FILE) -> list[Practice]:
    practices = TypeAdapter(list[Practice]).validate_json(path.read_bytes())
    ids = [p.id for p in practices]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"Duplicate practice ids in {path.name}: {duplicates}")
    return practices


def _collection_name(model_name: str) -> str:
    # One collection per embedding model: vectors from different models
    # cannot be mixed, and their dimensions may differ.
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", model_name.split("/")[-1]).strip("-").lower()
    return f"green-practices-{slug}"[:63]


class GreenCodingRAGService:
    def __init__(
        self,
        persist_dir: str | None = None,
        embedding_model_name: str | None = None,
        practices_file: Path = PRACTICES_FILE,
    ) -> None:
        persist_path = Path(persist_dir or settings.chroma_db_dir)
        if not persist_path.is_absolute():
            persist_path = BACKEND_DIR / persist_path
        self._persist_dir = persist_path
        self._model_name = embedding_model_name or settings.embedding_model_name
        self._practices_file = practices_file
        self._vectorstore: Chroma | None = None
        self._lock = threading.Lock()

    def _open_vectorstore(self) -> Chroma:
        embeddings = HuggingFaceEmbeddings(
            model_name=self._model_name,
            encode_kwargs={"normalize_embeddings": True},
        )
        client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        return Chroma(
            client=client,
            collection_name=_collection_name(self._model_name),
            embedding_function=embeddings,
            collection_configuration={"hnsw": {"space": "cosine"}},
        )

    def _sync(self, vectorstore: Chroma) -> SyncReport:
        practices = {p.id: p for p in load_practices(self._practices_file)}
        stored = vectorstore.get(include=["metadatas"])
        stored_fingerprints = {
            doc_id: (meta or {}).get("fingerprint")
            for doc_id, meta in zip(stored["ids"], stored["metadatas"])
        }

        removed = [doc_id for doc_id in stored_fingerprints if doc_id not in practices]
        changed = [
            p for p in practices.values() if stored_fingerprints.get(p.id) != p.fingerprint()
        ]
        updated = [p.id for p in changed if p.id in stored_fingerprints]

        stale = removed + updated
        if stale:
            vectorstore.delete(ids=stale)
        if changed:
            vectorstore.add_documents(
                [
                    Document(
                        page_content=f"{p.title}. {p.category}. {p.content}",
                        metadata={**p.model_dump(), "fingerprint": p.fingerprint()},
                    )
                    for p in changed
                ],
                ids=[p.id for p in changed],
            )

        report = SyncReport(
            added=len(changed) - len(updated),
            updated=len(updated),
            removed=len(removed),
            total=len(practices),
        )
        if changed or removed:
            logger.info("Synced green coding practices: %s", report)
        return report

    def sync(self) -> SyncReport:
        """Open the store if needed and bring it in line with practices.json."""
        with self._lock:
            try:
                vectorstore = self._vectorstore or self._open_vectorstore()
                report = self._sync(vectorstore)
            except Exception as exc:
                raise RAGUnavailableError(f"Knowledge base is unavailable: {exc}") from exc
            self._vectorstore = vectorstore
            return report

    def _get_vectorstore(self) -> Chroma:
        if self._vectorstore is None:
            self.sync()
        assert self._vectorstore is not None
        return self._vectorstore

    def search(self, query: str, top_k: int | None = None) -> list[PracticeResult]:
        query = query.strip()
        if not query:
            return []
        k = top_k or settings.rag_top_k

        vectorstore = self._get_vectorstore()
        try:
            hits = vectorstore.similarity_search_with_relevance_scores(query, k=k)
        except Exception as exc:
            raise RAGUnavailableError(f"Knowledge base search failed: {exc}") from exc

        return [
            PracticeResult(
                id=doc.metadata["id"],
                title=doc.metadata["title"],
                content=doc.metadata["content"],
                category=doc.metadata["category"],
                relevance_score=round(min(max(score, 0.0), 1.0), 4),
            )
            for doc, score in hits
        ]


rag_service = GreenCodingRAGService()


def get_rag_service() -> GreenCodingRAGService:
    return rag_service


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(rag_service.sync())
