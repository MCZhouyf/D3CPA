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
