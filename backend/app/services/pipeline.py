"""The full flow as a LangGraph state graph:

    measure_original -> audit -> optimize -> verify -> measure_and_compare

Every node reads and updates one `AnalyzeResponse`. A node that cannot continue
sets `stopped_reason`, and the conditional edges then route straight to END,
so the caller always gets everything done so far and can show partial results.
"""

import difflib
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.schemas import AnalyzeResponse
from app.services.auditor import audit_code
from app.services.comparison_service import compare, measure_alternating
from app.services.llm_service import LLMClient, LLMError
from app.services.measurement_service import MeasuredRun, measure_script_execution
from app.services.optimizer import optimize_code
from app.services.rag_service import GreenCodingRAGService, RAGUnavailableError
from app.services.verifier import verify_optimization

NODES = ("measure_original", "audit", "optimize", "verify", "measure_and_compare")


class AnalysisState(TypedDict, total=False):
    source: str
    response: AnalyzeResponse
    original_run: MeasuredRun


def unified_diff(original: str, optimized: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            optimized.splitlines(keepends=True),
            "original.py",
            "optimized.py",
        )
    )


def build_analysis_graph(llm: LLMClient, rag: GreenCodingRAGService):
    timeout = settings.execution_timeout_seconds

    def measure_original(state: AnalysisState) -> AnalysisState:
        source = state["source"]
        original = measure_script_execution(source.encode("utf-8"), timeout)
        response = AnalyzeResponse(original_code=source, original_execution=original.to_response())
        return {"response": response, "original_run": original}

    def audit(state: AnalysisState) -> AnalysisState:
        response = state["response"]
        try:
            response.audit = audit_code(state["source"], llm, rag)
        except SyntaxError as exc:
            response.stopped_reason = (
                f"The code has a syntax error on line {exc.lineno}, so it cannot be analyzed."
            )
            return {"response": response}
        except (LLMError, RAGUnavailableError) as exc:
            response.stopped_reason = f"The audit failed: {exc}"
            return {"response": response}

        if not response.audit.findings:
            response.stopped_reason = "The auditor found nothing worth optimizing."
        elif not state["original_run"].run.success:
            response.stopped_reason = (
                f"The original code must run without errors within {timeout:g} seconds "
                "before an optimized version can be verified and measured."
            )
        return {"response": response}

    def optimize(state: AnalysisState) -> AnalysisState:
        response = state["response"]
        try:
            response.optimization = optimize_code(state["source"], response.audit, llm)
        except LLMError as exc:
            response.stopped_reason = f"The optimizer failed: {exc}"
            return {"response": response}
        response.diff = unified_diff(state["source"], response.optimization.optimized_code)
        return {"response": response}

    def verify(state: AnalysisState) -> AnalysisState:
        response = state["response"]
        response.verification = verify_optimization(
            state["source"], response.optimization.optimized_code, state["original_run"].run, timeout
        )
        if not response.verification.passed:
            response.stopped_reason = "The verifier rejected the optimized code, so it was not measured."
        return {"response": response}

    def measure_and_compare(state: AnalysisState) -> AnalysisState:
        response = state["response"]
        original_runs, optimized_runs = measure_alternating(
            state["source"].encode("utf-8"),
            response.optimization.optimized_code.encode("utf-8"),
            settings.comparison_runs,
            timeout,
        )
        response.optimized_execution = optimized_runs[0].to_response()
        if not all(r.run.success for r in original_runs + optimized_runs):
            response.stopped_reason = (
                "A measured run failed or timed out, so the measurements cannot be compared fairly."
            )
        else:
            response.comparison = compare(original_runs, optimized_runs)
        return {"response": response}

    def continue_to(next_node: str):
        def route(state: AnalysisState) -> str:
            return END if state["response"].stopped_reason else next_node

        return route

    graph = StateGraph(AnalysisState)
    for name, node in zip(NODES, (measure_original, audit, optimize, verify, measure_and_compare)):
        graph.add_node(name, node)
    graph.add_edge(START, "measure_original")
    graph.add_edge("measure_original", "audit")
    graph.add_conditional_edges("audit", continue_to("optimize"), ["optimize", END])
    graph.add_conditional_edges("optimize", continue_to("verify"), ["verify", END])
    graph.add_conditional_edges("verify", continue_to("measure_and_compare"), ["measure_and_compare", END])
    graph.add_edge("measure_and_compare", END)
    return graph.compile()


def run_analysis(source: str, llm: LLMClient, rag: GreenCodingRAGService) -> AnalyzeResponse:
    final_state = build_analysis_graph(llm, rag).invoke({"source": source})
    return final_state["response"]
