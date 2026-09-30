"""Retrieve green coding practices with BM25 keyword search.

The knowledge base is knowledge_base/practices.json. It is small (about 20
short practices), so an in-memory BM25 index built on first use is enough.
No embedding model and no vector database are needed.
"""

import math
import re
import threading
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from app.config import settings
from app.schemas import PracticeResult

PRACTICES_FILE = Path(__file__).resolve().parent.parent / "knowledge_base" / "practices.json"

_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "each",
    "for", "from", "has", "if", "in", "instead", "into", "is", "it", "its", "of",
    "on", "one", "or", "same", "so", "such", "than", "that", "the", "then", "this",
    "to", "use", "used", "when", "which", "while", "with", "you", "your",
}


class RAGUnavailableError(RuntimeError):
    """The knowledge base could not be loaded."""


class Practice(BaseModel):
    id: str
    title: str
    category: str
    content: str


def load_practices(path: Path = PRACTICES_FILE) -> list[Practice]:
    practices = TypeAdapter(list[Practice]).validate_json(path.read_bytes())
    ids = [p.id for p in practices]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"Duplicate practice ids in {path.name}: {duplicates}")
    return practices


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in _TOKEN_RE.findall(text.lower()):
        if token in _STOP_WORDS:
            continue
        # Light stemming so "loops" matches "loop" and "files" matches "file".
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        tokens.append(token)
    return tokens


class BM25Index:
    """Okapi BM25 over a fixed list of tokenized documents."""

    def __init__(self, documents: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._term_counts = [Counter(doc) for doc in documents]
        self._lengths = [len(doc) for doc in documents]
        self._avg_length = sum(self._lengths) / max(len(documents), 1)
        doc_freq = Counter(term for doc in documents for term in set(doc))
        n = len(documents)
        self._idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in doc_freq.items()
        }

    def scores(self, query: list[str]) -> list[float]:
        results = []
        for counts, length in zip(self._term_counts, self._lengths):
            score = 0.0
            for term in query:
                tf = counts.get(term, 0)
                if tf:
                    norm = self._k1 * (1 - self._b + self._b * length / self._avg_length)
                    score += self._idf[term] * tf * (self._k1 + 1) / (tf + norm)
            results.append(score)
        return results


class GreenCodingRAGService:
    def __init__(self, practices_file: Path = PRACTICES_FILE) -> None:
        self._practices_file = practices_file
        self._practices: list[Practice] | None = None
        self._index: BM25Index | None = None
        self._lock = threading.Lock()

    def _load(self) -> tuple[list[Practice], BM25Index]:
        with self._lock:
            if self._practices is None or self._index is None:
                try:
                    practices = load_practices(self._practices_file)
                except Exception as exc:
                    raise RAGUnavailableError(f"Knowledge base is unavailable: {exc}") from exc
                # The title is repeated so title words weigh more than body words.
                documents = [
                    tokenize(f"{p.title} {p.title} {p.category} {p.content}") for p in practices
                ]
                self._practices, self._index = practices, BM25Index(documents)
            return self._practices, self._index

    def search(self, query: str, top_k: int | None = None) -> list[PracticeResult]:
        """Best matches first. relevance_score is relative to the best match (1.0)."""
        terms = tokenize(query)
        if not terms:
            return []
        practices, index = self._load()

        ranked = sorted(
            ((score, p) for score, p in zip(index.scores(terms), practices) if score > 0),
            key=lambda pair: pair[0],
            reverse=True,
        )[: top_k or settings.rag_top_k]
        if not ranked:
            return []
        best = ranked[0][0]
        return [
            PracticeResult(
                id=p.id,
                title=p.title,
                content=p.content,
                category=p.category,
                relevance_score=round(score / best, 4),
            )
            for score, p in ranked
        ]


rag_service = GreenCodingRAGService()


def get_rag_service() -> GreenCodingRAGService:
    return rag_service
