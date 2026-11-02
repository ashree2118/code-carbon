"""Run untrusted Python inside a locked-down, single-use Docker container.

Starting a container takes about a second, and `docker exec` still costs
hundreds of milliseconds on Docker Desktop. Either would land inside the
CodeCarbon measurement. So each container is started ahead of time with a small
worker (WORKER_CODE) that waits on stdin for one job:

    prepare()  start container, wait for "ready"   (outside the measurement)
    run()      send the script, read the result     (the measured part)
    retire     kill the container, pre-start next   (outside the measurement)

Every script gets a fresh container, so nothing one script leaves behind (files,
background processes) can affect the next one. The container has no network, a
read-only root filesystem, memory/CPU/PID limits, and no capabilities except
SETUID/SETGID (used by the root worker to drop the script to `nobody`) and KILL
(to kill the script's process group on timeout). The script itself has no
capabilities and cannot write to the worker's files or signal or trace it.
"""

import atexit
import base64
import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

LABEL = "cfo-sandbox"
_READY = "CFO-READY"

# Runs inside the container as root (with only SETUID/SETGID). Reads one job,
# runs the script as nobody in its own session, and prints one JSON result.
WORKER_CODE = r"""
import base64, json, os, signal, subprocess, sys, time
limit = int(sys.argv[1])
print("CFO-READY", flush=True)
job = json.loads(sys.stdin.readline())
with open("/job/script.py", "wb") as f:
    f.write(base64.b64decode(job["source"]))
out, err = open("/job/stdout", "wb"), open("/job/stderr", "wb")
env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/work", "TMPDIR": "/tmp", "LANG": "C.UTF-8"}
started = time.perf_counter()
proc = subprocess.Popen(
    [sys.executable, "-I", "-B", "-X", "utf8", "/job/script.py"],
    stdin=subprocess.DEVNULL, stdout=out, stderr=err, cwd="/work", env=env,
    user=65534, group=65534, extra_groups=[], start_new_session=True,
)
timed_out = False
try:
    proc.wait(timeout=job["timeout"])
except subprocess.TimeoutExpired:
    timed_out = True
elapsed = time.perf_counter() - started
try:
    os.killpg(proc.pid, signal.SIGKILL)
except ProcessLookupError:
    pass
proc.wait()
out.close(); err.close()

def read(path):
    with open(path, "rb") as f:
        data = f.read(limit + 1)
    return base64.b64encode(data[:limit]).decode(), len(data) > limit

stdout, stdout_cut = read("/job/stdout")
stderr, stderr_cut = read("/job/stderr")
print(json.dumps({
    "nonce": job["nonce"], "exit_code": proc.returncode, "timed_out": timed_out,
    "elapsed": elapsed, "stdout": stdout, "stdout_truncated": stdout_cut,
    "stderr": stderr, "stderr_truncated": stderr_cut,
}), flush=True)
"""


class SandboxUnavailableError(RuntimeError):
    """Docker is not installed, not running, or the sandbox could not start."""


@dataclass
class SandboxRun:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool
    elapsed_seconds: float
    timed_out: bool


class _Container:
    """One started container whose worker is waiting for its job."""

    def __init__(self, docker: str) -> None:
        self.docker = docker
        self.name = f"{LABEL}-{uuid.uuid4().hex[:12]}"
        cmd = [
            docker, "run", "-i", "--rm", "--name", self.name,
            "--label", f"{LABEL}=1", "--label", f"{LABEL}-owner-pid={os.getpid()}",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/job:rw,size=16m,mode=0755",
            "--tmpfs", "/work:rw,size=64m,uid=65534,gid=65534,mode=0711",
            "--tmpfs", "/tmp:rw,size=64m,mode=1777",
            "--memory", settings.docker_memory, "--memory-swap", settings.docker_memory,
            "--cpus", str(settings.docker_cpus),
            "--pids-limit", "64",
            "--cap-drop", "ALL", "--cap-add", "SETUID", "--cap-add", "SETGID", "--cap-add", "KILL",
            "--security-opt", "no-new-privileges",
            "--user", "0:0",
            settings.docker_image,
            "python", "-I", "-u", "-c", WORKER_CODE, str(settings.max_output_bytes),
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
        self._lines: queue.Queue[bytes | None] = queue.Queue()
        self._stderr = bytearray()
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        for chunk in iter(lambda: self.process.stderr.read(4096), b""):
            if len(self._stderr) < 8192:
                self._stderr.extend(chunk)

    def docker_error(self) -> str:
        return self._stderr.decode("utf-8", errors="replace").strip()[-800:]

    def next_line(self, timeout: float) -> bytes | None:
        """The worker's next output line, or None if it exited or timed out."""
        try:
            return self._lines.get(timeout=timeout)
        except queue.Empty:
            return None

    def wait_ready(self, timeout: float) -> None:
        line = self.next_line(timeout)
        if line is None or line.decode(errors="replace").strip() != _READY:
            self.kill()
            raise SandboxUnavailableError(
                "The Docker sandbox did not start"
                + (f": {self.docker_error()}" if self.docker_error() else ".")
            )

    def kill(self) -> None:
        try:
            subprocess.run([self.docker, "rm", "-f", self.name], capture_output=True, check=False)
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=10)
        except Exception as exc:  # also runs during interpreter shutdown
            logger.debug("Could not remove sandbox container %s: %s", self.name, exc)


class DockerSandbox:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready: _Container | None = None
        self._prewarm: threading.Thread | None = None
        self._prewarm_error: Exception | None = None
        self._checked = False
        self._retiring: list[threading.Thread] = []
        atexit.register(self.shutdown)

    def _docker(self) -> str:
        docker = shutil.which("docker")
        if not docker:
            raise SandboxUnavailableError(
                "Docker is not installed or not on PATH. Install Docker, or set "
                "EXECUTION_SANDBOX=subprocess to run scripts without a container."
            )
        return docker

    def _check_docker(self, docker: str) -> None:
        if self._checked:
            return
        info = subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True)
        if info.returncode != 0:
            raise SandboxUnavailableError(
                "Docker is not running. Start Docker, or set EXECUTION_SANDBOX=subprocess."
            )
        image = settings.docker_image
        if subprocess.run([docker, "image", "inspect", image], capture_output=True).returncode != 0:
            logger.info("Pulling sandbox image %s", image)
            pulled = subprocess.run([docker, "pull", image], capture_output=True, text=True)
            if pulled.returncode != 0:
                raise SandboxUnavailableError(f"Could not pull {image}: {pulled.stderr.strip()[-400:]}")
        self._remove_orphans(docker)
        self._checked = True

    def _remove_orphans(self, docker: str) -> None:
        """Remove sandbox containers left by server processes that no longer exist."""
        import psutil

        listed = subprocess.run(
            [docker, "ps", "-a", "--filter", f"label={LABEL}=1",
             "--format", '{{.Names}} {{.Label "' + LABEL + '-owner-pid"}}'],
            capture_output=True, text=True,
        )
        for line in listed.stdout.splitlines():
            name, _, pid = line.partition(" ")
            if pid.isdigit() and int(pid) != os.getpid() and not psutil.pid_exists(int(pid)):
                subprocess.run([docker, "rm", "-f", name], capture_output=True, check=False)

    def _start_container(self) -> _Container:
        docker = self._docker()
        self._check_docker(docker)
        container = _Container(docker)
        container.wait_ready(settings.docker_start_timeout_seconds)
        return container

    def _prewarm_next(self) -> None:
        def start() -> None:
            try:
                self._ready = self._start_container()
            except Exception as exc:  # reported by the next prepare()
                self._prewarm_error = exc

        self._prewarm_error = None
        self._prewarm = threading.Thread(target=start, daemon=True)
        self._prewarm.start()

    def _take_ready(self) -> _Container:
        if self._prewarm is not None:
            self._prewarm.join()
            self._prewarm = None
        if self._ready is None or self._ready.process.poll() is not None:
            self._ready = self._start_container()
        return self._ready

    def prepare(self) -> None:
        """Make sure a container is started and idle. Call before measuring."""
        with self._lock:
            self._take_ready()

    def run(self, source: bytes, timeout_seconds: float) -> SandboxRun:
        with self._lock:
            container = self._take_ready()
            self._ready = None
            nonce = uuid.uuid4().hex
            job = {"source": base64.b64encode(source).decode(), "timeout": timeout_seconds, "nonce": nonce}
            started = time.perf_counter()
            try:
                assert container.process.stdin is not None
                container.process.stdin.write((json.dumps(job) + "\n").encode())
                container.process.stdin.close()
                # The worker enforces the timeout itself; this is only a backstop.
                line = container.next_line(timeout_seconds + settings.docker_start_timeout_seconds)
            except OSError as exc:
                line = None
                logger.warning("Lost the sandbox container: %s", exc)
            host_elapsed = time.perf_counter() - started
            result = self._parse(line, nonce, timeout_seconds, host_elapsed, container)
            retire = threading.Thread(target=container.kill, daemon=True)
            retire.start()
            self._retiring = [t for t in self._retiring if t.is_alive()] + [retire]
            self._prewarm_next()
            return result

    @staticmethod
    def _parse(
        line: bytes | None, nonce: str, timeout: float, host_elapsed: float, container: _Container
    ) -> SandboxRun:
        data = None
        if line is not None:
            try:
                data = json.loads(line)
            except ValueError:
                data = None
        if not isinstance(data, dict) or data.get("nonce") != nonce:
            detail = container.docker_error()
            timed_out = host_elapsed >= timeout
            message = (
                f"The sandbox stopped responding after {host_elapsed:.1f} seconds"
                if timed_out
                else "The sandbox container exited before returning a result"
            )
            if detail:
                message += f": {detail}"
            return SandboxRun(None, b"", message.encode(), False, False, host_elapsed, timed_out)
        return SandboxRun(
            exit_code=None if data["timed_out"] else data["exit_code"],
            stdout=base64.b64decode(data["stdout"]),
            stderr=base64.b64decode(data["stderr"]),
            stdout_truncated=bool(data["stdout_truncated"]),
            stderr_truncated=bool(data["stderr_truncated"]),
            elapsed_seconds=float(data["elapsed"]),
            timed_out=bool(data["timed_out"]),
        )

    def shutdown(self) -> None:
        for thread in self._retiring:
            thread.join(timeout=15)
        if self._prewarm is not None:
            self._prewarm.join(timeout=30)
        if self._ready is not None:
            self._ready.kill()
            self._ready = None


_sandbox: DockerSandbox | None = None
_sandbox_lock = threading.Lock()


def get_docker_sandbox() -> DockerSandbox:
    global _sandbox
    with _sandbox_lock:
        if _sandbox is None:
            _sandbox = DockerSandbox()
        return _sandbox
