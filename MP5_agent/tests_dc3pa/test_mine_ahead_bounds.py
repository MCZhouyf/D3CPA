from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

import structured_actions  # noqa: E402


class _Memory:
    inventory = {}


class _StoneAheadEnv:
    def __init__(self):
        self.calls = []
        size = structured_actions.vradius * 2 + 3
        self.events = {
            "location_stats": {"pos": np.array([0.0, 64.0, 0.0])},
            "inventory": {
                "name": np.array(["air"]),
                "quantity": np.array([0.0]),
            },
            "voxels": {"block_name": np.full((size, size, size), "stone")},
        }

    def step(self, action):
        self.calls.append(list(action))
        return self.events, 0.0, False, {}


def test_mine_ahead_returns_false_after_finite_attack_budget(monkeypatch):
    env = _StoneAheadEnv()
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert not structured_actions.mine_ahead(env, _Memory(), max_hits=2)
    # Initial sync + 2 head hits + look + 2 body hits + restore look.
    assert len(env.calls) == 7


def test_mine_ahead_returns_true_without_attacking_when_path_is_clear(monkeypatch):
    env = _StoneAheadEnv()
    env.events["voxels"]["block_name"].fill("air")
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert structured_actions.mine_ahead(env, _Memory(), max_hits=2)
    assert len(env.calls) == 1


class _CraftMemory:
    def __init__(self):
        self.inventory = {"crafting table": 1.0, "planks": 6.0, "stick": 4.0}


class _SolidCraftEnv:
    def __init__(self):
        self.calls = []
        size = structured_actions.vradius * 2 + 3
        self.events = {
            "location_stats": {"pos": np.array([0.0, 60.0, 0.0])},
            "inventory": {
                "name": np.array(["crafting table", "planks", "stick"]),
                "quantity": np.array([1.0, 6.0, 4.0]),
            },
            "voxels": {"block_name": np.full((size, size, size), "stone")},
        }

    def step(self, action):
        self.calls.append(list(action))
        return self.events, 0.0, False, {}


def test_crafting_table_prep_aborts_in_solid_tunnel(monkeypatch):
    env = _SolidCraftEnv()
    memory = _CraftMemory()
    monkeypatch.setattr(structured_actions, "move_to_middle", lambda _env: None)
    monkeypatch.setattr(structured_actions, "move_one_block", lambda *args: None)
    monkeypatch.setattr(structured_actions, "mine_ahead", lambda *args, **kwargs: False)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    names, quantities = structured_actions.action_craft(
        env, "wooden_pickaxe", memory, True, False, craft_num=1
    )

    assert names == ["crafting table", "planks", "stick"]
    assert quantities == [1.0, 6.0, 4.0]
    # No table-use (1) nor item-craft (4) action is sent after failed prep.
    assert all(action[5] not in {1, 4} for action in env.calls)


def test_underground_mine_caps_static_target_attacks(monkeypatch):
    env = _StoneAheadEnv()
    memory = _Memory()
    size = structured_actions.vradius * 2 + 3
    env.events["voxels"]["block_name"] = np.full((size, size, size), "air", dtype=object)
    env.events["voxels"]["block_name"][
        structured_actions.vradius + 1, structured_actions.vradius + 1, structured_actions.vradius
    ] = "stone"
    env.events["inventory"] = {
        "name": np.array(["wooden pickaxe"]),
        "quantity": np.array([1.0]),
    }
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(structured_actions, "mine_ahead", lambda *args, **kwargs: False)

    structured_actions.mine("cobblestone", "wooden pickaxe", True, env, memory)

    attack_actions = [action for action in env.calls if action[5] == 3]
    assert len(attack_actions) == 12
