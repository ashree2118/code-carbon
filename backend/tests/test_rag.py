import json
from pathlib import Path

import pytest

from app.config import settings
from app.schemas import PracticeResult
from app.services.ast_analyzer import PATTERN_QUERIES
from app.services.rag_service import (
    GreenCodingRAGService,
    RAGUnavailableError,
    get_rag_service,
    load_practices,
    tokenize,
)
from app.main import app
from tests.conftest import FakeRAG

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


# Real keyword search


@pytest.fixture(scope="module")
def rag() -> GreenCodingRAGService:
    return GreenCodingRAGService()


def test_every_ast_pattern_query_finds_its_practice(rag: GreenCodingRAGService):
    # The auditor searches with these exact queries, so each must hit the right practice.
    expected = {
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
    assert expected.keys() == PATTERN_QUERIES.keys()
    for kind, query in PATTERN_QUERIES.items():
        assert rag.search(query)[0].id == expected[kind], kind


@pytest.mark.parametrize(
    "query, expected_id",
    [
        ("nested loop iterating over two lists comparing items", "GCP-001"),
        ("membership test x in list inside loop", "GCP-002"),
        ("list.append in a loop could be a list comprehension", "GCP-004"),
        ("string concatenation with += inside loop", "GCP-005"),
        ("recursive function called repeatedly with same arguments", "GCP-008"),
        ("file opened inside a loop", "GCP-009"),
        ("re.search with pattern string inside loop", "GCP-011"),
        ("pandas iterrows row by row", "GCP-013"),
        ("list.pop(0) used as a queue", "GCP-015"),
    ],
)
def test_retrieval_returns_relevant_practice_first(rag: GreenCodingRAGService, query: str, expected_id: str):
    results = rag.search(query)
    assert results[0].id == expected_id


def test_search_result_shape_and_top_k(rag: GreenCodingRAGService):
    assert len(rag.search("loops")) == settings.rag_top_k
    results = rag.search("loops", top_k=5)
    assert len(results) == 5
    scores = [r.relevance_score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 1.0 and all(0 < s <= 1 for s in scores)
    assert all(r.title and r.content and r.category for r in results)


def test_empty_query_returns_nothing(rag: GreenCodingRAGService):
    assert rag.search("   ") == []


def test_query_with_no_matching_words_returns_nothing(rag: GreenCodingRAGService):
    assert rag.search("zebra giraffe") == []


def test_tokenize_normalizes_plurals_and_drops_stop_words():
    assert tokenize("The loops and files in a list") == ["loop", "file", "list"]


def test_bad_knowledge_base_raises_rag_error(tmp_path: Path):
    path = tmp_path / "practices.json"
    path.write_text("not json")
    with pytest.raises(RAGUnavailableError):
        GreenCodingRAGService(practices_file=path).search("loops")


# Endpoint

RESULT = PracticeResult(id="GCP-001", title="T", content="C", category="Cat", relevance_score=0.9)


def test_search_endpoint_returns_structured_results(client):
    fake = FakeRAG(results=[RESULT] * 5)
    app.dependency_overrides[get_rag_service] = lambda: fake
    response = client.post("/rag/search", json={"query": "nested loops", "top_k": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "nested loops"
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
