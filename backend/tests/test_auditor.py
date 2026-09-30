import pytest

from app.main import app
from app.schemas import AuditFinding, AuditReport, PracticeResult
from app.services import auditor
from app.services.auditor import GENERAL_QUERY, audit_code, retrieve_practices
from app.services.ast_analyzer import PATTERN_QUERIES
from app.services.llm_service import LLMError, get_llm_client
from app.services.rag_service import RAGUnavailableError, get_rag_service
from tests.conftest import FakeLLM, FakeRAG, upload

SOURCE = "result = ''\nfor word in words:\n    result += word\nprint(result)\n"


def finding(**overrides) -> AuditFinding:
    data = dict(
        line_start=2,
        line_end=3,
        issue="String concatenation in a loop",
        explanation="Each += copies the string.",
        severity="medium",
        green_practice="Build Strings with str.join",
        suggestion="Collect words and use ''.join().",
    )
    return AuditFinding(**{**data, **overrides})


def practice(pid: str, score: float) -> PracticeResult:
    return PracticeResult(id=pid, title=f"Practice {pid}", content="c", category="cat", relevance_score=score)


def test_audit_combines_ast_rag_and_llm():
    llm = FakeLLM({AuditReport: AuditReport(summary="One issue.", findings=[finding()])})
    rag = FakeRAG(results=[practice("GCP-005", 0.8)])

    result = audit_code(SOURCE, llm, rag)

    assert result.summary == "One issue."
    assert result.findings == [finding()]
    assert [p.kind for p in result.detected_patterns] == ["string_concat_in_loop"]
    assert rag.queries == [PATTERN_QUERIES["string_concat_in_loop"]]
    assert [p.id for p in result.practices] == ["GCP-005"]

    # The LLM sees numbered code, the AST patterns, and the retrieved practices.
    prompt = llm.calls[0]["prompt"]
    assert "   3 |     result += word" in prompt
    assert "string_concat_in_loop" in prompt
    assert "Practice GCP-005" in prompt
    assert llm.calls[0]["output_type"] is AuditReport


def test_findings_outside_the_file_are_dropped_and_ranges_fixed():
    findings = [finding(line_start=40, line_end=41), finding(line_start=3, line_end=2), finding(line_start=4, line_end=99)]
    llm = FakeLLM({AuditReport: AuditReport(summary="s", findings=findings)})
    result = audit_code(SOURCE, llm, FakeRAG())
    assert [(f.line_start, f.line_end) for f in result.findings] == [(2, 3), (4, 4)]


def test_practices_are_deduplicated_and_ranked():
    class PerQueryRAG(FakeRAG):
        def search(self, query, top_k=None):
            self.queries.append(query)
            return [practice("A", 0.5), practice("B", 0.9)] if len(self.queries) == 1 else [practice("A", 0.7)]

    patterns = auditor.analyze_code("for a in xs:\n    for b in ys:\n        s = sorted(data)\n")
    rag = PerQueryRAG()
    practices = retrieve_practices(patterns, rag)
    assert len(rag.queries) == 2
    assert [(p.id, p.relevance_score) for p in practices] == [("B", 0.9), ("A", 0.7)]


def test_general_query_when_no_patterns():
    rag = FakeRAG()
    retrieve_practices([], rag)
    assert rag.queries == [GENERAL_QUERY]


def test_audit_never_executes_code(monkeypatch: pytest.MonkeyPatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("code must not run during audit")

    monkeypatch.setattr("app.services.script_runner.run_python_script", forbidden)
    monkeypatch.setattr("app.services.measurement_service.run_python_script", forbidden)
    llm = FakeLLM({AuditReport: AuditReport(summary="s", findings=[])})
    audit_code("import os\nos.remove('important')\n", llm, FakeRAG())


# Endpoint


def test_audit_endpoint_returns_structured_audit(client):
    llm = FakeLLM({AuditReport: AuditReport(summary="One issue.", findings=[finding()])})
    app.dependency_overrides[get_llm_client] = lambda: llm
    app.dependency_overrides[get_rag_service] = lambda: FakeRAG(results=[practice("GCP-005", 0.8)])

    response = upload(client, "/audit", SOURCE.encode())
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "One issue."
    assert body["findings"][0] == finding().model_dump()
    assert body["detected_patterns"][0]["kind"] == "string_concat_in_loop"
    assert body["practices"][0]["id"] == "GCP-005"


def test_audit_endpoint_without_llm_key(client):
    app.dependency_overrides[get_rag_service] = lambda: FakeRAG()
    response = upload(client, "/audit", SOURCE.encode())
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


@pytest.mark.parametrize(
    "source, llm_response, rag_error, status",
    [
        (b"def broken(:\n", None, None, 400),
        (SOURCE.encode(), LLMError("model down"), None, 502),
        (SOURCE.encode(), None, RAGUnavailableError("store down"), 503),
    ],
)
def test_audit_endpoint_errors(client, source, llm_response, rag_error, status):
    llm = FakeLLM({AuditReport: llm_response or AuditReport(summary="s", findings=[])})
    app.dependency_overrides[get_llm_client] = lambda: llm
    app.dependency_overrides[get_rag_service] = lambda: FakeRAG(error=rag_error)
    assert upload(client, "/audit", source).status_code == status
