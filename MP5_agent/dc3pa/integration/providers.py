from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..reliability.contracts import ConfidenceRequest
from ..reliability.model import build_verbal_confidence_prompt


TRACK_E_MAX_OUTPUT_TOKENS = 2048
TRACK_E_TIMEOUT_SECONDS = 60


def configure_track_e_chat_model(model: Any) -> Any:
    """Return an isolated model copy with the E3 Track-E request budget."""

    model_copy = getattr(model, "copy", None)
    if callable(model_copy):
        try:
            configured = model_copy(deep=False)
        except TypeError:
            configured = copy.copy(model)
    else:
        configured = copy.copy(model)

    required = {
        "temperature": 0,
        "max_tokens": TRACK_E_MAX_OUTPUT_TOKENS,
        "request_timeout": TRACK_E_TIMEOUT_SECONDS,
        "max_retries": 0,
    }
    for name, value in required.items():
        if not hasattr(configured, name):
            raise TypeError(f"Track-E chat model does not expose {name}")
        setattr(configured, name, value)
        if getattr(configured, name) != value:
            raise ValueError(f"Track-E chat model did not apply {name}")
    return configured


def extract_text_response(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, Mapping):
        for key in ("content", "text", "output", "response"):
            value = response.get(key)
            if value is not None:
                return str(value)
    content = getattr(response, "content", None)
    if content is not None:
        return str(content)
    text = getattr(response, "text", None)
    if text is not None:
        return str(text)
    raise TypeError(
        f"Chat model response {type(response).__name__} has no textual content"
    )


@dataclass
class ChatModelTextAdapter:
    """Small vendor-neutral adapter for LangChain-style or callable chat models."""

    model: Any
    request_kwargs: Mapping[str, Any] | None = None

    def complete(self, prompt: str) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        request_kwargs = dict(self.request_kwargs or {})
        if hasattr(self.model, "invoke"):
            return extract_text_response(self.model.invoke(prompt, **request_kwargs))
        if hasattr(self.model, "predict"):
            return extract_text_response(self.model.predict(prompt, **request_kwargs))
        if callable(self.model):
            return extract_text_response(self.model(prompt, **request_kwargs))
        raise TypeError("chat model must expose invoke, predict, or __call__")


@dataclass
class ChatModelConfidenceProvider:
    adapter: ChatModelTextAdapter
    prompt_builder: Callable[[ConfidenceRequest], str] = build_verbal_confidence_prompt

    def confidence(self, request: ConfidenceRequest) -> Any:
        return self.adapter.complete(self.prompt_builder(request))


@dataclass
class ChatModelEvaluationProvider:
    adapter: ChatModelTextAdapter

    def complete(self, prompt: str) -> Any:
        return self.adapter.complete(prompt)
