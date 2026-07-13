from dataclasses import dataclass
from pathlib import Path
import sys

from dc3pa.integration.controller import LegacyControllerAdapter
from dc3pa.integration.execution_observer import (
    InMemoryExecutionObserver,
    emit_execution_event,
)


@dataclass
class _Step:
    step_id: str


class _Plan:
    plan_id = "plan-1"
    version = 2
    steps = (_Step("s1"), _Step("s2"))

    def to_legacy_workflow(self):
        return {
            "workflow": [
                {"times": 1, "actions": [{"type": "find", "object": "tree"}]},
                {"times": 1, "actions": [{"type": "mine", "object": "log"}]},
            ]
        }


class _FakeLegacyController:
    def check_and_execute_workflow(self, *, env, workflow_dict, task_information, underground):
        del env, task_information
        assert workflow_dict["workflow"][0]["_dc3pa_step_id"] == "s1"
        assert workflow_dict["workflow"][1]["_dc3pa_step_index"] == 1
        emit_execution_event(
            self,
            "step_started",
            plan_id="plan-1",
            plan_version=2,
            step_id="s1",
            step_index=0,
        )
        emit_execution_event(
            self,
            "step_finished",
            plan_id="plan-1",
            plan_version=2,
            step_id="s1",
            step_index=0,
            status="success",
        )
        return {"success": True, "feedback": "ok"}, underground


def test_adapter_tags_workflow_and_returns_telemetry():
    observer = InMemoryExecutionObserver()
    adapter = LegacyControllerAdapter(_FakeLegacyController(), observer=observer)
    result = adapter.execute(None, _Plan(), {}, False)
    assert result.success is True
    assert [event.event_type for event in result.telemetry] == [
        "step_started",
        "step_finished",
        "workflow_finished",
    ]


class _Array:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return list(self._values)


class _FakeEnv:
    def __init__(self):
        self.step_count = 0

    def step(self, action):
        self.step_count += 1
        return (
            {
                "rgb": f"frame-{self.step_count}",
                "inventory": {
                    "name": _Array([]),
                    "quantity": _Array([]),
                },
            },
            0,
            False,
            {},
        )


class _Memory:
    def __init__(self):
        self.inventory = {}

    def update_inventory(self, inventory):
        self.inventory = dict(inventory)


class _LegacyPlan:
    plan_id = "legacy-plan"
    version = 1
    steps = (_Step("missing-tool"), _Step("censored-step"))
    source = "test"
    task = "log"

    def to_legacy_workflow(self):
        return {
            "workflow": [
                {
                    "times": 1,
                    "actions": [
                        {
                            "name": "equip",
                            "args": {"obj": "wooden pickaxe"},
                        }
                    ],
                },
                {
                    "times": 1,
                    "actions": [
                        {
                            "name": "find",
                            "args": {"obj": "log"},
                        }
                    ],
                },
            ]
        }


def _make_legacy_controller():
    agent_dir = Path(__file__).resolve().parents[1] / "agent"
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))
    from controller import Controller

    return Controller(memory=_Memory(), checker=None)


def test_real_controller_observer_is_noninvasive_and_censors_remaining_steps():
    plain_env = _FakeEnv()
    observed_env = _FakeEnv()
    plain = LegacyControllerAdapter(_make_legacy_controller()).execute(
        plain_env,
        _LegacyPlan(),
        {"task": "log", "quantity": 1},
        False,
    )

    observer = InMemoryExecutionObserver()
    observed = LegacyControllerAdapter(
        _make_legacy_controller(), observer=observer
    ).execute(
        observed_env,
        _LegacyPlan(),
        {"task": "log", "quantity": 1},
        False,
    )

    assert observed.success == plain.success == False
    assert observed.feedback == plain.feedback
    assert observed_env.step_count == plain_env.step_count
    assert [event.event_type for event in observed.telemetry].count("action_started") == 1
    assert any(
        event.event_type == "action_finished" and event.status == "failure"
        for event in observed.telemetry
    )
    assert any(
        event.event_type == "step_finished"
        and event.step_id == "censored-step"
        and event.status == "censored"
        for event in observed.telemetry
    )
