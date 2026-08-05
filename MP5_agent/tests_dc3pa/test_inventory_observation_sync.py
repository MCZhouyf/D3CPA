from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from utils.common_utils import share_memory  # noqa: E402


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
