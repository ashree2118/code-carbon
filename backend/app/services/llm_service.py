"""The only place that talks to the LLM provider.

Services depend on the `LLMClient` protocol, so tests (and other providers)
can swap in a different implementation without touching the auditor or optimizer.
"""

from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)

_MAX_TOKENS = 16000


class LLMError(RuntimeError):
    """The LLM call failed or returned unusable output."""


class LLMNotConfiguredError(LLMError):
    pass


class LLMClient(Protocol):
    def generate(self, *, system: str, prompt: str, output_type: type[T]) -> T:
        """Return the model's answer parsed and validated as `output_type`."""
        ...


class AnthropicLLMClient:
    def __init__(self, api_key: str, model: str, effort: str, timeout_seconds: float) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds)
        self._model = model
        self._effort = effort

    def generate(self, *, system: str, prompt: str, output_type: type[T]) -> T:
        output_format = {
            "type": "json_schema",
            "schema": anthropic.transform_schema(output_type.model_json_schema()),
        }
        try:
            # `create` rather than `parse`: `parse` validates before we can check
            # stop_reason, which turns refusals into confusing validation errors.
            response = self._client.beta.messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
                output_config={"effort": self._effort, "format": output_format},
                # If the model declines, the API retries on a fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("The LLM API key was rejected. Check ANTHROPIC_API_KEY.") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("The LLM provider is rate limiting requests. Try again shortly.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"The LLM request failed ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the LLM provider.") from exc

        if response.stop_reason == "refusal":
            raise LLMError("The model declined to answer this request.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The model's answer was cut off. Try a smaller file.")
        text = "".join(block.text for block in response.content if block.type == "text")
        try:
            return output_type.model_validate_json(text)
        except ValidationError as exc:
            raise LLMError("The model did not return output in the expected format.") from exc


def get_llm_client() -> LLMClient:
    if not settings.anthropic_api_key:
        raise LLMNotConfiguredError(
            "The LLM is not configured. Set ANTHROPIC_API_KEY in backend/.env."
        )
    return AnthropicLLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
        effort=settings.llm_effort,
        timeout_seconds=settings.llm_timeout_seconds,
    )
