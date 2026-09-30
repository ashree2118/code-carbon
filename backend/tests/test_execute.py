import pytest

from app.config import settings
from tests.conftest import upload


def test_valid_python_file_executes_and_is_measured(client):
    response = upload(client, "/execute", b"print(sum(i * i for i in range(100000)))\n")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["exit_code"] == 0
    assert body["timed_out"] is False
    assert body["stdout"].strip() == str(sum(i * i for i in range(100000)))
    assert body["execution_time_seconds"] > 0
    # Real CodeCarbon values: never check exact numbers, only that they exist.
    assert body["carbon"]["energy_kwh"] > 0
    assert body["carbon"]["co2_kg"] > 0
    assert body["carbon_error"] is None


def test_python_error_returns_stderr_and_nonzero_exit(client):
    response = upload(client, "/execute", b"raise RuntimeError('intentional failure')\n")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["exit_code"] != 0
    assert "intentional failure" in body["stderr"]
    assert body["carbon"] is not None


def test_timeout_is_enforced_and_still_measured(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "execution_timeout_seconds", 0.3)
    response = upload(client, "/execute", b"while True:\n    pass\n")
    assert response.status_code == 200
    body = response.json()
    assert body["timed_out"] is True
    assert body["exit_code"] is None
    assert "timed out" in body["stderr"].lower()
    assert body["carbon"] is not None


@pytest.mark.parametrize(
    "filename, content, status, message",
    [
        ("notes.txt", b"print('nope')\n", 400, "Only .py files"),
        ("empty.py", b"", 400, "empty"),
        ("blank.py", b"   \n\n", 400, "empty"),
        ("latin1.py", b"print('caf\xe9')\n", 400, "UTF-8"),
        ("nulls.py", b"print(1)\x00\n", 400, "null bytes"),
    ],
)
def test_malformed_uploads_are_rejected(client, filename, content, status, message):
    response = upload(client, "/execute", content, filename=filename)
    assert response.status_code == status
    assert message in response.json()["detail"]


def test_file_larger_than_limit_is_rejected(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 64)
    response = upload(client, "/execute", b"x = '" + (b"a" * 80) + b"'\n")
    assert response.status_code == 413


def test_missing_file_field_is_rejected(client):
    response = client.post("/execute")
    assert response.status_code == 422


def test_health_reports_llm_configuration(client, monkeypatch: pytest.MonkeyPatch):
    assert client.get("/health").json() == {
        "status": "ok",
        "message": "API is running",
        "llm_configured": False,
    }
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    assert client.get("/health").json()["llm_configured"] is True
