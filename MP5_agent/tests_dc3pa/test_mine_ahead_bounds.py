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
    # max_hits is shared across head and body instead of allowing 2 + 2 hits.
    attack_actions = [action for action in env.calls if action[5] == 3]
    assert len(attack_actions) == 2


def test_mine_ahead_returns_true_without_attacking_when_path_is_clear(monkeypatch):
    env = _StoneAheadEnv()
    env.events["voxels"]["block_name"].fill("air")
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert structured_actions.mine_ahead(env, _Memory(), max_hits=2)
    assert len(env.calls) == 1


class _BreakingPickaxeEnv(_StoneAheadEnv):
    def __init__(self):
        super().__init__()
        self.events["inventory"] = {
            "name": np.array(["stone pickaxe"], dtype=object),
            "quantity": np.array([1.0]),
        }

    def step(self, action):
        self.calls.append(list(action))
        if action[5] == 3:
            self.events["inventory"] = {
                "name": np.array(["air"], dtype=object),
                "quantity": np.array([0.0]),
            }
        return self.events, 0.0, False, {}


def test_mine_ahead_stops_as_soon_as_pickaxe_breaks(monkeypatch):
    env = _BreakingPickaxeEnv()
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert not structured_actions.mine_ahead(env, _Memory(), max_hits=12)
    attack_actions = [action for action in env.calls if action[5] == 3]
    assert len(attack_actions) == 1


class _BlockedFurnacePlacementEnv(_StoneAheadEnv):
    def __init__(self):
        super().__init__()
        self.events["location_stats"]["pos"] = np.array([0.0, 40.0, 0.0])
        self.events["inventory"] = {
            "name": np.array(["furnace", "coal", "stone pickaxe"], dtype=object),
            "quantity": np.array([1.0, 1.0, 1.0]),
        }


def test_underground_furnace_placement_is_bounded_without_tunnel_clearing(monkeypatch):
    env = _BlockedFurnacePlacementEnv()
    memory = _Memory()
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(
        structured_actions,
        "mine_ahead",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("underground furnace placement must not clear a tunnel")
        ),
    )

    names, quantities = structured_actions.action_craft(
        env, "iron_ingot", memory, False, True, craft_num=1
    )

    assert names == ["furnace", "coal", "stone pickaxe"]
    assert quantities == [1.0, 1.0, 1.0]
    assert len([action for action in env.calls if action[5] == 6]) == 8
    assert all(action[5] != 4 for action in env.calls)


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


class _UndergroundTablePlacementEnv(_StoneAheadEnv):
    def __init__(self):
        super().__init__()
        self.events["location_stats"]["pos"] = np.array([0.0, 50.0, 0.0])
        self.events["inventory"] = {
            "name": np.array(["crafting table", "cobblestone"], dtype=object),
            "quantity": np.array([1.0, 8.0]),
        }

    def step(self, action):
        self.calls.append(list(action))
        if action[5] == 6:
            # Physical placement removes the selected table from inventory.
            self.events["inventory"]["quantity"][0] = 0.0
        return self.events, 0.0, False, {}


def test_underground_crafting_places_table_before_use_and_recipe(monkeypatch):
    env = _UndergroundTablePlacementEnv()
    memory = _CraftMemory()
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    structured_actions.action_craft(
        env, "furnace", memory, True, False, craft_num=1
    )

    operation_codes = [action[5] for action in env.calls]
    placement_index = operation_codes.index(6)
    assert operation_codes.index(1) > placement_index
    assert operation_codes.index(4) > placement_index


class _UndergroundExploreEnv:
    def __init__(self):
        size = structured_actions.vradius * 2 + 3
        self.events = {
            "location_stats": {"pos": np.array([0.0, 40.0, 0.0])},
            "inventory": {
                "name": np.array(["stone pickaxe"], dtype=object),
                "quantity": np.array([1.0]),
            },
            "voxels": {"block_name": np.full((size, size, size), "stone", dtype=object)},
        }

    def step(self, _action):
        return self.events, 0.0, False, {}


def test_underground_exploration_rotates_after_blocked_heading(monkeypatch):
    env = _UndergroundExploreEnv()
    memory = _Memory()
    attempted_directions = []
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "surrounding_voxel_detect", lambda *args: False)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(structured_actions, "explore_steps", 0)

    def fake_move(_env, _memory, movedir, underground, jumpornot):
        assert underground == 1 and jumpornot == 1
        attempted_directions.append(movedir)
        if movedir == 2:
            env.events["location_stats"]["pos"][2] += 1.0
            return True
        return False

    monkeypatch.setattr(structured_actions, "move_one_block", fake_move)

    assert not structured_actions.explore_above_ground(
        env,
        {"obj": "iron ore"},
        "iron ore",
        1,
        performer=object(),
        memory=memory,
        task_information={},
        max_try_steps=1,
    )
    assert attempted_directions == [0, 1, 2]


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


class _CollectingCobblestoneEnv(_StoneAheadEnv):
    def __init__(self):
        super().__init__()
        size = structured_actions.vradius * 2 + 3
        self.events["voxels"]["block_name"] = np.full((size, size, size), "air", dtype=object)
        self.events["voxels"]["block_name"][
            structured_actions.vradius + 1, structured_actions.vradius + 1, structured_actions.vradius
        ] = "stone"
        self.events["inventory"] = {
            "name": np.array(["wooden pickaxe", "cobblestone"]),
            "quantity": np.array([1.0, 0.0]),
        }
        self._attacks = 0

    def step(self, action):
        self.calls.append(list(action))
        if action[5] == 3:
            self._attacks += 1
            self.events["inventory"]["quantity"][1] = 1.0
            self.events["voxels"]["block_name"][
                structured_actions.vradius + 1, structured_actions.vradius + 1, structured_actions.vradius
            ] = "air"
        return self.events, 0.0, False, {}


def test_underground_mine_returns_after_first_collected_target(monkeypatch):
    env = _CollectingCobblestoneEnv()
    memory = _Memory()
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(structured_actions, "mine_ahead", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not clear tunnel after collection")))

    names, quantities = structured_actions.mine("cobblestone", "wooden pickaxe", True, env, memory)

    assert names == ["wooden pickaxe", "cobblestone"]
    assert quantities == [1.0, 1.0]
    assert env._attacks == 1


def test_mine_ahead_does_not_clear_tunnel_after_active_resource_goal_is_met(monkeypatch):
    env = _StoneAheadEnv()
    memory = _Memory()
    memory._dc3pa_active_resource_goal = {"item": "cobblestone", "quantity": 11}
    env.events["inventory"] = {
        "name": np.array(["wooden pickaxe", "cobblestone"]),
        "quantity": np.array([1.0, 11.0]),
    }
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert not structured_actions.mine_ahead(env, memory, max_hits=2)
    assert all(action[5] != 3 for action in env.calls)


class _DirectionalGoUpEnv:
    def __init__(self, successful_heading=None, lateral_elevation_heading=None):
        self.successful_heading = successful_heading
        self.lateral_elevation_heading = lateral_elevation_heading
        self.heading = 0
        self.y_level = 50.0
        self.x_level = 0.0
        self.z_level = 0.0
        self.calls = []

    def _events(self):
        return {
            "location_stats": {
                "pos": np.array([self.x_level, self.y_level, self.z_level])
            },
            "inventory": {
                "name": np.array(["wooden pickaxe"]),
                "quantity": np.array([1.0]),
            },
        }

    def step(self, action):
        action = list(action)
        self.calls.append(action)
        if action[4] == 15 and action[3] == 12:
            self.heading += 1
        if action[0] == 1 and action[2] == 1:
            self.x_level += 0.15
            if self.heading == self.lateral_elevation_heading:
                self.y_level = 51.0
        if (
            action[0] == 0
            and action[2] == 1
            and self.successful_heading is not None
            and self.heading == self.successful_heading
        ):
            self.y_level = 60.0
        return self._events(), 0.0, False, {}


def test_go_up_tries_escape_headings_until_one_gains_elevation(monkeypatch):
    env = _DirectionalGoUpEnv(successful_heading=3)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert structured_actions.go_up(
        env,
        60,
        max_vertical_attempts=3,
        stalled_limit=2,
    )
    heading_turns = [action for action in env.calls if action[3:5] == [12, 15]]
    assert len(heading_turns) == 3
    assert env.y_level == 60.0


def test_go_up_exhausts_exactly_eight_headings_when_all_are_blocked(monkeypatch):
    env = _DirectionalGoUpEnv(successful_heading=None)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert not structured_actions.go_up(
        env,
        60,
        max_vertical_attempts=2,
        stalled_limit=1,
    )
    heading_turns = [action for action in env.calls if action[3:5] == [12, 15]]
    assert len(heading_turns) == 8


def test_go_up_stops_after_first_heading_retains_partial_elevation(monkeypatch):
    env = _DirectionalGoUpEnv(lateral_elevation_heading=1)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert structured_actions.go_up(
        env,
        60,
        max_vertical_attempts=2,
        stalled_limit=1,
    )
    heading_turns = [action for action in env.calls if action[3:5] == [12, 15]]
    assert len(heading_turns) == 1
    assert env.y_level == 51.0
