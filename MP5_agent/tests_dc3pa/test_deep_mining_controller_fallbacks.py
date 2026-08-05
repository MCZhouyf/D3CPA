from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


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


def test_non_log_resource_fallback_is_disabled():
    controller = _controller({"iron pickaxe": 1})
    env = FakeEnv(controller.memory)

    assert not controller._fallback_mine_diamond_resource(env, "gold", 1)
    assert not env.set_inventory_calls


def test_inventory_mutation_rejects_non_log_items():
    controller = _controller({"planks": 2})
    env = FakeEnv(controller.memory)

    try:
        controller._set_inventory_from_memory(env, {"diamond": 1})
    except RuntimeError as exc:
        assert "restricted to the log callback" in str(exc)
    else:
        raise AssertionError("non-log inventory mutation must be rejected")
    assert not env.set_inventory_calls


def test_low_level_tool_failure_is_forwarded_once_for_llm_replanning():
    controller = _controller({"cobblestone": 8, "stick": 2})
    controller.memory._dc3pa_execution_failure = {
        "reason": "tool_consumed",
        "tool": "stone pickaxe",
        "resource_goal": {"item": "coal", "quantity": 3},
        "feedback": "The planned stone pickaxe was consumed during execution.",
        "success": False,
        "suggestion": "Re-plan from the current observed state.",
    }

    failure = controller._consume_execution_failure()

    assert not failure["success"]
    assert failure["reason"] == "tool_consumed"
    assert failure["tool"] == "stone pickaxe"
    assert failure["resource_goal"] == {"item": "coal", "quantity": 3}
    assert "Re-plan" in failure["suggestion"]
    assert controller._consume_execution_failure() is None


def test_gather_logs_falls_back_after_bounded_failed_attempts(monkeypatch):
    controller = _controller()
    env = FakeEnv(controller.memory)

    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "controller.explore_above_ground_none", lambda *args, **kwargs: None
    )

    assert controller._gather_logs(env, underground=False, target_logs=2, max_attempts=1)
    assert controller.memory.inventory["log"] == 2.0
    assert env.set_inventory_calls


class StepCountingFakeEnv(FakeEnv):
    def __init__(self, memory):
        super().__init__(memory)
        self.step_count = 0

    def step(self, action):
        self.step_count += 1
        return super().step(action)


def test_gather_logs_defers_callback_until_100_environment_steps(monkeypatch):
    controller = _controller()
    env = StepCountingFakeEnv(controller.memory)

    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "controller.explore_above_ground_none", lambda *args, **kwargs: None
    )

    assert controller._gather_logs(env, underground=False, target_logs=2)
    assert env.step_count >= 100
    assert controller.memory.inventory["log"] == 2.0
    assert env.set_inventory_calls


def test_wooden_bootstrap_does_not_synthesize_failed_crafts(monkeypatch):
    controller = _controller()
    env = FakeEnv(controller.memory)

    def fake_gather_logs(self, env, underground, target_logs):
        self._set_inventory_from_memory(
            env, {"log": target_logs}, callback_kind="log_callback"
        )
        return True

    monkeypatch.setattr(Controller, "_gather_logs", fake_gather_logs)
    monkeypatch.setattr(Controller, "_craft_bootstrap_item", lambda *args, **kwargs: None)

    assert not controller.ensure_wooden_bootstrap(env, underground=False)
    assert controller.memory.inventory.get("wooden pickaxe", 0) == 0
    assert set(controller.memory.inventory) == {"log"}


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


def test_dependency_preparation_does_not_synthesize_cobblestone_or_sticks():
    controller = _controller({"wooden pickaxe": 1, "cobblestone": 2})
    env = FakeEnv(controller.memory)

    controller._prepare_deep_mining_craft_dependencies(env, "stone pickaxe")
    assert controller.memory.inventory["cobblestone"] == 2.0

    controller = _controller(
        {"crafting table": 1, "iron ingot": 3, "planks": 2, "wooden pickaxe": 1}
    )
    env = FakeEnv(controller.memory)
    controller._prepare_deep_mining_craft_dependencies(env, "iron pickaxe")

    assert controller.memory.inventory.get("stick", 0) == 0
    assert not env.set_inventory_calls


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

    assert not result["success"]
    assert not underground
    assert controller.memory.inventory.get("cobblestone", 0) == 0
    assert not env.set_inventory_calls


class _UpwardEnv(FakeEnv):
    def __init__(self, memory, y_level=40.0):
        super().__init__(memory)
        self.y_level = float(y_level)
        self.can_see_sky = False

    def step(self, action):
        return (
            {
                "inventory": {
                    "name": np.array(list(self.memory.inventory)),
                    "quantity": np.array(list(self.memory.inventory.values())),
                },
                "location_stats": {
                    "pos": np.array([0.0, self.y_level, 0.0]),
                    "can_see_sky": self.can_see_sky,
                },
            },
            0,
            False,
            {},
        )


def test_planned_planks_craft_does_not_consume_logs_in_bootstrap(monkeypatch):
    controller = _controller({"log": 1})
    env = FakeEnv(controller.memory)
    craft_calls = []

    monkeypatch.setattr("controller.share_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(Controller, "_is_deep_mining_task", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        Controller,
        "ensure_wooden_bootstrap",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("planned plank crafting must not run wooden bootstrap")
        ),
    )
    monkeypatch.setattr(
        Controller,
        "_execute_craft_with_retries",
        lambda self, *args, **kwargs: craft_calls.append(args) or True,
    )

    result, underground = controller.check_and_execute_workflow(
        env,
        {
            "workflow": [
                {
                    "times": "1",
                    "actions": [
                        {
                            "name": "craft",
                            "args": {
                                "obj": {"planks": 4},
                                "materials": {"log": 1},
                                "platform": None,
                            },
                        }
                    ],
                }
            ]
        },
        {"task": "diamond"},
        underground=False,
    )

    assert result["success"]
    assert not underground
    assert controller.memory.inventory["log"] == 1
    assert craft_calls


def test_dig_up_invokes_physical_go_up_and_checks_elevation(monkeypatch):
    controller = _controller({"wooden pickaxe": 1})
    env = _UpwardEnv(controller.memory, y_level=40.0)
    called = []

    monkeypatch.setattr("controller.share_memory", lambda *args, **kwargs: None)

    def fake_go_up(target_env, target_y, equipment=""):
        called.append((target_env, target_y, equipment))
        target_env.y_level = float(target_y)
        target_env.can_see_sky = True

    monkeypatch.setattr("controller.go_up", fake_go_up)

    result, underground = controller.check_and_execute_workflow(
        env,
        {
            "workflow": [
                {
                    "times": "1",
                    "actions": [
                        {"name": "dig_up", "args": {"tool": "wooden pickaxe"}}
                    ],
                }
            ]
        },
        {"task": "diamond"},
        underground=True,
    )

    assert result["success"]
    assert called == [(env, 50, "wooden pickaxe")]
    assert not underground


def test_dig_down_normalizes_legacy_wooden_pickaxe_target(monkeypatch):
    controller = _controller({"wooden pickaxe": 1})
    env = _UpwardEnv(controller.memory, y_level=70.0)
    called = []

    monkeypatch.setattr("controller.share_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "controller.go_down_to_y_level",
        lambda target_env, target_y, equipment="": called.append(
            (target_env, target_y, equipment)
        ),
    )
    workflow = {
        "workflow": [
            {
                "times": "1",
                "actions": [
                    {
                        "name": "dig_down",
                        "args": {"y_level": 60, "tool": "wooden pickaxe"},
                    }
                ],
            }
        ]
    }

    result, underground = controller.check_and_execute_workflow(
        env, workflow, {"task": "diamond"}, underground=False
    )

    assert result["success"]
    assert underground
    assert called == [(env, 50, "wooden pickaxe")]
    assert workflow["workflow"][0]["actions"][0]["args"]["y_level"] == 50


def test_downstream_craft_materials_cap_cobblestone_collection():
    workflow = [
        {"times": "20", "actions": [{"name": "mine", "args": {"obj": "cobblestone"}}]},
        {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"furnace": 1}, "materials": {"cobblestone": 8}}}]},
        {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"stone pickaxe": 1}, "materials": {"cobblestone": 3, "stick": 2}}}]},
    ]

    assert Controller._workflow_material_requirement(workflow, 0, "cobblestone", 20) == 11


def test_unused_craft_surplus_is_capped_by_downstream_plan_demand():
    workflow = [
        {
            "times": "20",
            "actions": [
                {"name": "mine", "args": {"obj": "iron ore", "tool": "stone pickaxe"}}
            ],
        },
        {
            "times": "1",
            "actions": [
                {
                    "name": "craft",
                    "args": {
                        "obj": {"iron ingot": 20},
                        "materials": {"iron ore": 20, "coal": 20},
                        "platform": "furnace",
                    },
                }
            ],
        },
        {
            "times": "1",
            "actions": [
                {
                    "name": "craft",
                    "args": {
                        "obj": {"iron pickaxe": 1},
                        "materials": {"iron ingot": 3, "stick": 2},
                        "platform": "crafting table",
                    },
                }
            ],
        },
        {
            "times": "1",
            "actions": [
                {"name": "dig_down", "args": {"y_level": 12, "tool": "iron pickaxe"}}
            ],
        },
    ]

    Controller._cap_unused_craft_surplus(workflow)

    ingot_args = workflow[1]["actions"][0]["args"]
    assert ingot_args["obj"] == {"iron ingot": 3}
    assert ingot_args["materials"] == {"iron ore": 3, "coal": 3}
    assert Controller._workflow_material_requirement(workflow, 0, "iron ore", 20) == 3


def test_downstream_material_requirement_drives_cobblestone_skip(monkeypatch):
    controller = _controller({"cobblestone": 11})
    monkeypatch.setattr("controller.legacy_task_hacks_enabled", lambda: False)
    monkeypatch.setenv("DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK", "1")

    assert controller._should_skip_diamond_action(
        {"name": "mine", "args": {"obj": "cobblestone", "tool": "wooden pickaxe"}},
        20,
        {"task": "diamond"},
        required_quantity=11,
    )


def test_unsatisfied_stick_craft_is_not_skipped_by_existing_wooden_pickaxe(monkeypatch):
    controller = _controller({"wooden pickaxe": 1, "planks": 2})
    env = FakeEnv(controller.memory)
    craft_calls = []

    monkeypatch.setattr("controller.share_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(Controller, "_is_deep_mining_task", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        Controller, "ensure_wooden_bootstrap", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(
        Controller, "_prepare_deep_mining_craft_dependencies", lambda *args: None
    )
    monkeypatch.setattr(
        Controller,
        "_execute_craft_with_retries",
        lambda self, *args, **kwargs: craft_calls.append(args) or True,
    )

    result, underground = controller.check_and_execute_workflow(
        env,
        {
            "workflow": [
                {
                    "times": "1",
                    "actions": [
                        {
                            "name": "craft",
                            "args": {
                                "obj": {"stick": 4},
                                "materials": {"planks": 2},
                                "platform": None,
                            },
                        }
                    ],
                }
            ]
        },
        {"task": "diamond"},
        underground=False,
    )

    assert result["success"]
    assert not underground
    assert craft_calls


def test_missing_sticks_are_recovered_from_logs_in_same_attempt(monkeypatch):
    controller = _controller(
        {"iron ingot": 3, "planks": 1, "stone pickaxe": 1}
    )
    env = FakeEnv(controller.memory)

    monkeypatch.setattr(
        Controller,
        "_surface_for_material_recovery",
        lambda self, target_env, underground: (True, False),
    )

    def fake_gather(self, target_env, underground, target_logs, max_attempts=2):
        self._set_inventory_from_memory(
            target_env, {"log": target_logs}, callback_kind="log_callback"
        )
        return True

    monkeypatch.setattr(Controller, "_gather_logs", fake_gather)

    def fake_physical_craft(self, target_env, craft_name, use_crafting_table, craft_num=1):
        if craft_name == "planks":
            self.memory.inventory["log"] -= craft_num
            self.memory.inventory["planks"] = self.memory.inventory.get("planks", 0) + 4 * craft_num
        elif craft_name == "stick":
            self.memory.inventory["planks"] -= 2 * craft_num
            self.memory.inventory["stick"] = self.memory.inventory.get("stick", 0) + 4 * craft_num

    monkeypatch.setattr(Controller, "_craft_bootstrap_item", fake_physical_craft)

    recovered, underground = controller._recover_missing_craft_materials(
        env,
        {
            "materials": {"iron ingot": 3, "stick": 2},
            "obj": {"iron pickaxe": 1},
            "platform": "crafting table",
        },
        underground=True,
    )

    assert recovered
    assert not underground
    assert controller.memory.inventory["stick"] >= 2
    assert controller.memory.inventory["iron ingot"] == 3


def test_missing_wood_material_recovery_physically_digs_up(monkeypatch):
    controller = _controller({"stone pickaxe": 1})
    env = _UpwardEnv(controller.memory, y_level=40.0)
    called = []

    monkeypatch.setattr("controller.share_memory", lambda *args, **kwargs: None)

    def fake_go_up(target_env, target_y, equipment=""):
        called.append((target_env, target_y, equipment))
        target_env.y_level = float(target_y)
        target_env.can_see_sky = target_y >= 60

    monkeypatch.setattr("controller.go_up", fake_go_up)

    surfaced, underground = controller._surface_for_material_recovery(env, True)

    assert surfaced
    assert not underground
    assert called == [
        (env, 50, "stone pickaxe"),
        (env, 60, "stone pickaxe"),
    ]


def test_missing_direct_logs_are_gathered_in_same_attempt(monkeypatch):
    controller = _controller({"wooden pickaxe": 1})
    env = FakeEnv(controller.memory)
    gathered = []

    monkeypatch.setattr(
        Controller,
        "_surface_for_material_recovery",
        lambda self, target_env, underground: (True, False),
    )

    def fake_gather(self, target_env, underground, target_logs, max_attempts=2):
        gathered.append(target_logs)
        self._set_inventory_from_memory(
            target_env, {"log": target_logs}, callback_kind="log_callback"
        )
        return True

    monkeypatch.setattr(Controller, "_gather_logs", fake_gather)

    recovered, underground = controller._recover_missing_craft_materials(
        env,
        {
            "materials": {"log": 3},
            "obj": {"planks": 12},
            "platform": None,
        },
        underground=False,
    )

    assert recovered
    assert not underground
    assert gathered == [3]
    assert controller.memory.inventory["log"] == 3
