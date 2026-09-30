from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    message: str
    llm_configured: bool


# Execution and carbon


class CarbonMetrics(BaseModel):
    energy_kwh: float
    co2_kg: float


class ExecuteResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int | None
    execution_time_seconds: float
    timed_out: bool = False
    carbon: CarbonMetrics | None = None
    carbon_error: str | None = None


# RAG


class RAGSearchRequest(BaseModel):
    query: str = Field(max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class PracticeResult(BaseModel):
    id: str
    title: str
    content: str
    category: str
    relevance_score: float


class RAGSearchResponse(BaseModel):
    query: str
    results: list[PracticeResult]


# Auditor


Severity = Literal["low", "medium", "high"]


class DetectedPattern(BaseModel):
    """A pattern found by deterministic AST analysis."""

    kind: str
    line_start: int
    line_end: int
    description: str


class AuditFinding(BaseModel):
    line_start: int
    line_end: int
    issue: str
    explanation: str
    severity: Severity
    green_practice: str
    suggestion: str


class AuditReport(BaseModel):
    """What the LLM auditor must return."""

    summary: str
    findings: list[AuditFinding]


class AuditResponse(AuditReport):
    detected_patterns: list[DetectedPattern]
    practices: list[PracticeResult]


# Optimizer


class OptimizationChange(BaseModel):
    finding: str
    description: str


class OptimizationResult(BaseModel):
    """What the LLM optimizer must return."""

    optimized_code: str
    explanation: str
    changes: list[OptimizationChange]


# Verifier


CheckStatus = Literal["passed", "failed", "skipped"]


class VerificationCheck(BaseModel):
    name: str
    status: CheckStatus
    detail: str


class VerificationResult(BaseModel):
    passed: bool
    checks: list[VerificationCheck]


# Comparison


class MeasurementSummary(BaseModel):
    execution_time_seconds: float
    energy_kwh: float | None
    co2_kg: float | None


MetricVerdict = Literal["lower", "higher", "no_clear_change", "unavailable"]


class MetricComparison(BaseModel):
    original: float | None
    optimized: float | None
    change_percent: float | None
    verdict: MetricVerdict


class ComparisonResult(BaseModel):
    runs_per_version: int
    original: MeasurementSummary
    optimized: MeasurementSummary
    execution_time: MetricComparison
    energy: MetricComparison
    co2: MetricComparison
    summary: str


# Full pipeline


class AnalyzeResponse(BaseModel):
    original_code: str
    original_execution: ExecuteResponse
    audit: AuditResponse | None = None
    optimization: OptimizationResult | None = None
    verification: VerificationResult | None = None
    optimized_execution: ExecuteResponse | None = None
    comparison: ComparisonResult | None = None
    diff: str | None = None
    stopped_reason: str | None = None
