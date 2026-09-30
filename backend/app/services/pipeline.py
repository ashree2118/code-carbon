"""The full flow: run and measure -> audit -> optimize -> verify -> measure -> compare.

Each step can stop the flow. The response always contains everything done so
far plus `stopped_reason`, so the caller can show partial results.
"""

import difflib

from app.config import settings
from app.schemas import AnalyzeResponse
from app.services.auditor import audit_code
from app.services.comparison_service import compare, measure_alternating
from app.services.llm_service import LLMClient, LLMError
from app.services.measurement_service import measure_script_execution
from app.services.optimizer import optimize_code
from app.services.rag_service import GreenCodingRAGService, RAGUnavailableError
from app.services.verifier import verify_optimization


def unified_diff(original: str, optimized: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            optimized.splitlines(keepends=True),
            "original.py",
            "optimized.py",
        )
    )


def run_analysis(source: str, llm: LLMClient, rag: GreenCodingRAGService) -> AnalyzeResponse:
    timeout = settings.execution_timeout_seconds

    original = measure_script_execution(source.encode("utf-8"), timeout)
    response = AnalyzeResponse(original_code=source, original_execution=original.to_response())

    try:
        response.audit = audit_code(source, llm, rag)
    except SyntaxError as exc:
        response.stopped_reason = f"The code has a syntax error on line {exc.lineno}, so it cannot be analyzed."
        return response
    except (LLMError, RAGUnavailableError) as exc:
        response.stopped_reason = f"The audit failed: {exc}"
        return response

    if not response.audit.findings:
        response.stopped_reason = "The auditor found nothing worth optimizing."
        return response
    if not original.run.success:
        response.stopped_reason = (
            f"The original code must run without errors within {timeout:g} seconds "
            "before an optimized version can be verified and measured."
        )
        return response

    try:
        response.optimization = optimize_code(source, response.audit, llm)
    except LLMError as exc:
        response.stopped_reason = f"The optimizer failed: {exc}"
        return response
    optimized_source = response.optimization.optimized_code
    response.diff = unified_diff(source, optimized_source)

    response.verification = verify_optimization(source, optimized_source, original.run, timeout)
    if not response.verification.passed:
        response.stopped_reason = "The verifier rejected the optimized code, so it was not measured."
        return response

    original_runs, optimized_runs = measure_alternating(
        source.encode("utf-8"), optimized_source.encode("utf-8"), settings.comparison_runs, timeout
    )
    response.optimized_execution = optimized_runs[0].to_response()
    if not all(r.run.success for r in original_runs + optimized_runs):
        response.stopped_reason = (
            "A measured run failed or timed out, so the measurements cannot be compared fairly."
        )
        return response

    response.comparison = compare(original_runs, optimized_runs)
    return response
