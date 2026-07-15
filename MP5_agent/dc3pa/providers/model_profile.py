"""Pinned GPT-5.1 Responses API profile for DC3PA.

The exact snapshot avoids alias drift. The profile uses the same snapshot and
reasoning effort for all agentic roles to avoid a model-backbone confound.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping


PROFILE_SCHEMA_VERSION = 1
GPT51_SNAPSHOT = "gpt-5.1-2025-11-13"
SUPPORTED_EFFORTS = frozenset({"none", "low", "medium", "high"})


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class OpenAIResponsesModelProfile:
    profile_name: str = "dc3pa-gpt51-reference-v1"
    model: str = GPT51_SNAPSHOT
    reasoning_effort: str = "low"
    store: bool = False
    request_timeout_seconds: float = 180.0
    maximum_retries: int = 3
    purpose_max_output_tokens: Mapping[str, int] = field(
        default_factory=lambda: {
            "planning": 8192,
            "dc3pa_confidence_and_evaluation": 4096,
            "reflection": 4096,
        }
    )
    api_key_environment_variable: str = "OPENAI_API_KEY"
    base_url_environment_variable: str = "OPENAI_BASE_URL"
    schema_version: int = PROFILE_SCHEMA_VERSION
    profile_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != PROFILE_SCHEMA_VERSION:
            raise ValueError("Unsupported model profile schema")
        if self.model != GPT51_SNAPSHOT:
            raise ValueError(f"Model must be exact snapshot {GPT51_SNAPSHOT}")
        if self.reasoning_effort not in SUPPORTED_EFFORTS:
            raise ValueError("Unsupported reasoning effort")
        if not isinstance(self.store, bool):
            raise ValueError("store must be bool")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.maximum_retries < 0:
            raise ValueError("maximum_retries cannot be negative")
        if not self.purpose_max_output_tokens:
            raise ValueError("Purpose token caps are required")
        for purpose, value in self.purpose_max_output_tokens.items():
            if not purpose.strip() or isinstance(value, bool) or int(value) <= 0:
                raise ValueError("Invalid purpose token cap")
        expected = self.compute_profile_id()
        if self.profile_id and self.profile_id != expected:
            raise ValueError("Model profile hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("profile_id", None)
        payload["purpose_max_output_tokens"] = dict(
            sorted(self.purpose_max_output_tokens.items())
        )
        return payload

    def compute_profile_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "OpenAIResponsesModelProfile":
        return replace(self, profile_id=self.compute_profile_id())

    def to_dict(self) -> dict[str, Any]:
        profile = self if self.profile_id else self.with_id()
        payload = profile.payload_without_id()
        payload["profile_id"] = profile.profile_id
        return payload

    def token_cap_for(self, purpose: str) -> int:
        if purpose not in self.purpose_max_output_tokens:
            raise ValueError(f"Unknown LLM purpose {purpose!r}")
        return int(self.purpose_max_output_tokens[purpose])
