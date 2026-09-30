import os
import tempfile
import time
from pathlib import Path

import pytest

from app.config import settings
from app.services import script_runner
from app.services.script_runner import run_python_script


def test_success_captures_stdout_and_exit_code():
    result = run_python_script(b"print('hello')\n", 5)
    assert result.success is True
    assert result.exit_code == 0
    assert result.stdout == "hello\n"
    assert result.timed_out is False
    assert result.execution_time_seconds > 0


def test_python_error_returns_stderr_and_nonzero_exit():
    result = run_python_script(b"raise RuntimeError('intentional failure')\n", 5)
    assert result.success is False
    assert result.exit_code == 1
    assert "intentional failure" in result.stderr


def test_syntax_error_is_reported_not_raised():
    result = run_python_script(b"def broken(:\n", 5)
    assert result.success is False
    assert "SyntaxError" in result.stderr


def test_timeout_stops_script():
    started = time.perf_counter()
    result = run_python_script(b"while True:\n    pass\n", 0.3)
    assert time.perf_counter() - started < 3
    assert result.success is False
    assert result.timed_out is True
    assert result.exit_code is None
    assert "timed out" in result.stderr.lower()


@pytest.mark.skipif(os.name != "posix", reason="uses POSIX process groups")
def test_timeout_kills_child_processes(tmp_path: Path):
    # The script starts a child that would outlive it and hold the output pipe.
    marker = tmp_path / "child_alive"
    source = f"""
import subprocess, sys
subprocess.Popen([sys.executable, "-c", "import time, pathlib; time.sleep(1.5); pathlib.Path({str(marker)!r}).write_text('x')"])
while True:
    pass
""".encode()
    started = time.perf_counter()
    result = run_python_script(source, 0.5)
    assert result.timed_out is True
    assert time.perf_counter() - started < 1.4
    time.sleep(1.5)
    assert not marker.exists(), "child process survived the timeout"


def test_output_is_capped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "max_output_bytes", 1000)
    result = run_python_script(b"for _ in range(10000):\n    print('x' * 100)\n", 5)
    assert result.success is True
    assert len(result.stdout) < 1100
    assert "output truncated" in result.stdout


def test_server_secrets_are_not_passed_to_script(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROQ_API_KEY", "secret-value")
    result = run_python_script(b"import os\nprint(os.environ.get('GROQ_API_KEY'))\n", 5)
    assert result.stdout.strip() == "None"


def test_non_utf8_output_does_not_crash():
    result = run_python_script(b"import sys\nsys.stdout.buffer.write(b'\\xff\\xfe ok')\n", 5)
    assert result.success is True
    assert "ok" in result.stdout


def _track_temp_dirs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    created: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(path)
        return path

    monkeypatch.setattr(script_runner.tempfile, "mkdtemp", tracking_mkdtemp)
    return created


@pytest.mark.parametrize(
    "source, timeout",
    [(b"print('ok')\n", 5), (b"raise SystemExit(3)\n", 5), (b"while True:\n    pass\n", 0.3)],
)
def test_temporary_files_are_cleaned_up(monkeypatch: pytest.MonkeyPatch, source: bytes, timeout: float):
    created = _track_temp_dirs(monkeypatch)
    run_python_script(source, timeout)
    assert created
    assert not any(Path(p).exists() for p in created)


def test_temporary_files_are_cleaned_up_when_launch_fails(monkeypatch: pytest.MonkeyPatch):
    created = _track_temp_dirs(monkeypatch)

    def failing_popen(*args, **kwargs):
        raise OSError("cannot start process")

    monkeypatch.setattr(script_runner.subprocess, "Popen", failing_popen)
    with pytest.raises(OSError):
        run_python_script(b"print('x')\n", 5)
    assert not any(Path(p).exists() for p in created)
