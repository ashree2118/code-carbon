from app.services.script_runner import run_python_script
from app.services.verifier import verify_optimization

ORIGINAL = "out = ''\nfor i in range(5):\n    out += str(i)\nprint(out)\n"
GOOD = "print(''.join(str(i) for i in range(5)))\n"


def verify(optimized: str, original: str = ORIGINAL, timeout: float = 5):
    original_run = run_python_script(original.encode(), timeout)
    result = verify_optimization(original, optimized, original_run, timeout)
    return result, {c.name: c for c in result.checks}


def test_valid_optimization_is_accepted():
    result, checks = verify(GOOD)
    assert result.passed is True
    assert [c.status for c in result.checks] == ["passed"] * 4


def test_invalid_syntax_is_rejected():
    result, checks = verify("print(''.join(str(i) for i in range(5))\n")
    assert result.passed is False
    assert checks["syntax"].status == "failed"
    assert checks["runs"].status == "skipped"


def test_runtime_error_is_rejected():
    result, checks = verify("print(''.join(i for i in range(5)))\n")
    assert result.passed is False
    assert checks["runs"].status == "failed"
    assert "TypeError" in checks["runs"].detail


def test_timeout_is_rejected():
    result, checks = verify("while True:\n    pass\n", timeout=0.3)
    assert result.passed is False
    assert "Timed out" in checks["runs"].detail


def test_different_output_is_rejected():
    result, checks = verify("print('01235')\n")
    assert result.passed is False
    assert checks["output_matches"].status == "failed"
    assert "-01234" in checks["output_matches"].detail
    assert "+01235" in checks["output_matches"].detail


def test_unchanged_code_is_rejected():
    result, checks = verify(ORIGINAL + "\n")
    assert result.passed is False
    assert checks["changed"].status == "failed"


def test_nondeterministic_original_skips_output_check():
    original = "import random\nprint(random.random())\n"
    result, checks = verify("import random\nprint(random.random() * 1)\n", original=original)
    assert result.passed is True
    assert checks["output_matches"].status == "skipped"
