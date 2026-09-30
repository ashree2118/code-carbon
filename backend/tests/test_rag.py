import json
import shutil
from pathlib import Path

import pytest

from app.config import settings
from app.schemas import PracticeResult
from app.services.rag_service import (
    PRACTICES_FILE,
    GreenCodingRAGService,
    RAGUnavailableError,
    get_rag_service,
    load_practices,
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


# Real embeddings and Chroma (uses the local model cache; first run downloads it)


@pytest.fixture(scope="module")
def rag_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("chroma")


@pytest.fixture(scope="module")
def rag(rag_dir: Path) -> GreenCodingRAGService:
    service = GreenCodingRAGService(persist_dir=str(rag_dir))
    report = service.sync()
    assert report.added == report.total == len(load_practices())
    return service


def test_sync_twice_does_not_duplicate(rag: GreenCodingRAGService):
    report = rag.sync()
    assert (report.added, report.updated, report.removed) == (0, 0, 0)
    assert len(rag._get_vectorstore().get()["ids"]) == report.total


def test_store_persists_across_service_instances(rag: GreenCodingRAGService, rag_dir: Path):
    reopened = GreenCodingRAGService(persist_dir=str(rag_dir))
    report = reopened.sync()
    assert report.added == 0 and report.total == len(load_practices())


def test_changed_knowledge_base_is_resynced(tmp_path: Path):
    practices_file = tmp_path / "practices.json"
    shutil.copy(PRACTICES_FILE, practices_file)
    service = GreenCodingRAGService(persist_dir=str(tmp_path / "db"), practices_file=practices_file)
    service.sync()

    data = json.loads(practices_file.read_text())
    data[0]["content"] += " Edited."
    removed_id = data.pop()["id"]
    data.append({"id": "NEW-1", "title": "New practice", "category": "Test", "content": "Brand new content."})
    practices_file.write_text(json.dumps(data))

    report = GreenCodingRAGService(persist_dir=str(tmp_path / "db"), practices_file=practices_file).sync()
    assert (report.added, report.updated, report.removed) == (1, 1, 1)
    ids = service._get_vectorstore().get()["ids"]
    assert removed_id not in ids and "NEW-1" in ids and len(ids) == len(data)


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
    assert all(0 <= s <= 1 for s in scores)
    assert all(r.title and r.content and r.category for r in results)


def test_empty_query_returns_nothing(rag: GreenCodingRAGService):
    assert rag.search("   ") == []


def test_broken_embedding_model_raises_rag_error(tmp_path: Path):
    service = GreenCodingRAGService(persist_dir=str(tmp_path), embedding_model_name="/no/such/model")
    with pytest.raises(RAGUnavailableError):
        service.search("loops")


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
