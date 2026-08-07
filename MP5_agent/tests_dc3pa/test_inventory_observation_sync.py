from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from utils.common_utils import (  # noqa: E402
    share_memory,
    update_memory_inventory_from_observation,
)


class _Memory:
    def __init__(self, inventory):
        self.inventory = inventory

    def update_inventory(self, inventory):
        self.inventory = inventory


def _events(names, quantities):
    return {
        "inventory": {
            "name": np.array(names, dtype=object),
            "quantity": np.array(quantities, dtype=float),
        }
    }


def test_single_empty_inventory_frame_does_not_erase_material_ledger():
    memory = _Memory({"cobblestone": 19.0, "crafting table": 1.0})

    share_memory(memory, _events(["air"], [0]))

    assert memory.inventory == {"cobblestone": 19.0, "crafting table": 1.0}


def test_two_empty_inventory_frames_confirm_a_real_empty_inventory():
    memory = _Memory({"cobblestone": 19.0})
    empty_events = _events(["air"], [0])

    share_memory(memory, empty_events)
    share_memory(memory, empty_events)

    assert memory.inventory == {}


def test_nonempty_observation_resets_empty_frame_confirmation():
    memory = _Memory({"cobblestone": 19.0})
    empty_events = _events(["air"], [0])

    share_memory(memory, empty_events)
    share_memory(memory, _events(["cobblestone"], [18]))
    share_memory(memory, empty_events)

    assert memory.inventory == {"cobblestone": 18.0}


def test_direct_inventory_observation_uses_the_same_empty_frame_guard():
    """Action helpers returning inventory arrays must not bypass share_memory."""
    memory = _Memory({"stone pickaxe": 1.0, "cobblestone": 24.0})

    assert not update_memory_inventory_from_observation(memory, {})
    assert memory.inventory == {"stone pickaxe": 1.0, "cobblestone": 24.0}

    assert update_memory_inventory_from_observation(memory, {})
    assert memory.inventory == {}
