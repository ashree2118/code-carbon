"""The Docker execution backend. Skipped when Docker is not running."""

import shutil
import subprocess

import pytest

from app.config import settings
from app.services import docker_sandbox
from app.services.docker_sandbox import LABEL, SandboxUnavailableError, get_docker_sandbox
from app.services.measurement_service import measure_script_execution
from app.services.script_runner import run_python_script
from tests.conftest import upload


def _docker_running() -> bool:
    docker = shutil.which("docker")
    if not docker:
        return False
    return subprocess.run([docker, "info"], capture_output=True).returncode == 0


needs_docker = pytest.mark.skipif(not _docker_running(), reason="Docker is not running")


@pytest.fixture
def docker_backend(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "execution_sandbox", "docker")


def run(source: str, timeout: float = 5):
    return run_python_script(source.encode(), timeout)


@needs_docker
def test_runs_script_and_captures_output(docker_backend):
    result = run("print('hello')\n")
    assert result.success is True
    assert result.exit_code == 0
    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert 0 < result.execution_time_seconds < 2


@needs_docker
def test_reports_errors_and_exit_codes(docker_backend):
    failed = run("raise RuntimeError('intentional failure')\n")
    assert failed.success is False and failed.exit_code == 1
    assert "intentional failure" in failed.stderr
    assert run("import sys; sys.exit(3)\n").exit_code == 3


@needs_docker
def test_timeout_kills_the_script(docker_backend):
    result = run("while True: pass\n", timeout=1)
    assert result.timed_out is True
    assert result.success is False and result.exit_code is None
    assert "timed out after 1" in result.stderr
    assert result.execution_time_seconds < 3


@needs_docker
def test_script_runs_unprivileged_without_network_or_secrets(docker_backend, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "do-not-leak")
    result = run(
        "import os, socket\n"
        "print(os.getuid())\n"
        "print('SECRET_TOKEN' in os.environ)\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=2)\n"
        "    print('network open')\n"
        "except OSError:\n"
        "    print('network blocked')\n"
        "for path in ('/etc/x', '/job/script.py'):\n"
        "    try:\n"
        "        open(path, 'a').write('x')\n"
        "        print('wrote', path)\n"
        "    except OSError:\n"
        "        print('read-only', path)\n"
    )
    assert result.stdout.split("\n")[:5] == [
        "65534",
        "False",
        "network blocked",
        "read-only /etc/x",
        "read-only /job/script.py",
    ]


@needs_docker
def test_each_script_gets_a_fresh_container(docker_backend):
    first = run("import pathlib; pathlib.Path('/work/left.txt').write_text('x'); print('ok')\n")
    assert first.stdout == "ok\n"
    second = run("import os; print(os.path.exists('/work/left.txt'))\n")
    assert second.stdout == "False\n"


@needs_docker
def test_background_processes_do_not_break_the_run(docker_backend):
    result = run("import subprocess; subprocess.Popen(['sleep', '1000']); print('spawned')\n")
    assert result.success is True
    assert result.stdout == "spawned\n"


@needs_docker
def test_output_is_capped(docker_backend, monkeypatch):
    monkeypatch.setattr(settings, "max_output_bytes", 1000)
    sandbox = docker_sandbox.DockerSandbox()  # new instance so the new limit is used
    monkeypatch.setattr(docker_sandbox, "_sandbox", sandbox)
    try:
        result = run("print('x' * 5000)\n")
    finally:
        sandbox.shutdown()
    assert result.stdout.startswith("x" * 1000)
    assert "[output truncated after 1000 bytes]" in result.stdout


@needs_docker
def test_measurement_through_docker_returns_real_carbon(docker_backend):
    measured = measure_script_execution(b"print(sum(i * i for i in range(10**6)))\n", 10)
    assert measured.run.success is True
    assert measured.carbon_error is None
    assert measured.carbon is not None
    assert measured.carbon.energy_kwh > 0 and measured.carbon.co2_kg > 0


@needs_docker
def test_execute_endpoint_uses_docker(docker_backend, client):
    response = upload(client, "/execute", b"import os\nprint(os.getuid())\n")
    assert response.status_code == 200
    body = response.json()
    assert body["stdout"] == "65534\n"
    assert body["carbon"]["energy_kwh"] > 0


@needs_docker
def test_no_containers_are_left_behind(docker_backend):
    run("print(1)\n")
    sandbox = get_docker_sandbox()
    sandbox.shutdown()
    for thread in sandbox._retiring:
        thread.join(timeout=15)
    names = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"label={LABEL}=1", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    ).stdout.split()
    assert not [n for n in names if n.startswith(LABEL)], names


def test_missing_docker_gives_a_clear_error(docker_backend, monkeypatch):
    monkeypatch.setattr(docker_sandbox.shutil, "which", lambda _name: None)
    monkeypatch.setattr(docker_sandbox, "_sandbox", docker_sandbox.DockerSandbox())
    with pytest.raises(SandboxUnavailableError, match="EXECUTION_SANDBOX=subprocess"):
        run("print(1)\n")


def test_missing_docker_returns_503_from_the_api(docker_backend, monkeypatch, client):
    monkeypatch.setattr(docker_sandbox.shutil, "which", lambda _name: None)
    monkeypatch.setattr(docker_sandbox, "_sandbox", docker_sandbox.DockerSandbox())
    response = upload(client, "/execute", b"print(1)\n")
    assert response.status_code == 503
    assert "Docker" in response.json()["detail"]
