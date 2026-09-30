import pytest

from app.config import settings
from app.main import app
from app.schemas import AuditReport, CarbonMetrics, OptimizationChange, OptimizationResult
from app.services.comparison_service import compare, compare_metric
from app.services.llm_service import LLMError, get_llm_client
from app.services.measurement_service import MeasuredRun
from app.services.rag_service import get_rag_service
from app.services.script_runner import ScriptRunResult
from tests.conftest import FakeLLM, FakeRAG, upload
from tests.test_auditor import finding

ORIGINAL = """\
allowed = list(range(2000))
hits = 0
for x in range(2000):
    if x in allowed:
        hits += 1
print(hits)
"""
OPTIMIZED = ORIGINAL.replace("allowed = list(range(2000))", "allowed = set(range(2000))")

AUDIT = AuditReport(summary="Linear search in a loop.", findings=[finding(line_start=4, line_end=4)])


def optimization(code: str) -> OptimizationResult:
    return OptimizationResult(
        optimized_code=code,
        explanation="Use a set for membership tests.",
        changes=[OptimizationChange(finding="Linear search", description="list -> set")],
    )


@pytest.fixture
def analyze(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "comparison_runs", 2)
    app.dependency_overrides[get_rag_service] = lambda: FakeRAG()

    def run(llm: FakeLLM, source: str = ORIGINAL):
        app.dependency_overrides[get_llm_client] = lambda: llm
        response = upload(client, "/analyze", source.encode())
        assert response.status_code == 200
        return response.json()

    return run


def test_full_pipeline_returns_both_measurements(analyze):
    body = analyze(FakeLLM({AuditReport: AUDIT, OptimizationResult: optimization(OPTIMIZED)}))

    assert body["stopped_reason"] is None
    assert body["original_code"] == ORIGINAL
    assert body["original_execution"]["stdout"] == "2000\n"
    assert body["audit"]["findings"][0]["line_start"] == 4
    assert body["optimization"]["optimized_code"] == OPTIMIZED
    assert "-allowed = list(range(2000))" in body["diff"]
    assert "+allowed = set(range(2000))" in body["diff"]
    assert body["verification"]["passed"] is True
    assert body["optimized_execution"]["stdout"] == "2000\n"

    comparison = body["comparison"]
    assert comparison["runs_per_version"] == 2
    for side in ("original", "optimized"):
        assert comparison[side]["execution_time_seconds"] > 0
        assert comparison[side]["energy_kwh"] > 0
        assert comparison[side]["co2_kg"] > 0
    for metric in ("execution_time", "energy", "co2"):
        assert comparison[metric]["verdict"] in ("lower", "higher", "no_clear_change")
    assert comparison["summary"]


def test_rejected_optimization_is_not_measured(analyze):
    wrong = OPTIMIZED.replace("print(hits)", "print(hits + 1)")
    body = analyze(FakeLLM({AuditReport: AUDIT, OptimizationResult: optimization(wrong)}))
    assert body["verification"]["passed"] is False
    assert body["optimized_execution"] is None
    assert body["comparison"] is None
    assert "rejected" in body["stopped_reason"]


def test_no_findings_stops_before_optimizer(analyze):
    llm = FakeLLM({AuditReport: AuditReport(summary="Looks efficient.", findings=[])})
    body = analyze(llm)
    assert body["original_execution"]["success"] is True
    assert body["audit"]["summary"] == "Looks efficient."
    assert body["optimization"] is None
    assert len(llm.calls) == 1


def test_failing_original_is_audited_but_not_optimized(analyze):
    body = analyze(FakeLLM({AuditReport: AUDIT}), source=ORIGINAL + "raise SystemExit(2)\n")
    assert body["original_execution"]["exit_code"] == 2
    assert body["audit"] is not None
    assert body["optimization"] is None
    assert "must run without errors" in body["stopped_reason"]


def test_syntax_error_is_reported(analyze):
    body = analyze(FakeLLM({}), source="def broken(:\n")
    assert body["original_execution"]["success"] is False
    assert "syntax error on line 1" in body["stopped_reason"]


def test_llm_failure_returns_partial_result(analyze):
    body = analyze(FakeLLM({AuditReport: AUDIT, OptimizationResult: LLMError("model down")}))
    assert body["audit"] is not None
    assert body["optimization"] is None
    assert "model down" in body["stopped_reason"]


def test_analyze_without_llm_key(client):
    response = upload(client, "/analyze", ORIGINAL.encode())
    assert response.status_code == 503


# Comparison logic, with fixed numbers


def measured(time: float, energy: float | None) -> MeasuredRun:
    run = ScriptRunResult(True, "", "", 0, time, False)
    carbon = CarbonMetrics(energy_kwh=energy, co2_kg=energy / 2) if energy is not None else None
    return MeasuredRun(run=run, carbon=carbon, carbon_error=None)


def test_comparison_uses_medians_and_honest_verdicts():
    result = compare(
        [measured(1.0, 10.0), measured(1.2, 12.0), measured(9.0, 90.0)],
        [measured(0.5, 11.9), measured(0.6, 11.5), measured(0.4, 11.8)],
    )
    assert result.original.execution_time_seconds == 1.2
    assert result.optimized.execution_time_seconds == 0.5
    assert result.execution_time.verdict == "lower"
    assert result.execution_time.change_percent == pytest.approx(-58.3)
    # 12.0 -> 11.8 is within the noise threshold, so no improvement is claimed.
    assert result.energy.verdict == "no_clear_change"
    assert "no clear change" in result.summary


@pytest.mark.parametrize(
    "original, optimized, verdict",
    [(10, 5, "lower"), (10, 15, "higher"), (10, 10.4, "no_clear_change"), (None, 5, "unavailable"), (0, 5, "unavailable")],
)
def test_metric_verdicts(original, optimized, verdict):
    assert compare_metric(original, optimized).verdict == verdict


def test_missing_carbon_makes_energy_unavailable():
    result = compare([measured(1.0, None)], [measured(0.5, 5.0)])
    assert result.energy.verdict == "unavailable"
    assert result.execution_time.verdict == "lower"
