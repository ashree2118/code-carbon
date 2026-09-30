import json

import groq
import httpx
import pytest

from app.config import settings
from app.schemas import AuditReport
from app.services.llm_service import (
    GroqLLMClient,
    LLMError,
    LLMNotConfiguredError,
    get_llm_client,
    strict_json_schema,
)

AUDIT = {"summary": "One issue.", "findings": []}


def make_client(handler) -> tuple[GroqLLMClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    llm = GroqLLMClient(api_key="test-key", model="openai/gpt-oss-120b", effort="high", timeout_seconds=10)
    llm._client = groq.Groq(
        api_key="test-key", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(record))
    )
    return llm, requests


def completion(content: str | None, finish_reason: str = "stop") -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "openai/gpt-oss-120b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


def error(status: int, message: str, code: str | None = None) -> httpx.Response:
    body = {"error": {"message": message, "type": "invalid_request_error", "code": code}}
    return httpx.Response(status, json=body)


def test_request_shape_and_parsed_output():
    llm, requests = make_client(lambda r: httpx.Response(200, json=completion(json.dumps(AUDIT))))
    result = llm.generate(system="sys", prompt="audit this", output_type=AuditReport)

    assert result == AuditReport(**AUDIT)
    body = json.loads(requests[0].content)
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "audit this"},
    ]
    assert body["reasoning_effort"] == "high"
    assert body["include_reasoning"] is False
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "AuditReport"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == strict_json_schema(AuditReport)


def test_strict_schema_closes_every_object():
    schema = strict_json_schema(AuditReport)
    objects = [schema, *schema["$defs"].values()]
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])


@pytest.mark.parametrize(
    "response, message",
    [
        (httpx.Response(200, json=completion('{"summary": "cut', finish_reason="length")), "cut off"),
        (httpx.Response(200, json=completion('{"summary": 1}')), "expected format"),
        (httpx.Response(200, json=completion(None)), "expected format"),
        (error(400, "Generated JSON does not match the schema", "json_validate_failed"), "expected format"),
        (error(400, "model does not support json_schema"), "rejected"),
        (error(401, "Invalid API Key", "invalid_api_key"), "GROQ_API_KEY"),
        (error(429, "Rate limit reached", "rate_limit_exceeded"), "rate limiting"),
        (error(500, "boom"), "500"),
    ],
)
def test_failures_become_llm_errors(response: httpx.Response, message: str):
    llm, _ = make_client(lambda r: response)
    with pytest.raises(LLMError, match=message):
        llm.generate(system="s", prompt="p", output_type=AuditReport)


def test_connection_failure_becomes_llm_error():
    def fail(request):
        raise httpx.ConnectError("offline")

    llm, _ = make_client(fail)
    with pytest.raises(LLMError, match="reach"):
        llm.generate(system="s", prompt="p", output_type=AuditReport)


def test_missing_api_key_is_reported(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(LLMNotConfiguredError, match="GROQ_API_KEY"):
        get_llm_client()
    monkeypatch.setattr(settings, "groq_api_key", "k")
    monkeypatch.setattr(settings, "llm_model", "openai/gpt-oss-20b")
    assert get_llm_client()._model == "openai/gpt-oss-20b"
