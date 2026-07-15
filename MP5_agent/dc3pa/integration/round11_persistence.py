"""Round-1.1 persistence helpers shared by the Stage-6 runtime.

Keeping record construction outside the 900-line runtime makes the lifecycle
rules testable without MineDojo.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Mapping, Sequence, Tuple

from ..contracts import Plan
from ..memory.acquisition import (
    AcquisitionStore,
    LocalSceneCandidate,
    SuccessfulTrajectoryRecord,
)
from ..memory.calibration_store import (
    CalibrationEpisodeRecord,
    CalibrationEpisodeStore,
)
from ..reliability.environment_v2 import canonical_action_key
from .telemetry_serialization import serialize_execution_event


def new_episode_id(task: str, attempt: int) -> str:
    safe_task = "-".join(str(task).strip().split()) or "task"
    return f"{safe_task}-{int(attempt)}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"


def _key(event: Any) -> tuple[int, int]:
    return int(getattr(event, "step_index", -1)), int(
        getattr(event, "action_index", -1)
    )


def commit_successful_acquisition(
    *,
    store: AcquisitionStore,
    episode_id: str,
    task: str,
    task_information: Mapping[str, Any],
    plan: Plan,
    execution_telemetry: Sequence[Any],
    attempt: int,
    mode: str,
) -> tuple[str, int]:
    """Commit one successful trajectory and its locally successful scenes."""

    action_starts: Dict[tuple[int, int], Any] = {}
    successful_starts: Dict[tuple[int, int], Any] = {}
    for event in execution_telemetry:
        event_type = getattr(event, "event_type", "")
        if event_type == "action_started":
            action_starts[_key(event)] = event
        elif event_type == "action_finished" and getattr(event, "status", "") == "success":
            started = action_starts.get(_key(event))
            if started is not None:
                successful_starts[_key(event)] = started

    candidates: list[LocalSceneCandidate] = []
    image_paths: Dict[tuple[int, int], str] = {}
    for key, started in sorted(successful_starts.items()):
        payload = getattr(started, "payload", {})
        rgb = payload.get("rgb") if isinstance(payload, Mapping) else None
        if rgb is None:
            continue
        step_index, action_index = key
        step_id = str(getattr(started, "step_id", "") or f"step-{step_index}")
        image_path = store.write_rgb_array(
            episode_id=episode_id,
            step_id=step_id,
            action_index=action_index,
            rgb=rgb,
        )
        image_paths[key] = image_path
        local_subgoal = str(payload.get("local_subgoal", "")).strip()
        action = dict(payload.get("action", {}))
        if not local_subgoal:
            raise ValueError(
                "action_started telemetry is missing local_subgoal; "
                "the adapter/controller integration is incomplete"
            )
        candidates.append(
            LocalSceneCandidate(
                episode_id=episode_id,
                task_name=task,
                plan_id=str(getattr(started, "plan_id", plan.plan_id)),
                plan_version=int(getattr(started, "plan_version", plan.version)),
                step_id=step_id,
                step_index=step_index,
                action_index=action_index,
                local_subgoal=local_subgoal,
                action=action,
                image_path=image_path,
                pre_inventory=dict(payload.get("inventory", {})),
                metadata={
                    "capture_point": "immediately_before_action",
                    "action_key": canonical_action_key(action),
                    "local_subgoal": local_subgoal,
                },
            )
        )

    telemetry_payload = []
    for event in execution_telemetry:
        telemetry_payload.append(
            serialize_execution_event(event, image_path=image_paths.get(_key(event)))
        )

    record = SuccessfulTrajectoryRecord(
        episode_id=episode_id,
        task_name=task,
        seed=str(task_information.get("seed", "")),
        plan=plan.to_dict(),
        telemetry=tuple(telemetry_payload),
        scene_candidates=tuple(candidates),
        metadata={"stage": 6, "mode": mode, "attempt": int(attempt)},
    )
    path = store.commit_success(record)
    return str(path), len(candidates)


def commit_calibration_episode(
    *,
    store: CalibrationEpisodeStore,
    episode_id: str,
    task: str,
    task_information: Mapping[str, Any],
    plan: Plan,
    execution_telemetry: Sequence[Any],
    success: bool,
    failure_reason: str,
    attempt: int,
    mode: str,
    confidence_observations: Sequence[Mapping[str, Any]] = (),
) -> str:
    """Persist a success or failure for later step-label construction."""

    telemetry = tuple(
        serialize_execution_event(event) for event in execution_telemetry
    )
    record = CalibrationEpisodeRecord(
        episode_id=episode_id,
        task_name=task,
        seed=str(task_information.get("seed", "")),
        success=bool(success),
        plan=plan.to_dict(),
        telemetry=telemetry,
        confidence_observations=tuple(dict(item) for item in confidence_observations),
        failure_reason=str(failure_reason or ""),
        metadata={"stage": 6, "mode": mode, "attempt": int(attempt)},
    )
    return str(store.commit(record))
