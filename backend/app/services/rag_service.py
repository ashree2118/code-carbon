import json
import logging
from pathlib import Path
from typing import List

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
    except ImportError:
        from langchain.embeddings import HuggingFaceEmbeddings  # type: ignore

try:
    from langchain_chroma import Chroma
except ImportError:
    try:
        from langchain_community.vectorstores import Chroma
    except ImportError:
        from langchain.vectorstores import Chroma  # type: ignore

from langchain_core.documents import Document

from app.config import settings
from app.schemas import PracticeResult

logger = logging.getLogger(__name__)

PRACTICES_FILE = (
    Path(__file__).parent.parent / "knowledge_base" / "practices.json"
)


class GreenCodingRAGService:
    def __init__(self) -> None:
        self._vectorstore: Chroma | None = None
        self._embeddings: HuggingFaceEmbeddings | None = None

    def _get_embeddings(self) -> HuggingFaceEmbeddings:
        if self._embeddings is None:
            self._embeddings = HuggingFaceEmbeddings(
                model_name=settings.embedding_model_name
            )
        return self._embeddings

    def _load_practice_documents(self) -> List[Document]:
        if not PRACTICES_FILE.exists():
            logger.warning("Practices file not found at %s", PRACTICES_FILE)
            return []

        with open(PRACTICES_FILE, "r", encoding="utf-8") as f:
            practices = json.load(f)

        documents: List[Document] = []
        for p in practices:
            page_content = f"{p['title']}. Category: {p['category']}. {p['content']}"
            metadata = {
                "id": p["id"],
                "title": p["title"],
                "category": p["category"],
                "content": p["content"],
            }
            documents.append(Document(page_content=page_content, metadata=metadata))
        return documents

    def get_or_create_vectorstore(self) -> Chroma:
        if self._vectorstore is not None:
            return self._vectorstore

        embeddings = self._get_embeddings()
        persist_dir = settings.chroma_db_dir

        vectorstore = Chroma(
            collection_name="green_coding_practices",
            embedding_function=embeddings,
            persist_directory=persist_dir,
        )

        existing = vectorstore.get()
        if not existing or not existing.get("ids"):
            logger.info("Ingesting green coding practices into ChromaDB...")
            documents = self._load_practice_documents()
            if documents:
                vectorstore.add_documents(documents)
                if hasattr(vectorstore, "persist"):
                    try:
                        vectorstore.persist()
                    except Exception:
                        pass

        self._vectorstore = vectorstore
        return self._vectorstore

    def search_practices(self, query: str, top_k: int = 3) -> List[PracticeResult]:
        if not query or not query.strip():
            return []

        vectorstore = self.get_or_create_vectorstore()
        results = vectorstore.similarity_search_with_score(query.strip(), k=top_k)

        practice_results: List[PracticeResult] = []
        for doc, score in results:
            relevance = round(1.0 / (1.0 + float(score)), 4)
            practice_results.append(
                PracticeResult(
                    title=doc.metadata.get("title", ""),
                    content=doc.metadata.get("content", doc.page_content),
                    category=doc.metadata.get("category", "General"),
                    relevance_score=relevance,
                )
            )

        return practice_results


rag_service = GreenCodingRAGService()
