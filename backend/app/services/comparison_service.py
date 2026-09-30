"""Compare original and optimized code using real measurements.

Both versions go through the same measurement service. Runs alternate
(original, optimized, original, ...) so slow drifts in machine load affect both
sides equally, and the median of each side is compared. A difference smaller
than NOISE_THRESHOLD_PERCENT is reported as "no clear change", because single
short runs are noisy.
"""

from statistics import median

from app.schemas import ComparisonResult, MeasurementSummary, MetricComparison
from app.services.measurement_service import MeasuredRun, measure_script_execution

NOISE_THRESHOLD_PERCENT = 5.0


def measure_alternating(
    original: bytes, optimized: bytes, runs: int, timeout_seconds: float
) -> tuple[list[MeasuredRun], list[MeasuredRun]]:
    original_runs: list[MeasuredRun] = []
    optimized_runs: list[MeasuredRun] = []
    for _ in range(max(runs, 1)):
        original_runs.append(measure_script_execution(original, timeout_seconds))
        optimized_runs.append(measure_script_execution(optimized, timeout_seconds))
    return original_runs, optimized_runs


def summarize(runs: list[MeasuredRun]) -> MeasurementSummary:
    carbon = [r.carbon for r in runs]
    have_carbon = all(c is not None for c in carbon)
    return MeasurementSummary(
        execution_time_seconds=round(median(r.run.execution_time_seconds for r in runs), 4),
        energy_kwh=median(c.energy_kwh for c in carbon) if have_carbon else None,
        co2_kg=median(c.co2_kg for c in carbon) if have_carbon else None,
    )


def compare_metric(original: float | None, optimized: float | None) -> MetricComparison:
    if original is None or optimized is None or original <= 0:
        return MetricComparison(original=original, optimized=optimized, change_percent=None, verdict="unavailable")
    change = (optimized - original) / original * 100
    if abs(change) < NOISE_THRESHOLD_PERCENT:
        verdict = "no_clear_change"
    else:
        verdict = "lower" if change < 0 else "higher"
    return MetricComparison(
        original=original, optimized=optimized, change_percent=round(change, 1), verdict=verdict
    )


def _describe(label: str, metric: MetricComparison, lower_word: str, higher_word: str) -> str:
    if metric.verdict == "unavailable":
        return f"{label} was not available"
    if metric.verdict == "no_clear_change":
        return f"{label} showed no clear change (within {NOISE_THRESHOLD_PERCENT:g}%)"
    word = lower_word if metric.verdict == "lower" else higher_word
    return f"{label} was {abs(metric.change_percent or 0):g}% {word}"


def compare(original_runs: list[MeasuredRun], optimized_runs: list[MeasuredRun]) -> ComparisonResult:
    original = summarize(original_runs)
    optimized = summarize(optimized_runs)
    time = compare_metric(original.execution_time_seconds, optimized.execution_time_seconds)
    energy = compare_metric(original.energy_kwh, optimized.energy_kwh)
    co2 = compare_metric(original.co2_kg, optimized.co2_kg)

    parts = [
        _describe("Energy use", energy, "lower", "higher"),
        _describe("CO2", co2, "lower", "higher"),
        _describe("Run time", time, "shorter", "longer"),
    ]
    summary = (
        f"Median of {len(original_runs)} measured run(s) per version: " + "; ".join(parts) + "."
    )
    return ComparisonResult(
        runs_per_version=len(original_runs),
        original=original,
        optimized=optimized,
        execution_time=time,
        energy=energy,
        co2=co2,
        summary=summary,
    )
