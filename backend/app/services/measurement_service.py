"""Measure the energy and CO2 of running a script, using CodeCarbon.

The tracker runs only around the subprocess, so request parsing and response
handling are not counted. CodeCarbon measures the whole machine (CPU, RAM, GPU),
so runs are serialized with a lock: two scripts measured at the same time would
count each other's energy.
"""

import logging
import threading
from dataclasses import dataclass

import codecarbon.emissions_tracker as _cc_tracker_module
from codecarbon import OfflineEmissionsTracker

from app.config import settings
from app.schemas import CarbonMetrics, ExecuteResponse
from app.services.script_runner import (
    ScriptRunResult,
    execution_lock,
    prepare_sandbox,
    run_python_script,
)

logger = logging.getLogger(__name__)

_measurement_lock = threading.Lock()
_warmed_up = False


def _install_safe_physical_cpu_count() -> None:
    """CodeCarbon 3.3.1 counts CPU sockets on Windows by launching `powershell`
    and only handles some of the errors that can raise. When PowerShell is not on
    PATH it raises FileNotFoundError inside start(), whose @suppress decorator
    swallows it: the tracker never starts and every run reports no carbon data.
    Fall back to one socket, the same value CodeCarbon uses for its other errors.
    """
    original = _cc_tracker_module.count_physical_cpus
    if getattr(original, "_cfo_safe", False):
        return

    warned = False

    def safe_count_physical_cpus() -> int:
        nonlocal warned
        try:
            return original()
        except Exception as exc:
            if not warned:
                logger.warning("Could not count physical CPUs (%s); assuming 1", exc)
                warned = True
            return 1

    safe_count_physical_cpus._cfo_safe = True  # type: ignore[attr-defined]
    _cc_tracker_module.count_physical_cpus = safe_count_physical_cpus


_install_safe_physical_cpu_count()


@dataclass
class MeasuredRun:
    run: ScriptRunResult
    carbon: CarbonMetrics | None
    carbon_error: str | None

    def to_response(self) -> ExecuteResponse:
        return ExecuteResponse(
            success=self.run.success,
            stdout=self.run.stdout,
            stderr=self.run.stderr,
            exit_code=self.run.exit_code,
            execution_time_seconds=self.run.execution_time_seconds,
            timed_out=self.run.timed_out,
            carbon=self.carbon,
            carbon_error=self.carbon_error,
        )


def _start_tracker() -> tuple[OfflineEmissionsTracker | None, str | None]:
    try:
        tracker = OfflineEmissionsTracker(
            project_name="uploaded_script",
            country_iso_code=settings.codecarbon_country_iso_code,
            measure_power_secs=settings.codecarbon_measure_power_secs,
            output_methods=[],  # keep results in memory only; no emissions.csv
            log_level="error",
            # We already serialize measurements with our own lock. CodeCarbon's
            # lock file adds nothing, and a stale one (left by a killed server
            # process) would make every later measurement silently return nothing.
            allow_multiple_runs=True,
        )
        tracker.start()
        # start() is wrapped in @suppress(Exception) and fails silently, so
        # check that it really started instead of finding out at stop().
        if getattr(tracker, "_start_time", None) is None:
            return None, "CodeCarbon could not start tracking (see server logs)"
        return tracker, None
    except Exception as exc:
        logger.warning("Could not start CodeCarbon tracker: %s", exc)
        return None, f"CodeCarbon could not start: {exc}"


def _stop_tracker(tracker: OfflineEmissionsTracker) -> tuple[CarbonMetrics | None, str | None]:
    try:
        # CodeCarbon 3.x skips its final power reading in stop() when the last
        # reading is under 50 ms old, so scripts shorter than that were counted
        # as almost free. Take the final reading here so the whole run counts.
        tracker._measure_power_and_energy()
        tracker.stop()
        data = getattr(tracker, "final_emissions_data", None)
        if data is None:
            return None, "CodeCarbon returned no data"
        return (
            CarbonMetrics(energy_kwh=float(data.energy_consumed), co2_kg=float(data.emissions)),
            None,
        )
    except Exception as exc:
        logger.warning("Could not stop CodeCarbon tracker: %s", exc)
        return None, f"CodeCarbon could not finish the measurement: {exc}"


def _warm_up() -> None:
    """The first tracker in a process spends ~150 ms on setup after start(),
    which would otherwise be counted as part of the first measured script."""
    global _warmed_up
    if not _warmed_up:
        tracker, _ = _start_tracker()
        if tracker is not None:
            _stop_tracker(tracker)
        _warmed_up = True


def measure_script_execution(source: bytes, timeout_seconds: float) -> MeasuredRun:
    """Raises SandboxUnavailableError if the configured sandbox cannot run scripts."""
    with _measurement_lock, execution_lock:
        # Start the sandbox container (if any) before tracking begins, so its
        # startup is not counted as the script's energy.
        prepare_sandbox()
        _warm_up()
        carbon: CarbonMetrics | None = None
        tracker, carbon_error = _start_tracker()
        try:
            run = run_python_script(source, timeout_seconds)
        finally:
            if tracker is not None:
                carbon, carbon_error = _stop_tracker(tracker)
    return MeasuredRun(run=run, carbon=carbon, carbon_error=carbon_error)
