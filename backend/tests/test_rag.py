import hashlib
import json
import math
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings

from app.config import settings
from app.main import app
from app.schemas import PracticeResult
from app.services.ast_analyzer import PATTERN_QUERIES
from app.services.knowledge_base import Practice
from app.services.rag_service import (
    GreenCodingRAGService,
    RAGUnavailableError,
    get_rag_service,
    load_practices,
    tokenize,
)
from app.services.vector_retriever import VectorRetriever
from tests.conftest import FakeRAG

# The auditor searches with these exact queries, so each must hit the right practice.
EXPECTED_FOR_PATTERN = {
    "nested_loop": "GCP-001",
    "linear_search_in_loop": "GCP-002",
    "invariant_call_in_loop": "GCP-003",
    "append_loop": "GCP-004",
    "string_concat_in_loop": "GCP-005",
    "list_in_aggregate": "GCP-007",
    "uncached_recursion": "GCP-008",
    "file_io_in_loop": "GCP-009",
    "regex_in_loop": "GCP-011",
    "pandas_row_iteration": "GCP-013",
    "queue_pop_front": "GCP-015",
}

NATURAL_QUERIES = [
    ("nested loop iterating over two lists comparing items", "GCP-001"),
    ("membership test x in list inside loop", "GCP-002"),
    ("list.append in a loop could be a list comprehension", "GCP-004"),
    ("string concatenation with += inside loop", "GCP-005"),
    ("recursive function called repeatedly with same arguments", "GCP-008"),
    ("file opened inside a loop", "GCP-009"),
    ("re.search with pattern string inside loop", "GCP-011"),
    ("pandas iterrows row by row", "GCP-013"),
    ("list.pop(0) used as a queue", "GCP-015"),
]

# Knowledge base


def test_knowledge_base_is_valid():
    practices = load_practices()
    assert 15 <= len(practices) <= 25
    assert len({p.id for p in practices}) == len(practices)
    assert len({p.title for p in practices}) == len(practices)
    for practice in practices:
        assert practice.title.strip() and practice.category.strip()
        assert len(practice.content) > 80


def test_duplicate_ids_are_rejected(tmp_path: Path):
    path = tmp_path / "practices.json"
    item = {"id": "X-1", "title": "t", "category": "c", "content": "body"}
    path.write_text(json.dumps([item, item]))
    with pytest.raises(ValueError, match="Duplicate"):
        load_practices(path)


def test_bad_knowledge_base_raises_rag_error(tmp_path: Path):
    path = tmp_path / "practices.json"
    path.write_text("not json")
    with pytest.raises(RAGUnavailableError):
        GreenCodingRAGService(practices_file=path, backend="keyword").search("loops")


# Keyword (BM25) fallback retriever


@pytest.fixture(scope="module")
def keyword_rag() -> GreenCodingRAGService:
    return GreenCodingRAGService(backend="keyword")


def test_keyword_pattern_queries_find_their_practice(keyword_rag: GreenCodingRAGService):
    assert EXPECTED_FOR_PATTERN.keys() == PATTERN_QUERIES.keys()
    for kind, query in PATTERN_QUERIES.items():
        assert keyword_rag.search(query)[0].id == EXPECTED_FOR_PATTERN[kind], kind


@pytest.mark.parametrize("query, expected_id", NATURAL_QUERIES)
def test_keyword_retrieval_returns_relevant_practice_first(
    keyword_rag: GreenCodingRAGService, query: str, expected_id: str
):
    assert keyword_rag.search(query)[0].id == expected_id


def test_keyword_result_shape_and_top_k(keyword_rag: GreenCodingRAGService):
    assert keyword_rag.retriever_name == "keyword"
    assert len(keyword_rag.search("loops")) == settings.rag_top_k
    results = keyword_rag.search("loops", top_k=5)
    assert len(results) == 5
    scores = [r.relevance_score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 1.0 and all(0 < s <= 1 for s in scores)
    assert all(r.title and r.content and r.category for r in results)


def test_keyword_empty_or_unmatched_query_returns_nothing(keyword_rag: GreenCodingRAGService):
    assert keyword_rag.search("   ") == []
    assert keyword_rag.search("zebra giraffe") == []


def test_tokenize_normalizes_plurals_and_drops_stop_words():
    assert tokenize("The loops and files in a list") == ["loop", "file", "list"]


# Backend selection and fallback


def test_auto_backend_falls_back_to_keyword_when_vector_store_fails():
    def broken(_practices):
        raise OSError("model download failed")

    rag = GreenCodingRAGService(backend="auto", vector_factory=broken)
    assert rag.search(PATTERN_QUERIES["regex_in_loop"])[0].id == "GCP-011"
    assert rag.retriever_name == "keyword"
    assert "model download failed" in rag.fallback_reason


def test_forced_vector_backend_reports_failure_instead_of_falling_back():
    def broken(_practices):
        raise OSError("model download failed")

    rag = GreenCodingRAGService(backend="vector", vector_factory=broken)
    with pytest.raises(RAGUnavailableError, match="Vector store is unavailable"):
        rag.search("loops")


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError):
        GreenCodingRAGService(backend="magic")


# Vector store mechanics, with a small deterministic embedding (fast, offline)


class HashEmbeddings(Embeddings):
    """Bag-of-words hashed into 64 dimensions. Deterministic, no model needed."""

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * 64
        for token in tokenize(text):
            vector[int(hashlib.md5(token.encode()).hexdigest(), 16) % 64] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embedded = getattr(self, "embedded", 0) + len(texts)
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


PRACTICES = [
    Practice(id="A", title="Replace nested loops", category="loops", content="nested loops over two lists " * 5),
    Practice(id="B", title="Cache recursive calls", category="memo", content="recursive function memoize cache " * 5),
    Practice(id="C", title="Batch file writes", category="io", content="open file once write outside loop " * 5),
]


def test_vector_store_retrieves_by_similarity_and_reports_cosine_scores():
    retriever = VectorRetriever(PRACTICES, HashEmbeddings(), persist_dir=None, embedding_id="hash")
    hits = retriever.search("recursive memoize", k=2)
    assert hits[0][0].id == "B"
    assert 0 < hits[0][1] <= 1.0001
    assert hits[0][1] >= hits[1][1]
    assert retriever.search("  ", k=3) == []


def test_vector_store_drops_hits_below_min_relevance():
    retriever = VectorRetriever(
        PRACTICES, HashEmbeddings(), persist_dir=None, embedding_id="hash", min_relevance=0.99
    )
    assert retriever.search("zebra giraffe", k=3) == []


def test_vector_store_is_persisted_and_rebuilt_when_practices_change(tmp_path: Path):
    first = HashEmbeddings()
    VectorRetriever(PRACTICES, first, persist_dir=tmp_path, embedding_id="hash")
    assert first.embedded == 3

    # Same practices: the persisted collection is reused, nothing re-embedded.
    second = HashEmbeddings()
    reused = VectorRetriever(PRACTICES, second, persist_dir=tmp_path, embedding_id="hash")
    assert getattr(second, "embedded", 0) == 0
    assert reused.search("batch file writes", k=1)[0][0].id == "C"

    # Changed knowledge base: the collection is rebuilt with the new content.
    changed = [*PRACTICES[:2], Practice(id="D", title="Use generators", category="mem", content="generator lazy " * 8)]
    third = HashEmbeddings()
    rebuilt = VectorRetriever(changed, third, persist_dir=tmp_path, embedding_id="hash")
    assert third.embedded == 3
    ids = {p.id for p, _ in rebuilt.search("generator lazy file", k=3)}
    assert "D" in ids and "C" not in ids


# Real Sentence Transformers + ChromaDB retrieval


@pytest.fixture(scope="module")
def vector_rag() -> GreenCodingRAGService:
    rag = GreenCodingRAGService(backend="vector")
    original_dir = settings.rag_persist_dir
    settings.rag_persist_dir = ""  # in-memory, so tests never touch the real store
    try:
        rag.warm_up()
    except RAGUnavailableError as exc:
        pytest.skip(f"Embedding model not available: {exc}")
    finally:
        settings.rag_persist_dir = original_dir
    return rag


def test_vector_pattern_queries_find_their_practice(vector_rag: GreenCodingRAGService):
    assert vector_rag.retriever_name == "vector"
    for kind, query in PATTERN_QUERIES.items():
        assert vector_rag.search(query)[0].id == EXPECTED_FOR_PATTERN[kind], kind


@pytest.mark.parametrize("query, expected_id", NATURAL_QUERIES)
def test_vector_retrieval_returns_relevant_practice_first(
    vector_rag: GreenCodingRAGService, query: str, expected_id: str
):
    assert vector_rag.search(query)[0].id == expected_id


def test_vector_returns_top_k_sorted_and_filters_unrelated_queries(vector_rag: GreenCodingRAGService):
    results = vector_rag.search("loops", top_k=5)
    assert len(results) == 5
    scores = [r.relevance_score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert vector_rag.search("zebra giraffe") == []


# Endpoint

RESULT = PracticeResult(id="GCP-001", title="T", content="C", category="Cat", relevance_score=0.9)


def test_search_endpoint_returns_structured_results(client):
    fake = FakeRAG(results=[RESULT] * 5)
    app.dependency_overrides[get_rag_service] = lambda: fake
    response = client.post("/rag/search", json={"query": "nested loops", "top_k": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "nested loops"
    assert body["retriever"] == "fake"
    assert len(body["results"]) == 2
    assert body["results"][0] == RESULT.model_dump()


@pytest.mark.parametrize("payload", [{"query": "x", "top_k": 0}, {"query": "x", "top_k": 100}, {}])
def test_search_endpoint_validates_input(client, payload):
    assert client.post("/rag/search", json=payload).status_code == 422


def test_search_endpoint_reports_unavailable_store(client):
    app.dependency_overrides[get_rag_service] = lambda: FakeRAG(error=RAGUnavailableError("down"))
    response = client.post("/rag/search", json={"query": "loops"})
    assert response.status_code == 503
    assert "down" in response.json()["detail"]
