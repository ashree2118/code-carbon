import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass


@dataclass
class ScriptRunResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int | None
    execution_time_seconds: float
    timed_out: bool


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_python_script(source: bytes, timeout_seconds: float) -> ScriptRunResult:
    temp_dir = tempfile.mkdtemp(prefix="cfo-exec-")
    script_path = os.path.join(temp_dir, "script.py")

    try:
        with open(script_path, "wb") as handle:
            handle.write(source)

        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=temp_dir,
                check=False,
            )
            elapsed = time.perf_counter() - started
            return ScriptRunResult(
                success=completed.returncode == 0,
                stdout=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
                execution_time_seconds=round(elapsed, 4),
                timed_out=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.perf_counter() - started
            stderr = _to_text(exc.stderr)
            if not stderr:
                stderr = f"Execution timed out after {timeout_seconds} seconds"
            return ScriptRunResult(
                success=False,
                stdout=_to_text(exc.stdout),
                stderr=stderr,
                exit_code=None,
                execution_time_seconds=round(elapsed, 4),
                timed_out=True,
            )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
