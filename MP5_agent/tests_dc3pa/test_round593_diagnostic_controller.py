from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from tests_dc3pa.legacy_controller_test_gate import (
    missing_legacy_controller_dependencies,
)


pytestmark = pytest.mark.minedojo
_missing_legacy_deps = missing_legacy_controller_dependencies()
if _missing_legacy_deps:
    pytest.skip(
        "diagnostic Controller tests require optional runtime modules: "
        + ", ".join(_missing_legacy_deps),
        allow_module_level=True,
    )

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from controller import Controller  # noqa: E402
from dc3pa.experiments.log_fallback import (  # noqa: E402
    DiagnosticLogFallbackSession,
    LogFallbackPolicy,
)
from dc3pa.contracts import Action, Plan, PlanStep  # noqa: E402
from dc3pa.experiments.formal_log_bootstrap import (  # noqa: E402
    FormalLogBootstrapPolicy,
    FormalLogBootstrapSession,
)


class FakeMemory:
    def __init__(self, inventory=None):
        self.inventory = dict(inventory or {})


class FakeEnv:
    def __init__(self, memory):
        self.memory = memory
        self.set_inventory_calls = []

    def events(self):
        return {
            "inventory": {
                "name": np.array(list(self.memory.inventory), dtype=object),
                "quantity": np.array(
                    list(self.memory.inventory.values()), dtype=float
                ),
            }
        }

    def set_inventory(self, items):
        self.set_inventory_calls.append(tuple(items))
        self.memory.inventory = {
            item.name.replace("_", " "): float(item.quantity) for item in items
        }


class OneStaleFrameEnv(FakeEnv):
    def __init__(self, memory):
        super().__init__(memory)
        self.pending_inventory = None
        self.post_set_event_count = 0

    def events(self):
        if self.pending_inventory is not None:
            self.post_set_event_count += 1
            if self.post_set_event_count > 1:
                self.memory.inventory = self.pending_inventory
                self.pending_inventory = None
        return super().events()

    def set_inventory(self, items):
        self.set_inventory_calls.append(tuple(items))
        self.pending_inventory = {
            item.name.replace("_", " "): float(item.quantity) for item in items
        }


def _controller(inventory=None):
    controller = Controller.__new__(Controller)
    controller.memory = FakeMemory(inventory)
    controller.checker = object()
    controller._sync_memory = lambda env: env.events()
    return controller


def test_controller_diagnostic_session_preserves_inventory_and_records_event(
    monkeypatch,
):
    controller = _controller({"log": 1, "stick": 2, "stone pickaxe": 1})
    env = FakeEnv(controller.memory)
    session = DiagnosticLogFallbackSession(
        policy=LogFallbackPolicy().with_id(),
        source_commit="commit",
        task="craft fence",
        seed="17",
    )
    controller._dc3pa_log_fallback_session = session
    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "controller.explore_above_ground_none", lambda *args, **kwargs: None
    )

    assert controller._gather_logs(env, False, target_logs=4, max_attempts=3)

    assert controller.memory.inventory == {
        "log": 4.0,
        "stick": 2.0,
        "stone pickaxe": 1.0,
    }
    assert len(env.set_inventory_calls) == 1
    assert len(session.events) == 1
    assert session.events[0].injected_count == 3


def test_controller_without_session_never_calls_set_inventory(monkeypatch):
    controller = _controller({"stick": 2})
    env = FakeEnv(controller.memory)
    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "controller.explore_above_ground_none", lambda *args, **kwargs: None
    )

    assert not controller._gather_logs(env, False, target_logs=2, max_attempts=3)
    assert not env.set_inventory_calls


def test_controller_fallback_tolerates_one_stale_inventory_frame(monkeypatch):
    controller = _controller({"stick": 2})
    env = OneStaleFrameEnv(controller.memory)
    session = DiagnosticLogFallbackSession(
        policy=LogFallbackPolicy().with_id(),
        source_commit="commit",
        task="craft fence",
        seed="19",
    )
    controller._dc3pa_log_fallback_session = session
    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "controller.explore_above_ground_none", lambda *args, **kwargs: None
    )

    assert controller._gather_logs(env, False, target_logs=4, max_attempts=3)

    assert env.post_set_event_count == 2
    assert controller.memory.inventory == {"stick": 2.0, "log": 4.0}
    assert session.events[0].inventory_after == 4
    assert session.events[0].injected_count == 4


def test_formal_controller_uses_plan_target_instead_of_local_target(monkeypatch):
    controller = _controller({"stick": 2})
    env = FakeEnv(controller.memory)
    session = FormalLogBootstrapSession(
        policy=FormalLogBootstrapPolicy().with_id(),
        amendment_id="amendment",
        source_commit="commit",
        blueprint_id="blueprint",
        scope="formal_acquisition",
        method_id="single_chain_reactive_acquisition",
        task="craft fence",
        seed="23",
    )
    session.bind_plan(
        Plan(
            task="craft fence",
            plan_id="plan",
            version=3,
            steps=[
                PlanStep(
                    times=2,
                    actions=[
                        Action(
                            name="mine",
                            args={"obj": "log", "tool": ""},
                        )
                    ],
                )
            ],
        )
    )
    controller._dc3pa_log_fallback_session = session
    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "controller.explore_above_ground_none", lambda *args, **kwargs: None
    )

    assert controller._gather_logs(env, False, target_logs=99, max_attempts=3)
    assert controller.memory.inventory == {"stick": 2.0, "log": 2.0}
    assert session.events[0].planner_declared_log_requirement == 2
    assert session.events[0].injected_logs == 2


def test_formal_log_bootstrap_preserves_display_named_crafting_table(monkeypatch):
    controller = _controller({"crafting table": 1})
    env = FakeEnv(controller.memory)
    session = FormalLogBootstrapSession(
        policy=FormalLogBootstrapPolicy().with_id(),
        amendment_id="amendment",
        source_commit="commit",
        blueprint_id="blueprint",
        scope="formal_acquisition",
        method_id="single_chain_reactive_acquisition",
        task="craft wooden pressure plate",
        seed="29",
    )
    session.bind_plan(
        Plan(
            task="craft wooden pressure plate",
            plan_id="plan",
            version=1,
            steps=[
                PlanStep(
                    times=1,
                    actions=[
                        Action(name="mine", args={"obj": "log", "tool": ""})
                    ],
                )
            ],
        )
    )
    controller._dc3pa_log_fallback_session = session
    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "controller.explore_above_ground_none", lambda *args, **kwargs: None
    )

    assert controller._gather_logs(env, False, target_logs=1, max_attempts=3)
    assert controller.memory.inventory == {"crafting table": 1.0, "log": 1.0}
    assert session.events[0].injected_logs == 1


@pytest.mark.parametrize("action_name", ("find", "move_to", "mine"))
def test_formal_log_step_detection_supports_split_workflows(action_name):
    step = {
        "actions": [
            {"name": action_name, "args": {"obj": "log", "tool": None}}
        ]
    }

    assert Controller._is_formal_log_acquisition_step(step)


def test_formal_log_step_detection_does_not_expand_to_other_resources():
    step = {
        "actions": [
            {"name": "move_to", "args": {"obj": "cobblestone"}}
        ]
    }

    assert not Controller._is_formal_log_acquisition_step(step)
