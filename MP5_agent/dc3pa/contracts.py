from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .errors import ContractValidationError

ALLOWED_ACTIONS = {
    "find",
    "move_to",
    "mine",
    "craft",
    "fight",
    "equip",
    "dig_down",
    "dig_up",
    "apply",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_item_name(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{name} must be a mapping, got {type(value)!r}")
    return value


@dataclass(frozen=True)
class Action:
    name: str
    args: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.name not in ALLOWED_ACTIONS:
            raise ContractValidationError(
                f"Unsupported action '{self.name}'. Allowed: {sorted(ALLOWED_ACTIONS)}"
            )
        if not isinstance(self.args, dict):
            raise ContractValidationError("Action.args must be a dict")
        self._validate_shape()

    def _validate_shape(self) -> None:
        required = {
            "find": {"obj"},
            "move_to": {"obj"},
            "mine": {"obj", "tool"},
            "craft": {"obj", "materials", "platform"},
            "fight": {"obj", "tool"},
            "equip": {"obj"},
            "dig_down": {"y_level", "tool"},
            # Both vertical-navigation actions require the target height.  The
            # controller cannot infer it safely from the current frame: that
            # would turn an omitted LLM parameter into a hidden execution
            # policy and, before this contract check, let the malformed action
            # reach the controller only to fail at runtime.
            "dig_up": {"y_level", "tool"},
            "apply": {"obj", "tool"},
        }[self.name]
        missing = required - set(self.args)
        if missing:
            raise ContractValidationError(
                f"Action '{self.name}' is missing args: {sorted(missing)}"
            )
        if self.name == "craft":
            obj = _require_mapping(self.args["obj"], "craft.obj")
            materials = _require_mapping(self.args["materials"], "craft.materials")
            if len(obj) != 1:
                raise ContractValidationError("craft.obj must contain exactly one output")
            for label, mapping in (("craft.obj", obj), ("craft.materials", materials)):
                for key, quantity in mapping.items():
                    if not normalize_item_name(key):
                        raise ContractValidationError(f"{label} contains an empty item name")
                    try:
                        number = float(quantity)
                    except (TypeError, ValueError) as exc:
                        raise ContractValidationError(
                            f"{label}[{key!r}] must be numeric"
                        ) from exc
                    if not math.isfinite(number) or number <= 0:
                        raise ContractValidationError(
                            f"{label}[{key!r}] must be positive"
                        )
        if self.name in {"dig_down", "dig_up"}:
            try:
                int(self.args["y_level"])
            except (TypeError, ValueError) as exc:
                raise ContractValidationError(
                    f"{self.name}.y_level must be an integer"
                ) from exc

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Action":
        data = _require_mapping(data, "action")
        return cls(name=str(data.get("name", "")), args=dict(data.get("args", {})))

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "args": self.args}


@dataclass(frozen=True)
class PlanStep:
    actions: List[Action]
    times: int = 1
    step_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    expected_outputs: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.actions:
            raise ContractValidationError("A plan step must contain at least one action")
        if not isinstance(self.times, int) or self.times <= 0:
            raise ContractValidationError("PlanStep.times must be a positive integer")
        if not self.step_id:
            raise ContractValidationError("PlanStep.step_id cannot be empty")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanStep":
        data = _require_mapping(data, "plan step")
        try:
            times = int(data.get("times", 1))
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("PlanStep.times must be integer-like") from exc
        actions_raw = data.get("actions", [])
        if not isinstance(actions_raw, Sequence) or isinstance(actions_raw, (str, bytes)):
            raise ContractValidationError("PlanStep.actions must be a list")
        return cls(
            actions=[Action.from_dict(action) for action in actions_raw],
            times=times,
            step_id=str(data.get("step_id") or uuid.uuid4().hex),
            expected_outputs=dict(data.get("expected_outputs", {})),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self, legacy: bool = False) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "times": str(self.times) if legacy else self.times,
            "actions": [action.to_dict() for action in self.actions],
        }
        if not legacy:
            result.update(
                {
                    "step_id": self.step_id,
                    "expected_outputs": self.expected_outputs,
                    "metadata": self.metadata,
                }
            )
        return result


@dataclass(frozen=True)
class Plan:
    task: str
    steps: List[PlanStep]
    plan_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    version: int = 1
    source: str = "reasoning_chain"
    parent_plan_id: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task.strip():
            raise ContractValidationError("Plan.task cannot be empty")
        if not self.steps:
            raise ContractValidationError("Plan.steps cannot be empty")
        if self.version <= 0:
            raise ContractValidationError("Plan.version must be positive")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], task: Optional[str] = None) -> "Plan":
        data = _require_mapping(data, "plan")
        steps_raw = data.get("steps", data.get("workflow", []))
        if not isinstance(steps_raw, Sequence) or isinstance(steps_raw, (str, bytes)):
            raise ContractValidationError("Plan steps/workflow must be a list")
        resolved_task = str(task or data.get("task") or data.get("task_name") or "").strip()
        return cls(
            task=resolved_task,
            steps=[PlanStep.from_dict(step) for step in steps_raw],
            plan_id=str(data.get("plan_id") or uuid.uuid4().hex),
            version=int(data.get("version", 1)),
            source=str(data.get("source", "reasoning_chain")),
            parent_plan_id=data.get("parent_plan_id"),
            created_at=str(data.get("created_at") or utc_now_iso()),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "steps": [step.to_dict() for step in self.steps],
            "plan_id": self.plan_id,
            "version": self.version,
            "source": self.source,
            "parent_plan_id": self.parent_plan_id,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    def to_legacy_workflow(self) -> Dict[str, Any]:
        return {"workflow": [step.to_dict(legacy=True) for step in self.steps]}


@dataclass(frozen=True)
class AgentState:
    task: str
    inventory: Dict[str, float] = field(default_factory=dict)
    position: str = "unknown"
    health: Optional[float] = None
    observation_ref: Optional[str] = None
    voxel_summary: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def normalized_inventory(self) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for item, quantity in self.inventory.items():
            normalized = normalize_item_name(item)
            if normalized:
                result[normalized] = result.get(normalized, 0.0) + float(quantity)
        return result

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TraceEvent:
    event_type: str
    payload: Dict[str, Any]
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EpisodeTrace:
    episode_id: str
    task: str
    seed: int
    events: List[TraceEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def append(self, event_type: str, payload: Mapping[str, Any]) -> TraceEvent:
        event = TraceEvent(event_type=event_type, payload=dict(payload))
        self.events.append(event)
        return event

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "task": self.task,
            "seed": self.seed,
            "events": [event.to_dict() for event in self.events],
            "metadata": self.metadata,
        }

    def write_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
