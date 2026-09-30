"""The only place that talks to the LLM provider (Groq).

Services depend on the `LLMClient` protocol, so tests (and other providers)
can swap in a different implementation without touching the auditor or optimizer.
"""

import copy
from typing import Any, Protocol, TypeVar

import groq
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)

# Reasoning tokens count toward this limit, so leave plenty of room.
_MAX_COMPLETION_TOKENS = 32768


class LLMError(RuntimeError):
    """The LLM call failed or returned unusable output."""


class LLMNotConfiguredError(LLMError):
    pass


class LLMClient(Protocol):
    def generate(self, *, system: str, prompt: str, output_type: type[T]) -> T:
        """Return the model's answer parsed and validated as `output_type`."""
        ...


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic's JSON schema, adjusted for Groq strict mode: every object
    must set additionalProperties to false and list all its properties as required."""
    schema = copy.deepcopy(model.model_json_schema())

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(schema)
    return schema


class GroqLLMClient:
    def __init__(self, api_key: str, model: str, effort: str, timeout_seconds: float) -> None:
        self._client = groq.Groq(api_key=api_key, timeout=timeout_seconds)
        self._model = model
        self._effort = effort

    def generate(self, *, system: str, prompt: str, output_type: type[T]) -> T:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": output_type.__name__,
                        "strict": True,
                        "schema": strict_json_schema(output_type),
                    },
                },
                reasoning_effort=self._effort,
                include_reasoning=False,
                max_completion_tokens=_MAX_COMPLETION_TOKENS,
            )
        except groq.AuthenticationError as exc:
            raise LLMError("The LLM API key was rejected. Check GROQ_API_KEY.") from exc
        except groq.RateLimitError as exc:
            raise LLMError("The LLM provider is rate limiting requests. Try again shortly.") from exc
        except groq.BadRequestError as exc:
            if "json_validate_failed" in str(exc):
                raise LLMError("The model did not return output in the expected format.") from exc
            raise LLMError(f"The LLM request was rejected: {exc.message}") from exc
        except groq.APIStatusError as exc:
            raise LLMError(f"The LLM request failed ({exc.status_code}): {exc.message}") from exc
        except groq.APIConnectionError as exc:
            raise LLMError("Could not reach the LLM provider.") from exc

        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise LLMError("The model's answer was cut off. Try a smaller file.")
        try:
            return output_type.model_validate_json(choice.message.content or "")
        except ValidationError as exc:
            raise LLMError("The model did not return output in the expected format.") from exc


def get_llm_client() -> LLMClient:
    if not settings.groq_api_key:
        raise LLMNotConfiguredError(
            "The LLM is not configured. Set GROQ_API_KEY in backend/.env."
        )
    return GroqLLMClient(
        api_key=settings.groq_api_key,
        model=settings.llm_model,
        effort=settings.llm_effort,
        timeout_seconds=settings.llm_timeout_seconds,
    )
