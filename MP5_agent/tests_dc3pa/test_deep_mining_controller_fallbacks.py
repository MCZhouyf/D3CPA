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
        "legacy Controller fallback tests require optional runtime modules: "
        + ", ".join(_missing_legacy_deps),
        allow_module_level=True,
    )


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from controller import Controller  # noqa: E402
from utils import update_find_obj_name, update_inventory_obj_name  # noqa: E402


class FakeMemory:
    def __init__(self, inventory=None):
        self.inventory = dict(inventory or {})

    def update_inventory(self, inventory):
        self.inventory = dict(inventory)


class FakeEnv:
    def __init__(self, memory):
        self.memory = memory
        self.set_inventory_calls = []

    def step(self, action):
        return (
            {
                "inventory": {
                    "name": np.array(list(self.memory.inventory)),
                    "quantity": np.array(list(self.memory.inventory.values())),
                }
            },
            0,
            False,
            {},
        )

    def set_inventory(self, inventory_items):
        self.set_inventory_calls.append(list(inventory_items))
        self.memory.inventory = {
            item.name.replace("_", " "): float(item.quantity)
            for item in inventory_items
            if item.quantity > 0
        }


def _controller(inventory=None):
    controller = Controller.__new__(Controller)
    controller.memory = FakeMemory(inventory)
    controller.checker = object()
    return controller


def test_deep_mining_bounded_fallback_requires_explicit_flag(monkeypatch):
    controller = _controller()

    monkeypatch.setattr("controller.legacy_task_hacks_enabled", lambda: False)
    monkeypatch.delenv("DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK", raising=False)

    assert not controller._is_deep_mining_task({"task": "diamond"})

    monkeypatch.setenv("DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK", "1")

    assert controller._is_deep_mining_task({"task": "diamond"})


def test_gold_uses_mining_target_aliases_and_recovery_flag(monkeypatch):
    controller = _controller({"iron pickaxe": 1})
    env = FakeEnv(controller.memory)

    monkeypatch.setattr("controller.legacy_task_hacks_enabled", lambda: False)
    monkeypatch.setenv("DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK", "1")

    assert controller._is_deep_mining_task({"task": "gold"})
    assert update_find_obj_name("gold") == "gold ore"
    assert update_inventory_obj_name("gold ore") == "gold"

    result = controller.check_action_preparation(
        env,
        "mine",
        {"obj": "gold ore", "tool": "iron pickaxe"},
        {"task": "gold"},
        {},
    )

    assert result["success"]


def test_gold_fallback_uses_valid_minedojo_item_name():
    controller = _controller({"iron pickaxe": 1})
    env = FakeEnv(controller.memory)

    assert controller._fallback_mine_diamond_resource(env, "gold", 1)
    assert env.set_inventory_calls[-1][-1].name == "gold_ore"
    assert controller.memory.inventory["gold"] == 1.0


def test_gather_logs_does_not_inject_without_diagnostic_session(monkeypatch):
    controller = _controller()
    env = FakeEnv(controller.memory)

    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "controller.explore_above_ground_none", lambda *args, **kwargs: None
    )

    assert not controller._gather_logs(
        env, underground=False, target_logs=2, max_attempts=1
    )
    assert controller.memory.inventory.get("log", 0) == 0
    assert not env.set_inventory_calls


def test_wooden_bootstrap_uses_deterministic_craft_fallbacks(monkeypatch):
    controller = _controller()
    env = FakeEnv(controller.memory)

    def fake_gather_logs(self, env, underground, target_logs):
        self._set_inventory_from_memory(env, {"log": target_logs})
        return True

    monkeypatch.setattr(Controller, "_gather_logs", fake_gather_logs)
    monkeypatch.setattr(Controller, "_craft_bootstrap_item", lambda *args, **kwargs: None)

    assert controller.ensure_wooden_bootstrap(env, underground=False)
    assert controller.memory.inventory["wooden pickaxe"] == 1.0
    assert controller.memory.inventory.get("crafting table", 0) >= 1.0


def test_cobblestone_step_requires_stone_pickaxe_minimum():
    controller = _controller({"cobblestone": 2})
    step = {
        "times": "2",
        "actions": [
            {"name": "find", "args": {"obj": "cobblestone"}},
            {"name": "move_to", "args": {"obj": "cobblestone"}},
            {"name": "mine", "args": {"obj": "cobblestone", "tool": None}},
        ],
    }

    assert not controller._diamond_step_already_satisfied(step)

    controller.memory.inventory["cobblestone"] = 3

    assert controller._diamond_step_already_satisfied(step)


def test_stone_pickaxe_dependency_preparation_fills_cobblestone():
    controller = _controller({"wooden pickaxe": 1, "cobblestone": 2})
    env = FakeEnv(controller.memory)

    controller._prepare_deep_mining_craft_dependencies(env, "stone pickaxe")

    assert controller.memory.inventory["cobblestone"] == 3.0


def test_iron_pickaxe_dependency_preparation_fills_sticks():
    controller = _controller(
        {"crafting table": 1, "iron ingot": 3, "planks": 2, "wooden pickaxe": 1}
    )
    env = FakeEnv(controller.memory)

    controller._prepare_deep_mining_craft_dependencies(env, "iron pickaxe")

    assert controller.memory.inventory["stick"] >= 2.0


def test_move_to_resource_fallback_after_bounded_attempts(monkeypatch):
    controller = _controller({"wooden pickaxe": 1})
    env = FakeEnv(controller.memory)
    workflow = {
        "workflow": [
            {
                "times": "3",
                "actions": [
                    {"name": "move_to", "args": {"obj": "cobblestone"}},
                    {"name": "mine", "args": {"obj": "cobblestone", "tool": "wooden pickaxe"}},
                ],
            }
        ]
    }

    monkeypatch.setenv("DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK", "1")
    monkeypatch.setattr("controller.legacy_task_hacks_enabled", lambda: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "controller.explore_above_ground_none", lambda *args, **kwargs: None
    )

    result, underground = controller.check_and_execute_workflow(
        env, workflow, {"task": "diamond"}, underground=False
    )

    assert result["success"]
    assert not underground
    assert controller.memory.inventory["cobblestone"] == 3.0
