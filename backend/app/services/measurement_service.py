import logging
from typing import Tuple

from codecarbon import EmissionsTracker

from app.schemas import CarbonMetrics
from app.services.script_runner import ScriptRunResult, run_python_script

logger = logging.getLogger(__name__)


def measure_script_execution(
    source: bytes, timeout_seconds: float
) -> Tuple[ScriptRunResult, CarbonMetrics | None]:
    """
    Executes an uploaded script via subprocess (isolated execution) and measures
    its energy consumption (kWh) and CO2 emissions (kg) using CodeCarbon.

    CodeCarbon tracker ONLY measures during the subprocess execution, excluding
    FastAPI request parsing and HTTP response overhead.
    """
    tracker = None
    try:
        tracker = EmissionsTracker(
            project_name="uploaded_script",
            save_to_file=False,
            log_level="warning",
        )
        tracker.start()
    except Exception as exc:
        logger.warning("Failed to start CodeCarbon tracker: %s", exc)
        tracker = None

    try:
        result = run_python_script(source, timeout_seconds)
    finally:
        carbon = None
        if tracker is not None:
            try:
                emissions_kg = tracker.stop()

                energy_kwh: float | None = None
                co2_kg: float | None = (
                    float(emissions_kg) if isinstance(emissions_kg, (int, float)) else None
                )

                final_data = getattr(tracker, "final_emissions_data", None)
                if final_data is not None:
                    if getattr(final_data, "energy_consumed", None) is not None:
                        energy_kwh = float(final_data.energy_consumed)
                    if getattr(final_data, "emissions", None) is not None:
                        co2_kg = float(final_data.emissions)

                if energy_kwh is None and hasattr(tracker, "_total_energy"):
                    total_energy = getattr(tracker, "_total_energy")
                    if hasattr(total_energy, "kWh") and total_energy.kWh is not None:
                        energy_kwh = float(total_energy.kWh)

                if energy_kwh is not None or co2_kg is not None:
                    carbon = CarbonMetrics(
                        energy_kwh=energy_kwh,
                        co2_kg=co2_kg,
                    )
            except Exception as exc:
                logger.warning("Failed to stop CodeCarbon tracker or extract metrics: %s", exc)
                carbon = None

    return result, carbon
