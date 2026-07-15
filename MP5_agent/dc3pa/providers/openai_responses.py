"""Minimal OpenAI Responses API adapter with LangChain-like methods.

No prompt or response body is logged. Network calls are made only when an
explicit GPT-5.1 profile is enabled. The adapter supports the textual interfaces
used by the legacy Planner/Reflexion and DC3PA reliability chains.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Sequence

import requests

from .model_profile import OpenAIResponsesModelProfile


_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class AdapterMessage:
    content: str


@dataclass(frozen=True)
class ResponseUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class SafeResponseMetadata:
    requested_model: str
    returned_model: str
    profile_id: str
    reasoning_effort: str
    purpose: str
    request_started_at: str
    request_duration_seconds: float
    response_id_sha256: str
    usage: ResponseUsage
    request_text_logged: bool = False
    response_text_logged: bool = False


@dataclass(frozen=True)
class TextResponseWithMetadata:
    text: str
    metadata: SafeResponseMetadata


def _role_name(message: Any) -> str:
    role = getattr(message, "role", None)
    if role:
        return str(role)
    name = type(message).__name__.lower()
    if "system" in name:
        return "system"
    if "human" in name or "user" in name:
        return "user"
    if "assistant" in name or "ai" in name:
        return "assistant"
    return "user"


def _message_content(message: Any) -> str:
    if isinstance(message, str):
        return message
    content = getattr(message, "content", None)
    if content is not None:
        return str(content)
    if isinstance(message, Mapping):
        return str(message.get("content", ""))
    return str(message)


def normalize_input(value: Any) -> list[dict[str, str]]:
    if isinstance(value, str):
        return [{"role": "user", "content": value}]
    if isinstance(value, Mapping):
        return [
            {
                "role": str(value.get("role", "user")),
                "content": str(value.get("content", "")),
            }
        ]
    if isinstance(value, Sequence):
        return [
            {"role": _role_name(item), "content": _message_content(item)}
            for item in value
        ]
    return [{"role": "user", "content": str(value)}]


def extract_output_text(payload: Mapping[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    pieces: list[str] = []
    output = payload.get("output", [])
    if not isinstance(output, Sequence):
        raise ValueError("Responses API output is not a list")
    for item in output:
        if not isinstance(item, Mapping) or item.get("type") != "message":
            continue
        content = item.get("content", [])
        if not isinstance(content, Sequence):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            if part.get("type") in {"output_text", "text"}:
                text = part.get("text", "")
                if isinstance(text, str):
                    pieces.append(text)
    result = "".join(pieces)
    if not result:
        status = payload.get("status", "")
        incomplete = payload.get("incomplete_details", {})
        raise RuntimeError(
            f"Responses API returned no output text; status={status!r}, "
            f"incomplete_details={incomplete!r}"
        )
    return result


def parse_usage(payload: Mapping[str, Any]) -> ResponseUsage:
    usage = payload.get("usage", {})
    if not isinstance(usage, Mapping):
        return ResponseUsage()
    output_details = usage.get("output_tokens_details", {})
    if not isinstance(output_details, Mapping):
        output_details = {}
    return ResponseUsage(
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        reasoning_tokens=int(output_details.get("reasoning_tokens", 0) or 0),
        total_tokens=int(usage.get("total_tokens", 0) or 0),
    )


class OpenAIResponsesChatAdapter:
    def __init__(
        self,
        *,
        profile: OpenAIResponsesModelProfile,
        purpose: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
        usage_observer: Optional[Callable[[ResponseUsage], None]] = None,
        metadata_observer: Optional[Callable[[SafeResponseMetadata], None]] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.profile = profile if profile.profile_id else profile.with_id()
        self.purpose = purpose
        self.max_output_tokens = self.profile.token_cap_for(purpose)
        self.api_key = api_key or os.environ.get(
            self.profile.api_key_environment_variable, ""
        )
        if not self.api_key:
            raise ValueError(
                f"Missing API key environment variable "
                f"{self.profile.api_key_environment_variable}"
            )
        configured_base = base_url or os.environ.get(
            self.profile.base_url_environment_variable, ""
        )
        self.base_url = (configured_base or "https://api.openai.com/v1").rstrip("/")
        self.session = session or requests.Session()
        self.usage_observer = usage_observer
        self.metadata_observer = metadata_observer
        self.sleep = sleep

    def _request_payload(self, value: Any) -> dict[str, Any]:
        return {
            "model": self.profile.model,
            "input": normalize_input(value),
            "reasoning": {"effort": self.profile.reasoning_effort},
            "max_output_tokens": self.max_output_tokens,
            "store": self.profile.store,
        }

    def _post(self, value: Any) -> Mapping[str, Any]:
        payload = self._request_payload(value)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        attempts = self.profile.maximum_retries + 1
        last_error: Optional[BaseException] = None
        for attempt in range(attempts):
            try:
                response = self.session.post(
                    f"{self.base_url}/responses",
                    headers=headers,
                    json=payload,
                    timeout=self.profile.request_timeout_seconds,
                )
                if response.status_code in _RETRYABLE_STATUS and attempt + 1 < attempts:
                    retry_after = response.headers.get("retry-after", "")
                    try:
                        delay = float(retry_after)
                    except (TypeError, ValueError):
                        delay = min(8.0, (2.0 ** attempt) + random.random() * 0.25)
                    self.sleep(delay)
                    continue
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, Mapping):
                    raise ValueError("Responses API JSON must be an object")
                response_model = data.get("model")
                if response_model != self.profile.model:
                    raise ValueError(
                        "Responses API did not confirm the selected model identifier"
                    )
                return data
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                self.sleep(min(8.0, (2.0 ** attempt) + random.random() * 0.25))
        raise RuntimeError(
            f"OpenAI Responses request failed after {attempts} attempts"
        ) from last_error

    def invoke(self, value: Any, **_: Any) -> AdapterMessage:
        return AdapterMessage(content=self.invoke_with_metadata(value).text)

    def invoke_with_metadata(self, value: Any) -> TextResponseWithMetadata:
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()
        data = self._post(value)
        duration = time.monotonic() - started
        usage = parse_usage(data)
        if self.usage_observer is not None:
            self.usage_observer(usage)
        response_id = str(data.get("id", ""))
        metadata = SafeResponseMetadata(
            requested_model=self.profile.model,
            returned_model=str(data.get("model", "")),
            profile_id=self.profile.profile_id,
            reasoning_effort=self.profile.reasoning_effort,
            purpose=self.purpose,
            request_started_at=started_at,
            request_duration_seconds=duration,
            response_id_sha256=(
                hashlib.sha256(response_id.encode("utf-8")).hexdigest()
                if response_id else ""
            ),
            usage=usage,
        )
        if self.metadata_observer is not None:
            self.metadata_observer(metadata)
        return TextResponseWithMetadata(
            text=extract_output_text(data), metadata=metadata
        )

    def predict(self, text: str, **kwargs: Any) -> str:
        return self.invoke(text, **kwargs).content

    def __call__(self, value: Any, **kwargs: Any) -> AdapterMessage:
        return self.invoke(value, **kwargs)
