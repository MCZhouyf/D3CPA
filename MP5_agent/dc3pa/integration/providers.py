from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..reliability.contracts import ConfidenceRequest
from ..reliability.model import build_verbal_confidence_prompt


TRACK_E_MAX_OUTPUT_TOKENS = 2048
TRACK_E_TIMEOUT_SECONDS = 60


def isolated_chat_model_copy(model: Any) -> Any:
    """Shallow-copy a chat model while detaching Pydantic instance state."""

    configured = copy.copy(model)
    if configured is model:
        raise TypeError("Track-E chat model cannot be copied in isolation")
    original_state = getattr(model, "__dict__", None)
    if (
        isinstance(original_state, dict)
        and getattr(configured, "__dict__", None) is original_state
    ):
        object.__setattr__(configured, "__dict__", dict(original_state))
    for name in ("__fields_set__", "__pydantic_fields_set__"):
        original_fields = getattr(model, name, None)
        if (
            isinstance(original_fields, set)
            and getattr(configured, name, None) is original_fields
        ):
            object.__setattr__(configured, name, set(original_fields))
    return configured


def configure_track_e_chat_model(model: Any) -> Any:
    """Return an isolated model copy with the E3 Track-E request budget."""

    clone_for_track_e = getattr(model, "_dc3pa_clone_for_track_e", None)
    configured = (
        clone_for_track_e()
        if callable(clone_for_track_e)
        else isolated_chat_model_copy(model)
    )

    target_getter = getattr(configured, "_dc3pa_track_e_configuration_target", None)
    target = target_getter() if callable(target_getter) else configured
    original_target_getter = getattr(model, "_dc3pa_track_e_configuration_target", None)
    original_target = (
        original_target_getter()
        if callable(original_target_getter)
        else model
    )
    exposes_chat_call = any(
        hasattr(target, name) for name in ("invoke", "predict", "__call__")
    )

    required = {
        "temperature": 0,
        "max_tokens": TRACK_E_MAX_OUTPUT_TOKENS,
        "request_timeout": TRACK_E_TIMEOUT_SECONDS,
        "max_retries": 0,
    }
    for name, value in required.items():
        if not hasattr(target, name):
            if not exposes_chat_call:
                raise TypeError(f"Track-E chat model does not expose {name}")
            setattr(target, name, value)
            if getattr(target, name) != value:
                raise ValueError(f"Track-E chat model did not apply {name}")
            continue
        setattr(target, name, value)
        if getattr(target, name) != value:
            raise ValueError(f"Track-E chat model did not apply {name}")
    for name in ("callbacks", "callback_manager"):
        if hasattr(original_target, name) and not hasattr(target, name):
            raise TypeError(f"Track-E chat model copy lost {name}")
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
