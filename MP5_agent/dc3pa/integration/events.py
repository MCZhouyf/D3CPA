from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from ..contracts import Plan, utc_now_iso
from ..errors import ContractValidationError

_REDACT_MARKERS = ("api_key", "apikey", "password", "secret", "token")
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{12,}"),
    re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,;]+"),
)


def _redact_text(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("<redacted>", result)
    return result


def _safe_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ContractValidationError(f"{label} must be numeric, not bool")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(f"{label} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise ContractValidationError(f"{label} must be finite and non-negative")
    return number


def sanitize_for_trace(value: Any, *, depth: int = 0) -> Any:
    """Return a bounded, JSON-safe representation without raw observations or secrets."""

    if depth > 8:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        return value
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Path):
        return value.name
    if isinstance(value, Mapping):
        result: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(marker in lowered for marker in _REDACT_MARKERS):
                result[key_text] = "<redacted>"
            elif lowered in {"image", "rgb", "pov", "image_vector", "embedding"}:
                result[key_text] = _array_descriptor(item)
            else:
                result[key_text] = sanitize_for_trace(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        clipped = [sanitize_for_trace(item, depth=depth + 1) for item in items[:100]]
        if len(items) > 100:
            clipped.append(f"<truncated:{len(items) - 100}>")
        return clipped
    if is_dataclass(value):
        return sanitize_for_trace(asdict(value), depth=depth + 1)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return sanitize_for_trace(to_dict(), depth=depth + 1)
        except Exception:
            pass
    descriptor = _array_descriptor(value)
    if descriptor != "<opaque>":
        return descriptor
    return f"<{type(value).__name__}>"


def _array_descriptor(value: Any) -> Any:
    shape = getattr(value, "shape", None)
    dtype = getattr(value, "dtype", None)
    if shape is not None:
        try:
            return {
                "type": type(value).__name__,
                "shape": [int(item) for item in shape],
                "dtype": str(dtype) if dtype is not None else "unknown",
            }
        except Exception:
            return {"type": type(value).__name__, "shape": "unavailable"}
    return "<opaque>"


@dataclass(frozen=True)
class InventorySnapshot:
    items: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]]) -> "InventorySnapshot":
        normalized: Dict[str, float] = {}
        for name, quantity in dict(data or {}).items():
            item = " ".join(str(name).strip().lower().replace("_", " ").split())
            if not item:
                continue
            number = _safe_number(quantity, f"inventory[{name!r}]")
            normalized[item] = normalized.get(item, 0.0) + number
        return cls(items=normalized)

    def to_dict(self) -> Dict[str, float]:
        return dict(self.items)


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    attempt: int
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.event_type.strip():
            raise ContractValidationError("RuntimeEvent.event_type cannot be empty")
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 0:
            raise ContractValidationError("RuntimeEvent.attempt must be a non-negative integer")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "attempt": self.attempt,
            "payload": sanitize_for_trace(self.payload),
        }


@dataclass(frozen=True)
class AttemptRecord:
    attempt: int
    plan_id: Optional[str]
    plan_version: Optional[int]
    controller_executed: bool
    controller_success: bool
    goal_success: bool
    duration_seconds: float
    feedback: str = ""
    suggestion: str = ""
    fallback_used: bool = False
    blocked_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dict(sanitize_for_trace(asdict(self)))


@dataclass(frozen=True)
class TaskRunResult:
    task: str
    mode: str
    success: bool
    attempts: tuple[AttemptRecord, ...]
    events: tuple[RuntimeEvent, ...]
    reactive_replan_count: int
    pre_execution_revision_count: int
    evaluation_count: int
    planning_fallback_count: int
    pre_execution_block_count: int
    controller_execution_count: int
    final_plan: Optional[Plan] = None
    final_underground: bool = False
    memory_recorded: bool = False
    failure_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "mode": self.mode,
            "success": self.success,
            "attempts": [item.to_dict() for item in self.attempts],
            "events": [item.to_dict() for item in self.events],
            "reactive_replan_count": self.reactive_replan_count,
            "pre_execution_revision_count": self.pre_execution_revision_count,
            "evaluation_count": self.evaluation_count,
            "planning_fallback_count": self.planning_fallback_count,
            "pre_execution_block_count": self.pre_execution_block_count,
            "controller_execution_count": self.controller_execution_count,
            "final_plan": (
                sanitize_for_trace(self.final_plan.to_dict())
                if self.final_plan is not None
                else None
            ),
            "final_underground": self.final_underground,
            "memory_recorded": self.memory_recorded,
            "failure_reason": sanitize_for_trace(self.failure_reason),
        }
