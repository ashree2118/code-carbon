import json
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.main import app
from app.services.rag_service import rag_service

client = TestClient(app)

PRACTICES_FILE = (
    Path(__file__).parent.parent / "app" / "knowledge_base" / "practices.json"
)


def test_practices_json_valid_and_contains_20_items():
    assert PRACTICES_FILE.exists()
    with open(PRACTICES_FILE, "r", encoding="utf-8") as f:
        practices = json.load(f)
    assert len(practices) >= 20
    for item in practices:
        assert "id" in item
        assert "title" in item
        assert "category" in item
        assert "content" in item


def test_rag_search_endpoint_with_query_nested_loops(monkeypatch):
    mock_docs = [
        (
            Document(
                page_content="Optimize Nested Loops. Category: Loops & Iteration. Avoid quadratic O(N^2) loops.",
                metadata={
                    "title": "Optimize Nested Loops and Repeated Calculations",
                    "category": "Loops & Iteration",
                    "content": "Avoid quadratic O(N^2) nested loops by hoisting invariant computations out of loops.",
                },
            ),
            0.15,
        ),
        (
            Document(
                page_content="Cache Expensive Function Results. Category: Caching & Memoization.",
                metadata={
                    "title": "Cache Expensive Function Results",
                    "category": "Caching & Memoization",
                    "content": "Use functools.lru_cache for deterministic functions.",
                },
            ),
            0.32,
        ),
        (
            Document(
                page_content="Fast Membership Testing. Category: Data Structures.",
                metadata={
                    "title": "Fast Membership Testing with Sets and Dicts",
                    "category": "Data Structures",
                    "content": "Convert lists to sets or dicts for O(1) membership testing.",
                },
            ),
            0.45,
        ),
    ]

    mock_vectorstore = MagicMock()
    mock_vectorstore.similarity_search_with_score.return_value = mock_docs

    monkeypatch.setattr(
        rag_service, "get_or_create_vectorstore", lambda: mock_vectorstore
    )

    response = client.post(
        "/rag/search",
        json={"query": "nested loops and repeated calculations", "top_k": 3},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "nested loops and repeated calculations"
    assert len(data["results"]) == 3

    first = data["results"][0]
    assert first["title"] == "Optimize Nested Loops and Repeated Calculations"
    assert first["category"] == "Loops & Iteration"
    assert "content" in first
    assert "relevance_score" in first
    assert isinstance(first["relevance_score"], float)


def test_rag_search_empty_query():
    response = client.post("/rag/search", json={"query": "  ", "top_k": 3})
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []
