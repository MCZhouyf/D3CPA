from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..reliability.contracts import ConfidenceRequest
from ..reliability.model import build_verbal_confidence_prompt


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

    def complete(self, prompt: str) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        if hasattr(self.model, "invoke"):
            return extract_text_response(self.model.invoke(prompt))
        if hasattr(self.model, "predict"):
            return extract_text_response(self.model.predict(prompt))
        if callable(self.model):
            return extract_text_response(self.model(prompt))
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
