"""Semantic retrieval: Sentence Transformers embeddings in a ChromaDB store,
queried through LangChain.

The collection is persisted on disk and rebuilt automatically when the
practices or the embedding model change (tracked with a fingerprint stored in
the collection metadata), so restarts do not re-embed anything.
"""

import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.services.knowledge_base import Practice, fingerprint

logger = logging.getLogger(__name__)

COLLECTION_NAME = "green_coding_practices"


def sentence_transformer_embeddings(model_name: str) -> Embeddings:
    # Imported lazily: loading torch and sentence-transformers takes seconds.
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=model_name,
        encode_kwargs={"normalize_embeddings": True},
    )


class VectorRetriever:
    name = "vector"

    def __init__(
        self,
        practices: list[Practice],
        embeddings: Embeddings,
        persist_dir: Path | None,
        embedding_id: str,
        min_relevance: float = 0.0,
    ) -> None:
        self._by_id = {p.id: p for p in practices}
        self._min_relevance = min_relevance
        client_settings = ChromaSettings(anonymized_telemetry=False)
        if persist_dir is None:
            client = chromadb.EphemeralClient(settings=client_settings)
        else:
            persist_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(persist_dir), settings=client_settings)

        expected = fingerprint(practices, embedding_id)
        existing = {c.name for c in client.list_collections()}
        if COLLECTION_NAME in existing:
            stored = (client.get_collection(COLLECTION_NAME).metadata or {}).get("fingerprint")
            if stored != expected:
                logger.info("Knowledge base or embedding model changed; rebuilding the vector store")
                client.delete_collection(COLLECTION_NAME)
                existing.discard(COLLECTION_NAME)

        self._store = Chroma(
            client=client,
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            # Cosine distance, so relevance = 1 - distance is a cosine similarity.
            collection_metadata={"hnsw:space": "cosine", "fingerprint": expected},
        )
        if COLLECTION_NAME not in existing:
            self._store.add_documents(
                [
                    Document(page_content=p.document_text(), metadata={"id": p.id})
                    for p in practices
                ],
                ids=[p.id for p in practices],
            )

    def search(self, query: str, k: int) -> list[tuple[Practice, float]]:
        """Best first. Scores are cosine similarities between query and practice."""
        if not query.strip():
            return []
        hits = self._store.similarity_search_with_score(query, k=k)
        results = []
        for document, distance in hits:
            practice = self._by_id.get(document.metadata.get("id"))
            similarity = 1.0 - float(distance)
            if practice is not None and similarity >= self._min_relevance:
                results.append((practice, similarity))
        return results
