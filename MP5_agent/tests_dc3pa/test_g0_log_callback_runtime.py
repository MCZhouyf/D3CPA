from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from controller import Controller  # noqa: E402


class _Memory:
    def __init__(self) -> None:
        self.inventory: dict[str, float] = {}

    def update_inventory(self, inventory):
        self.inventory = dict(inventory)


class _Env:
    def __init__(self, memory: _Memory) -> None:
        self.memory = memory
        self.step_count = 0
        self.set_calls = []

    def step(self, _action):
        self.step_count += 1
        return ({"inventory": {"name": np.array(list(self.memory.inventory)), "quantity": np.array(list(self.memory.inventory.values()))}}, 0, False, {})

    def set_inventory(self, items):
        self.set_calls.append(list(items))
        self.memory.inventory = {item.name.replace("_", " "): float(item.quantity) for item in items}


def test_g0_dynamic_log_callback_trace_preserves_delayed_log_only_write(monkeypatch) -> None:
    controller = Controller.__new__(Controller)
    controller.memory = _Memory()
    controller.checker = object()
    env = _Env(controller.memory)
    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.explore_above_ground_none", lambda *args, **kwargs: None)

    assert controller._gather_logs(env, underground=False, target_logs=2)
    assert env.step_count >= 100
    assert len(env.set_calls) == 1
    assert [(item.name, item.quantity) for item in env.set_calls[0]] == [("log", 2)]
    assert controller.memory.inventory == {"log": 2.0}


def _g0_controller(inventory=None):
    controller = Controller.__new__(Controller)
    controller.memory = _Memory()
    controller.memory.inventory = dict(inventory or {})
    controller.checker = object()
    return controller


def test_g0_missing_mine_craft_and_smelt_requirements_fail_without_plan_or_inventory_mutation() -> None:
    cases = [
        (
            {"tool": "iron pickaxe", "obj": "diamond ore"},
            "mine",
            "missing_declared_tool",
        ),
        (
            {"obj": {"wooden pickaxe": 1}, "materials": {"planks": 3, "stick": 2}, "platform": "crafting table"},
            "craft",
            "missing_declared_platform",
        ),
        (
            {"obj": {"iron ingot": 1}, "materials": {"iron ore": 1, "coal": 1}, "platform": "furnace"},
            "smelt",
            "missing_declared_platform",
        ),
    ]
    for args, expected_type, expected_reason in cases:
        controller = _g0_controller()
        env = _Env(controller.memory)
        workflow = {"workflow": [{"times": "1", "actions": [{"name": "craft" if expected_type in {"craft", "smelt"} else "mine", "args": args}]}]}
        original = deepcopy(workflow)
        result, _ = controller.check_and_execute_workflow(env, workflow, {"task": "unrelated"}, False)
        assert result["success"] is False
        assert result["action_type"] == expected_type
        assert result["reason_code"] == expected_reason
        assert result["inventory_before_hash"] == result["inventory_after_hash"]
        assert controller.memory.inventory == {}
        assert env.set_calls == []
        assert workflow == original


def test_g0_craft_material_failure_names_the_missing_materials() -> None:
    controller = _g0_controller({"planks": 3})
    result = controller.check_action_preparation(
        _Env(controller.memory),
        "craft",
        {
            "obj": {"wooden pickaxe": 1},
            "materials": {"planks": 3, "stick": 2},
            "platform": None,
        },
    )

    assert result["reason_code"] == "missing_declared_materials"
    assert result["missing_requirements"] == ["stick"]
    assert result["feedback"] == "Missing declared craft materials: stick."


def test_g0_formal_dispatch_reaches_protected_log_gather_after_move_failure(monkeypatch) -> None:
    controller = _g0_controller()
    env = _Env(controller.memory)
    requested = []
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)

    def gather(_env, _underground, target_logs):
        requested.append(target_logs)
        controller.memory.inventory["log"] = float(target_logs)
        return True

    monkeypatch.setattr(controller, "_gather_logs", gather)
    workflow = {"workflow": [{"times": 1, "actions": [
        {"name": "move_to", "args": {"obj": "log"}},
        {"name": "mine", "args": {"obj": "log", "tool": ""}},
    ]}]}
    result, _ = controller.check_and_execute_workflow(env, workflow, {"task": "wooden slab"}, False)

    assert result["success"] is True
    assert requested == [1]
    assert controller.memory.inventory["log"] == 1.0


def test_g0_formal_mine_accepts_a_real_drop_with_a_different_block_name(monkeypatch) -> None:
    controller = _g0_controller()
    env = _Env(controller.memory)
    monkeypatch.setattr(
        "controller.mine",
        lambda **_kwargs: (np.array(["wheat seeds"]), np.array([1])),
    )
    workflow = {"workflow": [{"times": 1, "actions": [
        {"name": "mine", "args": {"obj": "grass", "tool": ""}},
    ]}]}

    result, _ = controller.check_and_execute_workflow(
        env, workflow, {"task": "wheat seeds"}, False
    )

    assert result["success"] is True
    assert controller.memory.inventory == {"wheat seeds": 1}


def test_g0_formal_move_uncertainty_does_not_censor_a_matching_declared_mine(monkeypatch) -> None:
    controller = _g0_controller()
    env = _Env(controller.memory)
    monkeypatch.setattr("controller.approach", lambda **_kwargs: False)
    monkeypatch.setattr(
        "controller.mine",
        lambda **_kwargs: (np.array(["wheat seeds"]), np.array([1])),
    )
    workflow = {"workflow": [{"times": 1, "actions": [
        {"name": "move_to", "args": {"obj": "grass"}},
        {"name": "mine", "args": {"obj": "grass", "tool": ""}},
    ]}]}

    result, _ = controller.check_and_execute_workflow(
        env, workflow, {"task": "wheat seeds"}, False
    )

    assert result["success"] is True
    assert controller.memory.inventory == {"wheat seeds": 1}
