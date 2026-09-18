import io
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def _upload(filename: str, content: bytes, content_type: str = "text/x-python"):
    return client.post(
        "/execute",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


def test_valid_python_file_executes_successfully():
    response = _upload("hello.py", b"print('hello from phase 2')\n")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["exit_code"] == 0
    assert body["timed_out"] is False
    assert body["execution_time_seconds"] >= 0


def test_stdout_is_returned():
    response = _upload("stdout.py", b"print('captured stdout')\n")
    assert response.status_code == 200
    assert "captured stdout" in response.json()["stdout"]


def test_invalid_file_extension_is_rejected():
    response = _upload("notes.txt", b"print('nope')\n", "text/plain")
    assert response.status_code == 400
    assert "Only .py files are allowed" in response.json()["detail"]


def test_file_larger_than_limit_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 64)
    response = _upload("too_big.py", b"x = '" + (b"a" * 80) + b"'\n")
    assert response.status_code == 413
    assert "limit" in response.json()["detail"].lower()


def test_python_error_returns_stderr_and_nonzero_exit():
    response = _upload("boom.py", b"raise RuntimeError('intentional failure')\n")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["exit_code"] != 0
    assert "intentional failure" in body["stderr"]


def test_long_running_script_is_stopped_by_timeout(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "execution_timeout_seconds", 0.3)
    response = _upload("loop.py", b"while True:\n    pass\n")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["timed_out"] is True
    assert body["exit_code"] is None
    assert "timed out" in body["stderr"].lower()


def test_temporary_files_are_cleaned_up(monkeypatch: pytest.MonkeyPatch):
    created: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(path)
        return path

    monkeypatch.setattr("app.services.script_runner.tempfile.mkdtemp", tracking_mkdtemp)

    response = _upload("cleanup.py", b"print('cleanup')\n")
    assert response.status_code == 200
    assert created
    for path in created:
        assert not Path(path).exists()
