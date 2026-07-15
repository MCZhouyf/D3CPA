"""Join model-confidence observations with Controller execution telemetry.

Only the final plan version actually executed is labelable.  Rejected plan revisions,
censored steps, deleted steps, and ambiguous system failures are excluded rather than
silently assigned label zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

from .confidence_observation import ModelConfidenceObservation
from .ordinal_calibration import OrdinalCalibrationSample

_SUCCESS = {"success", "succeeded", "skipped", "skipped_satisfied", "already_satisfied"}
_FAILURE = {"failure", "failed", "error", "timeout", "budget_exhausted"}
_CENSORED = {"censored", "not_executed"}


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _event_status(event: Any) -> str:
    return str(_get(event, "status", "") or "").strip().lower()


def _event_type(event: Any) -> str:
    return str(_get(event, "event_type", "") or "").strip().lower()


@dataclass(frozen=True)
class StepCalibrationExample:
    episode_id: str
    plan_id: str
    plan_version: int
    step_id: str
    step_index: int
    confidence_level: str
    label: int
    request_hash: str
    model_id: str
    prompt_version: str
    source_status: str

    def to_ordinal_sample(self) -> OrdinalCalibrationSample:
        return OrdinalCalibrationSample(
            confidence_level=self.confidence_level,
            label=self.label,
            source_id=(
                f"{self.episode_id}:{self.plan_id}:{self.plan_version}:{self.step_id}"
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "step_id": self.step_id,
            "step_index": self.step_index,
            "confidence_level": self.confidence_level,
            "label": self.label,
            "request_hash": self.request_hash,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "source_status": self.source_status,
        }


@dataclass(frozen=True)
class ExcludedStep:
    episode_id: str
    plan_id: str
    plan_version: int
    step_id: str
    step_index: int
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _classify_step(events: Sequence[Any]) -> tuple[int | None, str]:
    if not events:
        return None, "no_execution_telemetry"
    statuses = [_event_status(event) for event in events]
    event_types = [_event_type(event) for event in events]
    if any(status in _CENSORED for status in statuses) or any(
        "censor" in event_type for event_type in event_types
    ):
        return None, "censored"

    # Prefer explicit step completion events when present.
    step_finished = [
        event for event in events if _event_type(event) in {"step_finished", "step_completed"}
    ]
    if step_finished:
        status = _event_status(step_finished[-1])
        if status in _SUCCESS:
            return 1, status
        if status in _FAILURE:
            return 0, status
        return None, f"ambiguous_step_status:{status or 'empty'}"

    actions = [event for event in events if _event_type(event) == "action_finished"]
    if actions:
        action_statuses = [_event_status(event) for event in actions]
        if any(status in _FAILURE for status in action_statuses):
            return 0, "action_failure"
        if all(status in _SUCCESS for status in action_statuses):
            return 1, "all_actions_success"
        return None, "ambiguous_action_status"
    return None, "no_terminal_step_event"


def join_confidence_with_execution(
    *,
    episode_id: str,
    plan: Mapping[str, Any],
    telemetry: Sequence[Any],
    observations: Iterable[ModelConfidenceObservation | Mapping[str, Any]],
) -> tuple[Tuple[StepCalibrationExample, ...], Tuple[ExcludedStep, ...]]:
    plan_id = str(plan.get("plan_id", ""))
    plan_version = int(plan.get("version", plan.get("plan_version", 0)))
    normalized_observations = tuple(
        item
        if isinstance(item, ModelConfidenceObservation)
        else ModelConfidenceObservation.from_mapping(item)
        for item in observations
    )

    by_step: Dict[tuple[str, int, str], list[Any]] = {}
    for event in telemetry:
        event_plan_id = str(_get(event, "plan_id", ""))
        event_version = int(_get(event, "plan_version", 0) or 0)
        step_id = str(_get(event, "step_id", ""))
        if event_plan_id != plan_id or event_version != plan_version or not step_id:
            continue
        by_step.setdefault((event_plan_id, event_version, step_id), []).append(event)

    included = []
    excluded = []
    for observation in normalized_observations:
        if observation.plan_id != plan_id or observation.plan_version != plan_version:
            excluded.append(
                ExcludedStep(
                    episode_id=episode_id,
                    plan_id=observation.plan_id,
                    plan_version=observation.plan_version,
                    step_id=observation.step_id,
                    step_index=observation.step_index,
                    reason="non_executed_plan_version",
                )
            )
            continue
        label, source_status = _classify_step(
            by_step.get((plan_id, plan_version, observation.step_id), [])
        )
        if label is None:
            excluded.append(
                ExcludedStep(
                    episode_id=episode_id,
                    plan_id=plan_id,
                    plan_version=plan_version,
                    step_id=observation.step_id,
                    step_index=observation.step_index,
                    reason=source_status,
                )
            )
            continue
        included.append(
            StepCalibrationExample(
                episode_id=episode_id,
                plan_id=plan_id,
                plan_version=plan_version,
                step_id=observation.step_id,
                step_index=observation.step_index,
                confidence_level=observation.confidence_level,
                label=label,
                request_hash=observation.request_hash,
                model_id=observation.model_id,
                prompt_version=observation.prompt_version,
                source_status=source_status,
            )
        )
    included.sort(key=lambda item: item.step_index)
    excluded.sort(key=lambda item: (item.plan_version, item.step_index))
    return tuple(included), tuple(excluded)
