from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, runtime_checkable

from ..contracts import AgentState, Plan
from .contracts import ConfidenceRequest, DimensionScore, ReliabilityContext

_CODE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.IGNORECASE | re.DOTALL)
_PERCENT = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*$")


@runtime_checkable
class ConfidenceProvider(Protocol):
    def confidence(self, request: ConfidenceRequest) -> Any:
        ...


@dataclass
class CallableConfidenceProvider:
    function: Callable[[ConfidenceRequest], Any]

    def confidence(self, request: ConfidenceRequest) -> Any:
        return self.function(request)


def build_verbal_confidence_prompt(request: ConfidenceRequest) -> str:
    payload = request.to_prompt_payload()
    return (
        "Assess only the proposed step's chance of succeeding in the given state. "
        "Return JSON with keys confidence and reason. confidence must be a number "
        "between 0 and 1. Keep reason concise; do not provide hidden chain-of-thought.\n"
        + json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    )


def _strip_fence(text: str) -> str:
    match = _CODE_FENCE.match(text.strip())
    return match.group(1) if match else text.strip()


def parse_confidence(raw: Any) -> tuple[float, str, Dict[str, Any]]:
    metadata: Dict[str, Any] = {}
    reason = ""
    value = raw
    if isinstance(raw, str):
        stripped = _strip_fence(raw)
        percent = _PERCENT.match(stripped)
        if percent:
            value = float(percent.group(1)) / 100.0
            metadata["input_format"] = "percent_string"
        else:
            try:
                value = json.loads(stripped)
                metadata["input_format"] = "json_string"
            except json.JSONDecodeError:
                value = stripped
                metadata["input_format"] = "numeric_string"
    if isinstance(value, Mapping):
        reason = str(value.get("reason", value.get("rationale", ""))).strip()
        # Provider-supplied free-form fields are intentionally not persisted. They may
        # contain hidden reasoning, secrets, or non-serializable objects. Parser-generated
        # format metadata below is sufficient for an auditable confidence score.
        for key in ("confidence", "probability", "score"):
            if key in value:
                value = value[key]
                break
        else:
            raise ValueError("Confidence mapping has no confidence/probability/score field")
    if isinstance(value, str):
        percent = _PERCENT.match(value)
        if percent:
            value = float(percent.group(1)) / 100.0
        else:
            value = float(value.strip())
    if isinstance(value, bool):
        raise ValueError("Boolean confidence is invalid")
    probability = float(value)
    if 1.0 < probability <= 100.0:
        probability /= 100.0
        metadata["interpreted_as_percent"] = True
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"Confidence {probability!r} is outside [0, 1]")
    return probability, reason, metadata


class VerbalConfidenceStrategy:
    def __init__(
        self,
        provider: ConfidenceProvider,
        failure_mode: str = "unavailable",
        cache_enabled: bool = True,
    ):
        if failure_mode not in {"unavailable", "raise"}:
            raise ValueError("failure_mode must be 'unavailable' or 'raise'")
        self.provider = provider
        self.failure_mode = failure_mode
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, DimensionScore] = {}

    @staticmethod
    def _cache_key(request: ConfidenceRequest) -> str:
        payload = request.to_prompt_payload()
        serialized = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    def score(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> DimensionScore:
        request = ConfidenceRequest(
            plan=plan,
            state=state,
            step_index=step_index,
            context=context or ReliabilityContext(),
        )
        key = self._cache_key(request)
        if self.cache_enabled and key in self._cache:
            cached = self._cache[key]
            evidence = dict(cached.evidence)
            evidence["cache_hit"] = True
            return DimensionScore(
                dimension=cached.dimension,
                probability=cached.probability,
                available=cached.available,
                reason=cached.reason,
                evidence=evidence,
                hard_conflict=cached.hard_conflict,
            )
        try:
            raw = self.provider.confidence(request)
            probability, reason, metadata = parse_confidence(raw)
            result = DimensionScore(
                dimension="model",
                probability=probability,
                available=True,
                reason=reason or "Provider returned verbal confidence",
                evidence={
                    "provider_type": type(self.provider).__name__,
                    "cache_hit": False,
                    "metadata": metadata,
                },
            )
        except Exception as exc:
            if self.failure_mode == "raise":
                raise
            result = DimensionScore.unavailable(
                "model",
                f"Confidence provider failed: {type(exc).__name__}",
                evidence={"error": str(exc), "cache_hit": False},
            )
        if self.cache_enabled and result.available:
            self._cache[key] = result
        return result
