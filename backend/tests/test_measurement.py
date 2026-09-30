from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import measurement_service
from app.services.measurement_service import measure_script_execution


def test_real_measurement_returns_energy_co2_and_time():
    measured = measure_script_execution(b"print(sum(range(10**6)))\n", 5)
    assert measured.run.success is True
    assert measured.run.execution_time_seconds > 0
    assert measured.carbon is not None
    assert measured.carbon.energy_kwh > 0
    assert measured.carbon.co2_kg > 0
    assert measured.carbon_error is None


def test_tracker_wraps_only_the_script_run(monkeypatch: pytest.MonkeyPatch):
    events: list[str] = []
    tracker = MagicMock()
    tracker.start.side_effect = lambda: events.append("start")
    tracker.stop.side_effect = lambda: events.append("stop")
    tracker.final_emissions_data = SimpleNamespace(energy_consumed=0.00012, emissions=0.00005)
    monkeypatch.setattr(measurement_service, "OfflineEmissionsTracker", lambda **kwargs: tracker)

    real_run = measurement_service.run_python_script

    def recording_run(source, timeout):
        events.append("run")
        return real_run(source, timeout)

    monkeypatch.setattr(measurement_service, "run_python_script", recording_run)

    measured = measure_script_execution(b"print('measured')\n", 5)
    assert events == ["start", "run", "stop"]
    assert measured.carbon.energy_kwh == 0.00012
    assert measured.carbon.co2_kg == 0.00005


def test_codecarbon_start_failure_still_runs_script(monkeypatch: pytest.MonkeyPatch):
    def failing_tracker(**kwargs):
        raise RuntimeError("tracking unavailable")

    monkeypatch.setattr(measurement_service, "OfflineEmissionsTracker", failing_tracker)
    measured = measure_script_execution(b"print('still runs')\n", 5)
    assert measured.run.success is True
    assert measured.run.stdout == "still runs\n"
    assert measured.carbon is None
    assert "tracking unavailable" in measured.carbon_error


def test_codecarbon_stop_failure_is_reported(monkeypatch: pytest.MonkeyPatch):
    tracker = MagicMock()
    tracker.stop.side_effect = RuntimeError("stop broke")
    monkeypatch.setattr(measurement_service, "OfflineEmissionsTracker", lambda **kwargs: tracker)
    measured = measure_script_execution(b"print('ok')\n", 5)
    assert measured.run.success is True
    assert measured.carbon is None
    assert "stop broke" in measured.carbon_error


def test_tracker_is_stopped_when_script_runner_raises(monkeypatch: pytest.MonkeyPatch):
    tracker = MagicMock()
    monkeypatch.setattr(measurement_service, "OfflineEmissionsTracker", lambda **kwargs: tracker)

    def broken_run(source, timeout):
        raise OSError("cannot start")

    monkeypatch.setattr(measurement_service, "run_python_script", broken_run)
    with pytest.raises(OSError):
        measure_script_execution(b"print('x')\n", 5)
    tracker.stop.assert_called_once()


def test_execute_endpoint_reports_carbon_failure(client, monkeypatch: pytest.MonkeyPatch):
    from tests.conftest import upload

    def failing_tracker(**kwargs):
        raise RuntimeError("tracking unavailable")

    monkeypatch.setattr(measurement_service, "OfflineEmissionsTracker", failing_tracker)
    body = upload(client, "/execute", b"print('hello')\n").json()
    assert body["success"] is True
    assert body["carbon"] is None
    assert "tracking unavailable" in body["carbon_error"]


def _energy_rate(seconds: float) -> float:
    source = f"import time\nt = time.perf_counter()\nwhile time.perf_counter() - t < {seconds}:\n    pass\n"
    measured = measure_script_execution(source.encode(), 5)
    return measured.carbon.energy_kwh / measured.run.execution_time_seconds


def test_short_scripts_are_fully_measured():
    # CodeCarbon skips its final reading for windows under 50 ms unless we take
    # it ourselves. Energy per second must not collapse for short scripts.
    short_rate = _energy_rate(0.0)
    long_rate = _energy_rate(0.3)
    assert short_rate > long_rate / 3


def test_codecarbon_is_warmed_up_once(monkeypatch: pytest.MonkeyPatch):
    created = []
    real = measurement_service.OfflineEmissionsTracker

    def counting_tracker(**kwargs):
        created.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(measurement_service, "OfflineEmissionsTracker", counting_tracker)
    monkeypatch.setattr(measurement_service, "_warmed_up", False)
    measure_script_execution(b"pass\n", 5)
    assert len(created) == 2
    measure_script_execution(b"pass\n", 5)
    assert len(created) == 3
