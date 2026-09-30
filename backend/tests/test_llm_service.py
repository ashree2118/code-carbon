import json

import anthropic
import httpx2 as httpx
import pytest

from app.config import settings
from app.schemas import AuditReport
from app.services.llm_service import (
    AnthropicLLMClient,
    LLMError,
    LLMNotConfiguredError,
    get_llm_client,
)

AUDIT = {"summary": "One issue.", "findings": []}


def make_client(handler) -> tuple[AnthropicLLMClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    llm = AnthropicLLMClient(api_key="test-key", model="claude-opus-5-5", effort="high", timeout_seconds=10)
    llm._client = anthropic.Anthropic(
        api_key="test-key", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(record))
    )
    return llm, requests


def message(text: str, stop_reason: str = "end_turn") -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def test_request_shape_and_parsed_output():
    llm, requests = make_client(lambda r: httpx.Response(200, json=message(json.dumps(AUDIT))))
    result = llm.generate(system="sys", prompt="audit this", output_type=AuditReport)

    assert result == AuditReport(**AUDIT)
    body = json.loads(requests[0].content)
    assert body["model"] == "claude-opus-5-5"
    assert body["system"] == "sys"
    assert body["messages"] == [{"role": "user", "content": "audit this"}]
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"]["effort"] == "high"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in requests[0].headers["anthropic-beta"]


@pytest.mark.parametrize(
    "response, error",
    [
        (httpx.Response(200, json=message("", stop_reason="refusal")), "declined"),
        (httpx.Response(200, json=message('{"summary": "cut', stop_reason="max_tokens")), "cut off"),
        (httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "bad"}}), "API key"),
        (httpx.Response(429, json={"type": "error", "error": {"type": "rate_limit_error", "message": "slow"}}), "rate limiting"),
        (httpx.Response(500, json={"type": "error", "error": {"type": "api_error", "message": "boom"}}), "500"),
    ],
)
def test_failures_become_llm_errors(response: httpx.Response, error: str):
    llm, _ = make_client(lambda r: response)
    with pytest.raises(LLMError, match=error):
        llm.generate(system="s", prompt="p", output_type=AuditReport)


def test_connection_failure_becomes_llm_error():
    def fail(request):
        raise httpx.ConnectError("offline")

    llm, _ = make_client(fail)
    with pytest.raises(LLMError, match="reach"):
        llm.generate(system="s", prompt="p", output_type=AuditReport)


def test_missing_api_key_is_reported(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(LLMNotConfiguredError):
        get_llm_client()
    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    monkeypatch.setattr(settings, "llm_model", "claude-sonnet-5-5")
    assert get_llm_client()._model == "claude-sonnet-5-5"


def test_output_not_matching_schema_becomes_llm_error():
    llm, _ = make_client(lambda r: httpx.Response(200, json=message('{"summary": 1}')))
    with pytest.raises(LLMError, match="expected format"):
        llm.generate(system="s", prompt="p", output_type=AuditReport)
