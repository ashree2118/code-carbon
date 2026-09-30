import io
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.config import settings
from app.main import app


class FakeLLM:
    """Stands in for the real LLM. Returns canned answers by output type."""

    def __init__(self, responses: dict[type[BaseModel], BaseModel | Exception]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def generate(self, *, system: str, prompt: str, output_type: type[BaseModel]) -> BaseModel:
        self.calls.append({"system": system, "prompt": prompt, "output_type": output_type})
        response = self.responses[output_type]
        if isinstance(response, Exception):
            raise response
        return response


class FakeRAG:
    def __init__(self, results=None, error: Exception | None = None) -> None:
        self.results = results or []
        self.error = error
        self.queries: list[str] = []

    def search(self, query: str, top_k: int | None = None):
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.results[: top_k or 3]


@pytest.fixture(autouse=True)
def no_real_llm_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "groq_api_key", "")


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def upload(client: TestClient, path: str, content: bytes, filename: str = "script.py"):
    return client.post(path, files={"file": (filename, io.BytesIO(content), "text/x-python")})
