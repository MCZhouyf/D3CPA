from types import SimpleNamespace

import numpy as np

from dc3pa.contracts import Action, Plan, PlanStep
from dc3pa.integration.round11_persistence import (
    commit_calibration_episode,
    commit_successful_acquisition,
)
from dc3pa.memory.acquisition import AcquisitionStore
from dc3pa.memory.calibration_store import CalibrationEpisodeStore


def _event(event_type, status="", **kwargs):
    payload = kwargs.pop("payload", {})
    return SimpleNamespace(
        event_type=event_type,
        status=status,
        plan_id="p",
        plan_version=1,
        step_id="s",
        step_index=0,
        action_index=0,
        payload=payload,
        to_dict=lambda include_payload=True: {
            "event_type": event_type,
            "status": status,
            "plan_id": "p",
            "plan_version": 1,
            "step_id": "s",
            "step_index": 0,
            "action_index": 0,
            **({"payload": payload} if include_payload else {}),
        },
    )


def _plan():
    return Plan(
        task="obtain log",
        plan_id="p",
        steps=[
            PlanStep(
                step_id="s",
                actions=[Action("mine", {"obj": "log", "tool": ""})],
                metadata={"local_subgoal": "mine log"},
            )
        ],
    )


def test_successful_acquisition_keeps_full_clean_telemetry(tmp_path):
    start = _event(
        "action_started",
        payload={
            "local_subgoal": "mine log",
            "action": {"name": "mine", "args": {"obj": "log", "tool": ""}},
            "inventory": {},
            "rgb": np.zeros((4, 4, 3), dtype=np.uint8),
        },
    )
    finish = _event(
        "action_finished",
        "success",
        payload={"result": {"ok": True}, "inventory": {"log": 1}},
    )
    store = AcquisitionStore(tmp_path / "acq")
    path, count = commit_successful_acquisition(
        store=store,
        episode_id="e1",
        task="obtain log",
        task_information={"seed": 1},
        plan=_plan(),
        execution_telemetry=(start, finish),
        attempt=1,
        mode="reasoning_only",
    )
    assert count == 1
    payload = next(store.iter_payloads())["record"]
    assert payload["scene_candidates"][0]["local_subgoal"] == "mine log"
    assert "rgb" not in payload["telemetry"][0]["payload"]
    assert payload["telemetry"][1]["payload"]["result"]["ok"] is True
    assert path.endswith("e1.json")


def test_calibration_store_records_failure_without_entering_acquisition(tmp_path):
    store = CalibrationEpisodeStore(tmp_path / "cal")
    path = commit_calibration_episode(
        store=store,
        episode_id="e-fail",
        task="obtain log",
        task_information={"seed": 2},
        plan=_plan(),
        execution_telemetry=(_event("action_finished", "failure", payload={"result": {"reason": "blocked"}}),),
        success=False,
        failure_reason="controller_reported_failure",
        attempt=1,
        mode="reasoning_only",
    )
    payload = next(store.iter_payloads())["record"]
    assert payload["success"] is False
    assert payload["failure_reason"] == "controller_reported_failure"
    assert path.endswith("e-fail.json")
