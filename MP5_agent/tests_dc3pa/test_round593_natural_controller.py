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
        "natural Controller tests require optional runtime modules: "
        + ", ".join(_missing_legacy_deps),
        allow_module_level=True,
    )

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from controller import Controller  # noqa: E402
import structured_actions  # noqa: E402


class FakeMemory:
    def __init__(self, inventory=None):
        self.inventory = dict(inventory or {})

    def update_inventory(self, inventory):
        self.inventory = dict(inventory)


def _controller(inventory=None):
    controller = Controller.__new__(Controller)
    controller.memory = FakeMemory(inventory)
    controller.checker = object()
    return controller


def _events(*, position=(0.0, 60.0, 0.0), blocks=None, inventory=None):
    radius = structured_actions.vradius
    voxels = np.full((radius * 2 + 1,) * 3, "air", dtype=object)
    for offset, name in blocks or ():
        index = tuple(radius + value for value in offset)
        voxels[index] = name
    inventory = dict(inventory or {})
    return {
        "inventory": {
            "name": np.array(list(inventory), dtype=object),
            "quantity": np.array(list(inventory.values()), dtype=float),
        },
        "location_stats": {
            "pos": np.array(position, dtype=float),
            "pitch": np.array([0.0]),
        },
        "voxels": {"block_name": voxels},
        "rays": {
            "block_name": np.array([], dtype=object),
            "block_distance": np.array([], dtype=float),
        },
    }


def test_consecutive_table_recipe_is_detected_without_inventory_fabrication():
    workflow = [
        {"actions": [{"name": "craft", "args": {"platform": "crafting table"}}]},
        {"actions": [{"name": "craft", "args": {"platform": "crafting table"}}]},
    ]
    memory = FakeMemory({"planks": 3, "stick": 2})
    memory._dc3pa_crafting_table_placed = True
    events = _events(inventory=memory.inventory)

    assert Controller._should_keep_crafting_table_placed(workflow, 0, 0)
    returned, ready = structured_actions._place_crafting_table(
        object(), events, memory
    )

    assert ready
    assert returned is events
    assert memory.inventory == {"planks": 3, "stick": 2}
    assert "crafting table" not in memory.inventory


def test_table_returned_to_inventory_invalidates_stale_placement_marker():
    memory = FakeMemory({"crafting table": 1, "planks": 4, "stick": 2})
    memory._dc3pa_crafting_table_placed = True
    events = _events(inventory=memory.inventory)
    events["nearby_tools"] = {"table": False}

    assert not structured_actions._tracked_crafting_table_available(events, memory)
    assert memory._dc3pa_crafting_table_placed is False


def test_inventory_count_normalizes_recipe_item_names():
    events = _events(inventory={"wooden pickaxe": 1, "oak_log": 2})

    assert structured_actions._inventory_item_count(events, "wooden_pickaxe") == 1
    assert structured_actions._inventory_item_count(events, "oak log") == 2


def test_table_inventory_decrease_proves_placement_when_nearby_sensor_is_false():
    events = _events(inventory={})
    events["nearby_tools"] = {"table": False}

    assert structured_actions._crafting_table_placement_accepted(events, 1)
    assert not structured_actions._crafting_table_placement_accepted(events, 0)


def test_voxel_table_is_recognized_when_nearby_sensor_lags():
    events = _events(
        blocks=[((1, 0, 0), "crafting_table")],
        inventory={"planks": 4},
    )
    events["nearby_tools"] = {"table": False}

    assert structured_actions._crafting_table_observed(events)
    assert structured_actions._tracked_crafting_table_available(
        events, FakeMemory({"planks": 4})
    )


def test_table_placement_repositions_once_then_tracks_success(monkeypatch):
    memory = FakeMemory({"crafting table": 1, "planks": 4})

    class FakeEnv:
        def __init__(self):
            self.events = _events(inventory=memory.inventory)
            self.actions = []
            self.repositioned = False

        def step(self, action):
            self.actions.append(list(action))
            if action[0] == 2:
                self.repositioned = True
                self.events = _events(
                    position=(-0.7, 60.0, 0.0),
                    inventory={"crafting table": 1, "planks": 4},
                )
            elif action[5] == 6 and self.repositioned:
                self.events = _events(
                    position=(-0.7, 60.0, 0.0),
                    blocks=[((1, 0, 0), "crafting_table")],
                    inventory={"planks": 4},
                )
                self.events["nearby_tools"] = {"table": True}
            return self.events, 0, False, {}

    env = FakeEnv()
    monkeypatch.setattr(structured_actions, "sleep", lambda current_env: current_env.events)
    monkeypatch.setattr(structured_actions, "share_memory", lambda current_memory, obs: None)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda obs: None)

    returned, ready = structured_actions._place_crafting_table(
        env, env.events, memory, max_attempts=1
    )

    assert ready
    assert structured_actions._crafting_table_observed(returned)
    assert any(action[0] == 2 for action in env.actions)
    assert memory._dc3pa_crafting_table_placed is True
    assert memory._dc3pa_crafting_table_position == [-0.7, 60.0, 0.0]


def test_failed_table_craft_reclaims_table_before_retry(monkeypatch):
    events = _events(inventory={"planks": 4, "stick": 2})
    memory = FakeMemory({"planks": 4, "stick": 2})
    reclaimed = []

    class FakeEnv:
        def step(self, _action):
            return events, 0, False, {}

    monkeypatch.setattr(
        structured_actions,
        "_place_crafting_table",
        lambda env, current, current_memory: (current, True),
    )
    monkeypatch.setattr(structured_actions, "sleep", lambda env: events)
    monkeypatch.setattr(structured_actions, "share_memory", lambda memory, obs: None)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda obs: None)

    def fake_reclaim(env, current, current_memory):
        reclaimed.append(True)
        return current, True

    monkeypatch.setattr(
        structured_actions, "_reclaim_crafting_table", fake_reclaim
    )

    structured_actions.action_craft(
        FakeEnv(),
        "fence",
        memory,
        use_crafting_table=True,
        use_furnace=False,
        craft_num=1,
        reclaim_crafting_table=True,
    )

    assert reclaimed == [True]


@pytest.mark.parametrize(
    ("provider_name", "registry_name"),
    [
        ("oak_planks", "planks"),
        ("crafting_table", "crafting table"),
        ("wooden_pickaxe", "wooden pickaxe"),
        ("iron_ingot", "iron ingot"),
    ],
)
def test_provider_item_names_normalize_to_controller_registry(
    provider_name, registry_name
):
    assert structured_actions.normalize_inventory_name(provider_name) == registry_name


def test_provider_log_alias_maps_to_world_wood_target():
    assert structured_actions.update_find_obj_name("oak_log") == "wood"


def test_find_preparation_recognizes_provider_log_alias_in_inventory():
    events = _events(inventory={"log": 1})

    class FakeEnv:
        def step(self, _action):
            return events, 0, False, {}

    result = _controller().check_action_preparation(
        FakeEnv(),
        "find",
        {"obj": "oak_log"},
        {"task": "crafting_table"},
        events,
    )

    assert result["success"] is True


def test_craft_execution_uses_normalized_target_and_platform(monkeypatch):
    controller = _controller({"planks": 4, "crafting table": 1})
    controller._sync_memory = lambda env: None
    observed = {}

    def fake_action_craft(
        env,
        item,
        memory,
        use_crafting_table,
        use_furnace,
        craft_num,
        reclaim_crafting_table,
    ):
        observed.update(
            item=item,
            use_crafting_table=use_crafting_table,
            use_furnace=use_furnace,
        )
        return ["planks", "crafting table"], [8.0, 1.0]

    monkeypatch.setattr("controller.action_craft", fake_action_craft)

    assert controller._execute_craft_with_retries(
        object(),
        {
            "obj": {"oak_planks": 4},
            "materials": {"oak_log": 1},
            "platform": "crafting_table",
        },
        "planks",
        4,
        max_attempts=1,
    )
    assert observed == {
        "item": "planks",
        "use_crafting_table": True,
        "use_furnace": False,
    }


def test_stick_ignores_unnecessary_crafting_table_platform(monkeypatch):
    controller = _controller({"planks": 2, "crafting table": 1})
    controller._sync_memory = lambda env: None
    observed = {}

    def fake_action_craft(
        env,
        item,
        memory,
        use_crafting_table,
        use_furnace,
        craft_num,
        reclaim_crafting_table,
    ):
        observed["use_crafting_table"] = use_crafting_table
        return ["stick", "crafting table"], [4.0, 1.0]

    monkeypatch.setattr("controller.action_craft", fake_action_craft)

    assert controller._execute_craft_with_retries(
        object(),
        {
            "obj": {"stick": 4},
            "materials": {"planks": 2},
            "platform": "crafting table",
        },
        "stick",
        4,
        max_attempts=1,
    )
    assert observed["use_crafting_table"] is False


def test_table_is_kept_across_hand_craft_for_later_table_recipe():
    workflow = [
        {
            "actions": [
                {
                    "name": "craft",
                    "args": {"obj": {"stick": 4}, "platform": None},
                }
            ]
        },
        {
            "actions": [
                {
                    "name": "craft",
                    "args": {
                        "obj": {"wooden axe": 1},
                        "platform": "crafting table",
                    },
                }
            ]
        },
    ]

    assert Controller._should_keep_crafting_table_placed(workflow, 0, -1)


def test_normal_workflow_reports_failed_craft_instead_of_success(monkeypatch):
    events = _events(inventory={"planks": 3, "stick": 2, "crafting table": 1})
    controller = _controller({"planks": 3, "stick": 2, "crafting table": 1})
    controller._sync_memory = lambda env: events
    controller.check_action_preparation = lambda *args, **kwargs: {
        "feedback": "",
        "success": True,
        "suggestion": "",
    }
    controller._execute_craft_with_retries = lambda *args, **kwargs: False

    class FakeEnv:
        def step(self, _action):
            return events, 0, False, {}

    monkeypatch.setattr("controller.share_memory", lambda memory, obs: None)
    workflow = {
        "workflow": [
            {
                "times": "1",
                "actions": [
                    {
                        "name": "craft",
                        "args": {
                            "obj": {"wooden axe": 1},
                            "materials": {"planks": 3, "stick": 2},
                            "platform": "crafting table",
                        },
                    }
                ],
            }
        ]
    }

    result, underground = controller.check_and_execute_workflow(
        FakeEnv(), workflow, {"task": "wooden axe"}, False
    )

    assert result["success"] is False
    assert "not added to inventory" in result["feedback"]
    assert underground is False


def test_craft_preparation_accepts_provider_material_and_platform_names():
    events = _events(inventory={"planks": 4, "crafting table": 1})

    class FakeEnv:
        def step(self, _action):
            return events, 0, False, {}

    result = _controller().check_action_preparation(
        FakeEnv(),
        "craft",
        {
            "obj": {"fence": 3},
            "materials": {"oak_planks": 4},
            "platform": "crafting_table",
        },
        {"task": "fence"},
        events,
    )

    assert result["success"] is True


@pytest.mark.parametrize("target", ["cobblestone", "log"])
def test_acquired_target_stops_remaining_navigation_generically(target):
    controller = _controller({target: 2})
    step = {
        "actions": [
            {"name": "find", "args": {"obj": target}},
            {"name": "move_to", "args": {"obj": target}},
            {"name": "mine", "args": {"obj": target, "tool": None}},
        ]
    }

    assert controller._mine_step_already_satisfied(step, 2)
    controller.memory.inventory[target] = 1
    assert not controller._mine_step_already_satisfied(step, 2)


@pytest.mark.parametrize("block_name", ["stone", "wood"])
def test_navigation_tracks_selected_world_coordinate_without_retargeting(block_name):
    initial = _events(blocks=[((3, 0, 0), block_name)])
    selected = structured_actions.select_target_block(initial, block_name)
    moved = _events(
        position=(1.0, 60.0, 0.0),
        blocks=[((2, 0, 0), block_name), ((1, 0, 0), block_name)],
    )

    tracked = structured_actions.tracked_target_block(
        moved, selected, block_name
    )

    assert tracked["world_x"] == selected["world_x"]
    assert tracked["forward_offset"] == 2


def test_underground_state_reaches_approach_forward_movement(monkeypatch):
    events = _events(blocks=[((2, 0, 0), "stone")])
    calls = []

    monkeypatch.setattr(structured_actions, "sleep", lambda *args, **kwargs: events)
    monkeypatch.setattr(
        structured_actions,
        "try_forward",
        lambda env, memory, underground, approach=0: calls.append(
            (underground, approach)
        ) or False,
    )

    assert not structured_actions.approach(
        object(), FakeMemory(), "cobblestone", underground=True
    )
    assert calls == [(True, 1)]
