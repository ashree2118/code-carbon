"""Verifier: "Did we improve it safely?"

Rejects optimized code unless it changed, compiles, runs without errors inside
the timeout, and prints the same stdout as the original. Uses the same script
runner as everything else, so optimized code never runs in the API process.
"""

import difflib

from app.schemas import VerificationCheck, VerificationResult
from app.services.script_runner import ScriptRunResult, run_python_script

CHECK_NAMES = ("changed", "syntax", "runs", "output_matches")


def _first_difference(expected: str, actual: str) -> str:
    diff = difflib.unified_diff(
        expected.splitlines(), actual.splitlines(), "original", "optimized", n=0, lineterm=""
    )
    lines = [line for line in diff if not line.startswith(("---", "+++", "@@"))]
    return "\n".join(lines[:6])


def _tail(text: str, lines: int = 8) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def _check_output(
    original_source: str,
    original_run: ScriptRunResult,
    optimized_run: ScriptRunResult,
    timeout_seconds: float,
) -> VerificationCheck:
    if not original_run.success:
        return VerificationCheck(
            name="output_matches",
            status="skipped",
            detail="The original did not run successfully, so there is no output to compare.",
        )
    if optimized_run.stdout == original_run.stdout:
        return VerificationCheck(
            name="output_matches", status="passed", detail="stdout is identical to the original."
        )

    # Outputs differ. Run the original again to see if its own output is stable.
    rerun = run_python_script(original_source.encode("utf-8"), timeout_seconds)
    if rerun.stdout != original_run.stdout:
        return VerificationCheck(
            name="output_matches",
            status="skipped",
            detail="The original prints different output on each run (for example random "
            "values or timestamps), so outputs cannot be compared.",
        )
    return VerificationCheck(
        name="output_matches",
        status="failed",
        detail="stdout differs from the original:\n"
        + _first_difference(original_run.stdout, optimized_run.stdout),
    )


def verify_optimization(
    original_source: str,
    optimized_source: str,
    original_run: ScriptRunResult,
    timeout_seconds: float,
) -> VerificationResult:
    checks: list[VerificationCheck] = []

    def result() -> VerificationResult:
        done = {c.name for c in checks}
        for name in CHECK_NAMES:
            if name not in done:
                checks.append(
                    VerificationCheck(name=name, status="skipped", detail="Not run because an earlier check failed.")
                )
        return VerificationResult(passed=all(c.status != "failed" for c in checks), checks=checks)

    if optimized_source.strip() == original_source.strip():
        checks.append(VerificationCheck(name="changed", status="failed", detail="The optimized code is identical to the original."))
        return result()
    checks.append(VerificationCheck(name="changed", status="passed", detail="The code was changed."))

    try:
        compile(optimized_source, "optimized.py", "exec")
    except (SyntaxError, ValueError) as exc:
        line = getattr(exc, "lineno", None)
        where = f" on line {line}" if line else ""
        checks.append(VerificationCheck(name="syntax", status="failed", detail=f"Invalid Python{where}: {exc}"))
        return result()
    checks.append(VerificationCheck(name="syntax", status="passed", detail="The code compiles."))

    optimized_run = run_python_script(optimized_source.encode("utf-8"), timeout_seconds)
    if optimized_run.timed_out:
        checks.append(VerificationCheck(name="runs", status="failed", detail=f"Timed out after {timeout_seconds} seconds."))
        return result()
    if optimized_run.exit_code != 0:
        checks.append(
            VerificationCheck(
                name="runs",
                status="failed",
                detail=f"Exited with code {optimized_run.exit_code}:\n{_tail(optimized_run.stderr)}",
            )
        )
        return result()
    checks.append(VerificationCheck(name="runs", status="passed", detail="Ran without errors."))

    checks.append(_check_output(original_source, original_run, optimized_run, timeout_seconds))
    return result()
