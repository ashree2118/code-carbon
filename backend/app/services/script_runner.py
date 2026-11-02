"""Run untrusted Python source outside the API process.

Two backends, chosen by EXECUTION_SANDBOX:

- docker (default): a fresh, locked-down container per script. See
  docker_sandbox.py.
- subprocess: a child process on the host. It never goes through a shell and
  gets its own temporary directory, a minimal environment (no server secrets),
  a hard timeout that kills the whole process tree, and capped output buffers.
  This is process isolation, not a security sandbox: the script can still read
  files the server user can read.

Both return the same ScriptRunResult. Every caller (execution, measurement,
verification) goes through run_python_script.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import IO

from app.config import settings

_READ_CHUNK_BYTES = 64 * 1024
_READER_JOIN_SECONDS = 2.0
# Environment variables the child may inherit. Everything else (API keys,
# tokens, cloud credentials) is dropped.
_INHERITED_ENV_VARS = ("PATH", "SYSTEMROOT", "LANG", "LC_ALL")

# Only one script runs at a time. CodeCarbon measures the whole machine, so a
# second script (for example a verifier run from another request) running during
# a measurement would be counted in it. Re-entrant so the measurement service can
# hold it around preparation, tracking and the run itself.
execution_lock = threading.RLock()


@dataclass
class ScriptRunResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int | None
    execution_time_seconds: float
    timed_out: bool


class _OutputCollector(threading.Thread):
    """Drain a pipe so the child never blocks, keeping only the first `limit` bytes."""

    def __init__(self, stream: IO[bytes], limit: int) -> None:
        super().__init__(daemon=True)
        self._stream = stream
        self._limit = limit
        self._data = bytearray()
        self.truncated = False

    def run(self) -> None:
        fd = self._stream.fileno()
        try:
            while chunk := os.read(fd, _READ_CHUNK_BYTES):
                room = self._limit - len(self._data)
                if room > 0:
                    self._data.extend(chunk[:room])
                if len(chunk) > room:
                    self.truncated = True
        except OSError:
            pass
        finally:
            self._stream.close()

    def text(self) -> str:
        # Line endings are normalized: on Windows the child writes "\r\n".
        return _decode_output(bytes(self._data), self.truncated, self._limit)


def _child_env(work_dir: str) -> dict[str, str]:
    env = {key: os.environ[key] for key in _INHERITED_ENV_VARS if key in os.environ}
    for key in ("HOME", "TMPDIR", "TEMP", "TMP"):
        env[key] = work_dir
    return env


def _kill_process_tree(process: subprocess.Popen) -> None:
    """Kill the child and anything it started. Safe to call after it has exited."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    else:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
        if process.poll() is None:
            process.kill()


def _decode_output(data: bytes, truncated: bool, limit: int) -> str:
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    if truncated:
        text += f"\n[output truncated after {limit} bytes]"
    return text


def _with_timeout_note(stderr: str, timed_out: bool, timeout_seconds: float) -> str:
    if not timed_out:
        return stderr
    note = f"Execution timed out after {timeout_seconds} seconds"
    return f"{stderr.rstrip()}\n{note}".lstrip()


def prepare_sandbox() -> None:
    """Do any slow setup (starting a container) now, so it is not measured."""
    if settings.execution_sandbox == "docker":
        from app.services.docker_sandbox import get_docker_sandbox

        with execution_lock:
            get_docker_sandbox().prepare()


def run_python_script(source: bytes, timeout_seconds: float) -> ScriptRunResult:
    """Raises SandboxUnavailableError if the docker backend cannot be used."""
    backend = settings.execution_sandbox
    with execution_lock:
        if backend == "docker":
            return _run_in_docker(source, timeout_seconds)
        if backend == "subprocess":
            return _run_in_subprocess(source, timeout_seconds)
    raise ValueError(f"Unknown EXECUTION_SANDBOX {backend!r}; use docker or subprocess")


def _run_in_docker(source: bytes, timeout_seconds: float) -> ScriptRunResult:
    from app.services.docker_sandbox import get_docker_sandbox

    run = get_docker_sandbox().run(source, timeout_seconds)
    limit = settings.max_output_bytes
    return ScriptRunResult(
        success=not run.timed_out and run.exit_code == 0,
        stdout=_decode_output(run.stdout, run.stdout_truncated, limit),
        stderr=_with_timeout_note(
            _decode_output(run.stderr, run.stderr_truncated, limit), run.timed_out, timeout_seconds
        ),
        exit_code=None if run.timed_out else run.exit_code,
        execution_time_seconds=round(run.elapsed_seconds, 4),
        timed_out=run.timed_out,
    )


def _run_in_subprocess(source: bytes, timeout_seconds: float) -> ScriptRunResult:
    work_dir = tempfile.mkdtemp(prefix="cfo-exec-")
    try:
        script_path = os.path.join(work_dir, "script.py")
        with open(script_path, "wb") as handle:
            handle.write(source)

        popen_kwargs: dict = {}
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        else:
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        started = time.perf_counter()
        process = subprocess.Popen(
            # -I: isolated mode (ignores PYTHON* env vars and user site-packages)
            # -B: do not write .pyc files; -X utf8: stable UTF-8 stdio everywhere
            [sys.executable, "-I", "-B", "-X", "utf8", script_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=work_dir,
            env=_child_env(work_dir),
            **popen_kwargs,
        )
        try:
            stdout = _OutputCollector(process.stdout, settings.max_output_bytes)
            stderr = _OutputCollector(process.stderr, settings.max_output_bytes)
            stdout.start()
            stderr.start()

            timed_out = False
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
            elapsed = time.perf_counter() - started
        finally:
            # Always runs, even on errors. Also kills background children
            # that could keep the pipes open after the main process exits.
            _kill_process_tree(process)
            process.wait()
        stdout.join(_READER_JOIN_SECONDS)
        stderr.join(_READER_JOIN_SECONDS)

        stderr_text = _with_timeout_note(stderr.text(), timed_out, timeout_seconds)

        return ScriptRunResult(
            success=not timed_out and process.returncode == 0,
            stdout=stdout.text(),
            stderr=stderr_text,
            exit_code=None if timed_out else process.returncode,
            execution_time_seconds=round(elapsed, 4),
            timed_out=timed_out,
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
