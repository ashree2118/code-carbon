import pytest

from app.schemas import AuditResponse, OptimizationChange, OptimizationResult
from app.services.llm_service import LLMError
from app.services.optimizer import optimize_code
from tests.conftest import FakeLLM
from tests.test_auditor import SOURCE, finding

AUDIT = AuditResponse(summary="s", findings=[finding()], detected_patterns=[], practices=[])
OPTIMIZED = "print(''.join(words))\n"


def result(code: str) -> OptimizationResult:
    return OptimizationResult(
        optimized_code=code,
        explanation="Used str.join.",
        changes=[OptimizationChange(finding="String concatenation in a loop", description="Replaced += with join")],
    )


def test_returns_optimized_code_and_explanation():
    llm = FakeLLM({OptimizationResult: result(OPTIMIZED)})
    optimized = optimize_code(SOURCE, AUDIT, llm)
    assert optimized.optimized_code == OPTIMIZED
    assert optimized.explanation == "Used str.join."
    assert optimized.changes[0].finding == "String concatenation in a loop"

    prompt = llm.calls[0]["prompt"]
    assert SOURCE in prompt
    assert "String concatenation in a loop" in prompt


@pytest.mark.parametrize(
    "raw",
    ["```python\nprint(''.join(words))\n```", "```\nprint(''.join(words))```\n", "print(''.join(words))"],
)
def test_markdown_fences_and_missing_newline_are_normalized(raw: str):
    optimized = optimize_code(SOURCE, AUDIT, FakeLLM({OptimizationResult: result(raw)}))
    assert optimized.optimized_code == OPTIMIZED


def test_empty_code_is_rejected():
    with pytest.raises(LLMError, match="empty"):
        optimize_code(SOURCE, AUDIT, FakeLLM({OptimizationResult: result("```python\n```")}))


def test_no_findings_means_nothing_to_optimize():
    llm = FakeLLM({})
    with pytest.raises(ValueError):
        optimize_code(SOURCE, AUDIT.model_copy(update={"findings": []}), llm)
    assert llm.calls == []
