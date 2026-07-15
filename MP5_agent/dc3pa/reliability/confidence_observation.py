"""Auditable, non-secret model-confidence observations.

The collector is intentionally independent from the runtime.  The reliability strategy
records plan/step keyed observations; the Stage-6 runtime drains only observations for
the final plan version that is actually sent to the Controller.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from threading import RLock
from typing import Any, Dict, Iterable, Mapping, Tuple


@dataclass(frozen=True)
class ModelConfidenceObservation:
    plan_id: str
    plan_version: int
    step_id: str
    step_index: int
    request_hash: str
    implementation: str
    confidence_level: str
    base_probability: float
    decision_probability: float
    calibrated_probability: float | None = None
    model_id: str = ""
    prompt_version: str = ""
    prompt_sha256: str = ""
    calibration_artifact_id: str = ""
    cache_hit: bool = False
    episode_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.plan_id or not self.step_id or not self.request_hash:
            raise ValueError("plan_id, step_id, and request_hash are required")
        if self.plan_version < 0 or self.step_index < 0:
            raise ValueError("plan_version and step_index must be non-negative")
        for name in ("base_probability", "decision_probability"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.calibrated_probability is not None and not (
            0.0 <= float(self.calibrated_probability) <= 1.0
        ):
            raise ValueError("calibrated_probability must be in [0, 1]")

    @property
    def key(self) -> tuple[str, int, str, str, str]:
        return (
            self.plan_id,
            self.plan_version,
            self.step_id,
            self.implementation,
            self.prompt_version,
        )

    def with_episode_id(self, episode_id: str) -> "ModelConfidenceObservation":
        return replace(self, episode_id=str(episode_id))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "step_id": self.step_id,
            "step_index": self.step_index,
            "request_hash": self.request_hash,
            "implementation": self.implementation,
            "confidence_level": self.confidence_level,
            "base_probability": self.base_probability,
            "decision_probability": self.decision_probability,
            "calibrated_probability": self.calibrated_probability,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_sha256,
            "calibration_artifact_id": self.calibration_artifact_id,
            "cache_hit": self.cache_hit,
            "episode_id": self.episode_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ModelConfidenceObservation":
        return cls(
            plan_id=str(data.get("plan_id", "")),
            plan_version=int(data.get("plan_version", 0)),
            step_id=str(data.get("step_id", "")),
            step_index=int(data.get("step_index", -1)),
            request_hash=str(data.get("request_hash", "")),
            implementation=str(data.get("implementation", "")),
            confidence_level=str(data.get("confidence_level", "")),
            base_probability=float(data.get("base_probability")),
            decision_probability=float(data.get("decision_probability")),
            calibrated_probability=(
                None
                if data.get("calibrated_probability") is None
                else float(data.get("calibrated_probability"))
            ),
            model_id=str(data.get("model_id", "")),
            prompt_version=str(data.get("prompt_version", "")),
            prompt_sha256=str(data.get("prompt_sha256", "")),
            calibration_artifact_id=str(data.get("calibration_artifact_id", "")),
            cache_hit=bool(data.get("cache_hit", False)),
            episode_id=str(data.get("episode_id", "")),
            metadata=dict(data.get("metadata", {})),
        )


class ConfidenceObservationCollector:
    """Thread-safe latest-observation collector keyed by plan version and step.

    Re-scoring the same final step replaces the older observation.  This ensures that
    calibration uses the value closest to Controller execution rather than a rejected
    earlier computation.  Older plan versions are retained until the runtime explicitly
    drains/clears the plan, allowing revision diagnostics without mislabeling them.
    """

    def __init__(self) -> None:
        self._items: Dict[
            tuple[str, int, str, str, str], ModelConfidenceObservation
        ] = {}
        self._lock = RLock()

    def record(self, observation: ModelConfidenceObservation) -> None:
        with self._lock:
            self._items[observation.key] = observation

    def snapshot(self) -> Tuple[ModelConfidenceObservation, ...]:
        with self._lock:
            values = tuple(self._items.values())
        return tuple(
            sorted(values, key=lambda item: (item.plan_id, item.plan_version, item.step_index))
        )

    def for_plan(
        self, plan_id: str, plan_version: int
    ) -> Tuple[ModelConfidenceObservation, ...]:
        return tuple(
            item
            for item in self.snapshot()
            if item.plan_id == plan_id and item.plan_version == int(plan_version)
        )

    def drain_for_execution(
        self, *, plan_id: str, plan_version: int, episode_id: str
    ) -> Tuple[ModelConfidenceObservation, ...]:
        with self._lock:
            selected = [
                item
                for item in self._items.values()
                if item.plan_id == plan_id and item.plan_version == int(plan_version)
            ]
            # Clear all versions for this logical plan after the execution attempt so
            # rejected revisions cannot leak into a later reactive attempt.
            keys = [key for key, item in self._items.items() if item.plan_id == plan_id]
            for key in keys:
                self._items.pop(key, None)
        selected.sort(key=lambda item: item.step_index)
        return tuple(item.with_episode_id(episode_id) for item in selected)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def extend(self, observations: Iterable[ModelConfidenceObservation]) -> None:
        for observation in observations:
            self.record(observation)
