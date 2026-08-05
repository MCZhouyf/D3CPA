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


def test_interaction_ready_accepts_adjacent_diagonal_ore():
    target = {
        "forward_offset": 0,
        "side_offset": -1,
        "vertical_offset": 1,
    }
    assert structured_actions.interaction_ready(target, "iron ore")


def test_interaction_ready_rejects_block_more_than_one_cell_to_side():
    target = {
        "forward_offset": 0,
        "side_offset": 2,
        "vertical_offset": 1,
    }
    assert not structured_actions.interaction_ready(target, "iron ore")


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


class _LeftTopIronEnv:
    def __init__(self):
        self.calls = []
        self.left_turn_count = 0
        size = structured_actions.vradius * 2 + 3
        blocks = np.full((size, size, size), "air", dtype=object)
        blocks[
            structured_actions.vradius,
            structured_actions.vradius + 1,
            structured_actions.vradius - 1,
        ] = "iron ore"
        self.events = {
            "location_stats": {"pos": np.array([0.0, 40.0, 0.0])},
            "inventory": {
                "name": np.array(["stone pickaxe", "iron ore"], dtype=object),
                "quantity": np.array([1.0, 0.0]),
            },
            "voxels": {"block_name": blocks},
            "delta_inv": {"inc_name_by_other": np.array([], dtype=object)},
        }

    def step(self, action):
        action = list(action)
        self.calls.append(action)
        if action[3:5] == [12, 14]:
            self.left_turn_count += 1
        if action[5] == 3 and self.left_turn_count >= 3:
            self.events["inventory"]["quantity"][1] = 1.0
            self.events["voxels"]["block_name"][
                structured_actions.vradius,
                structured_actions.vradius + 1,
                structured_actions.vradius - 1,
            ] = "air"
            self.events["delta_inv"]["inc_name_by_other"] = np.array(
                ["iron ore"], dtype=object
            )
        return self.events, 0.0, False, {}


class _CenteredRayIronEnv(_LeftTopIronEnv):
    def __init__(self):
        super().__init__()
        ray_count = 24 * 24
        names = np.full(ray_count, "stone", dtype=object)
        distances = np.full(ray_count, 2.0, dtype=float)
        pitches = np.repeat(np.deg2rad(np.arange(-60, 60, 5)), 24)
        yaws = np.tile(np.deg2rad(np.arange(-60, 60, 5)), 24)
        center = np.flatnonzero(
            np.isclose(pitches, 0.0) & np.isclose(yaws, 0.0)
        )[0]
        names[center] = "iron ore"
        self.events["rays"] = {
            "block_name": names,
            "block_distance": distances,
            "ray_pitch": pitches,
            "ray_yaw": yaws,
        }

    def step(self, action):
        action = list(action)
        self.calls.append(action)
        if action[5] == 3:
            self.events["inventory"]["quantity"][1] = 1.0
            self.events["delta_inv"]["inc_name_by_other"] = np.array(
                ["iron ore"], dtype=object
            )
        return self.events, 0.0, False, {}


class _OffCenterRayIronEnv(_CenteredRayIronEnv):
    def __init__(self):
        super().__init__()
        names = self.events["rays"]["block_name"]
        pitches = self.events["rays"]["ray_pitch"]
        yaws = self.events["rays"]["ray_yaw"]
        names[:] = "stone"
        self.center = np.flatnonzero(
            np.isclose(pitches, 0.0) & np.isclose(yaws, 0.0)
        )[0]
        self.off_center = np.flatnonzero(
            np.isclose(pitches, 0.0) & np.isclose(yaws, np.deg2rad(30.0))
        )[0]
        names[self.off_center] = "iron ore"

    def step(self, action):
        action = list(action)
        self.calls.append(action)
        if action[3:5] == [12, 10]:
            names = self.events["rays"]["block_name"]
            names[self.off_center] = "stone"
            names[self.center] = "iron ore"
        if action[5] == 3 and self.events["rays"]["block_name"][self.center] == "iron ore":
            self.events["inventory"]["quantity"][1] = 1.0
            self.events["delta_inv"]["inc_name_by_other"] = np.array(
                ["iron ore"], dtype=object
            )
        return self.events, 0.0, False, {}


def test_left_top_underground_mining_turns_fully_and_restores_camera(monkeypatch):
    env = _LeftTopIronEnv()
    memory = _Memory()
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    names, quantities = structured_actions.mine(
        "iron ore", "stone pickaxe", True, env, memory
    )

    assert dict(zip(names, quantities))["iron ore"] == 1.0
    attack_index = next(i for i, action in enumerate(env.calls) if action[5] == 3)
    assert sum(action[3:5] == [12, 14] for action in env.calls[:attack_index]) == 3
    assert sum(action[3:5] == [12, 10] for action in env.calls[attack_index + 1:]) == 3


def test_underground_mining_uses_centered_lidar_before_world_axis_voxel_turn(monkeypatch):
    env = _CenteredRayIronEnv()
    memory = _Memory()
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    names, quantities = structured_actions.mine(
        "iron ore", "stone pickaxe", True, env, memory
    )

    assert dict(zip(names, quantities))["iron ore"] == 1.0
    attack_index = next(i for i, action in enumerate(env.calls) if action[5] == 3)
    assert all(action[3:5] not in ([12, 10], [12, 14]) for action in env.calls[:attack_index])


def test_underground_mining_aims_at_reachable_off_center_lidar_target(monkeypatch):
    env = _OffCenterRayIronEnv()
    memory = _Memory()
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    names, quantities = structured_actions.mine(
        "iron ore", "stone pickaxe", True, env, memory
    )

    assert dict(zip(names, quantities))["iron ore"] == 1.0
    aim_index = next(i for i, action in enumerate(env.calls) if action[3:5] == [12, 10])
    attack_index = next(i for i, action in enumerate(env.calls) if action[5] == 3)
    assert aim_index < attack_index


def test_world_space_voxel_aim_uses_current_pose_and_target_block_center():
    size = structured_actions.vradius * 2 + 3
    events = {
        "location_stats": {
            "pos": np.array([217.54549, 40.0, 246.7]),
            "yaw": np.array([168.0]),
            "pitch": np.array([0.0]),
        },
        "voxels": {"block_name": np.full((size, size, size), "air")},
    }

    action = structured_actions.camera_action_toward_voxel(
        events,
        structured_actions.vradius,
        structured_actions.vradius + 1,
        structured_actions.vradius - 1,
    )

    # This is the exact geometry from the failed iron episode: the target is
    # almost due north, so yaw should move +15 degrees, not farther negative.
    assert action[3:5] == [12, 13]


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


class _SideTunnelPitchEnv(_StoneAheadEnv):
    def __init__(self):
        super().__init__()
        self.events["inventory"] = {
            "name": np.array(["stone pickaxe"], dtype=object),
            "quantity": np.array([1.0]),
        }
        self.looking_down = False

    def step(self, action):
        action = list(action)
        self.calls.append(action)
        if action[3] == 15:
            self.looking_down = True
        elif action[3] == 9:
            self.looking_down = False
        if action[5] == 3:
            if self.looking_down:
                self.events["voxels"]["block_name"][
                    structured_actions.vradius,
                    structured_actions.vradius,
                    structured_actions.vradius - 1,
                ] = "air"
            else:
                self.events["voxels"]["block_name"][
                    structured_actions.vradius,
                    structured_actions.vradius + 1,
                    structured_actions.vradius - 1,
                ] = "air"
        return self.events, 0.0, False, {}


def test_side_tunnel_looks_down_to_clear_lower_collision_block(monkeypatch):
    env = _SideTunnelPitchEnv()
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert structured_actions.mine_ahead(env, _Memory(), direction=1, max_hits=4)
    assert [0, 0, 0, 15, 12, 0, 0, 0] in env.calls
    assert [0, 0, 0, 9, 12, 0, 0, 0] in env.calls


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
    memory = _Memory()
    memory.inventory = {"stone pickaxe": 1.0}
    memory._dc3pa_active_resource_goal = {"item": "coal", "quantity": 3}
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert not structured_actions.mine_ahead(env, memory, max_hits=12)
    attack_actions = [action for action in env.calls if action[5] == 3]
    assert len(attack_actions) == 1
    assert memory._dc3pa_execution_failure["reason"] == "tool_consumed"
    assert memory._dc3pa_execution_failure["tool"] == "stone pickaxe"
    assert memory._dc3pa_execution_failure["resource_goal"] == {
        "item": "coal",
        "quantity": 3,
    }


def test_mine_ahead_reports_planned_pickaxe_missing_at_action_boundary(monkeypatch):
    env = _StoneAheadEnv()
    env.events["location_stats"]["pos"] = np.array([4.0, 10.0, 8.0])
    memory = _Memory()
    memory.inventory = {"cobblestone": 139.0, "stick": 4.0}
    memory._dc3pa_active_resource_goal = {"item": "coal", "quantity": 3}
    memory._dc3pa_active_resource_tool = "stone pickaxe"
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert not structured_actions.mine_ahead(env, memory, max_hits=12)
    failure = memory._dc3pa_execution_failure
    assert failure["reason"] == "required_tool_missing"
    assert failure["tool"] == "stone pickaxe"
    assert failure["resource_goal"] == {"item": "coal", "quantity": 3}
    assert not [action for action in env.calls if action[5] == 3]


class _RespawnDuringTunnelMoveEnv(_StoneAheadEnv):
    def __init__(self):
        super().__init__()
        self.events["location_stats"]["pos"] = np.array([8.5, 34.0, 252.3])
        self.events["inventory"] = {
            "name": np.array(["stone pickaxe"], dtype=object),
            "quantity": np.array([1.0]),
        }

    def step(self, action):
        action = list(action)
        self.calls.append(action)
        if action[:3] == [1, 0, 0]:
            self.events["location_stats"]["pos"] = np.array([3.5, 64.0, 247.5])
            self.events["inventory"] = {
                "name": np.array(["air"], dtype=object),
                "quantity": np.array([0.0]),
            }
        return self.events, 0.0, False, {}


def test_underground_move_rejects_respawn_jump_and_requests_replan(monkeypatch):
    env = _RespawnDuringTunnelMoveEnv()
    memory = _Memory()
    memory.inventory = {"stone pickaxe": 1.0}
    memory._dc3pa_active_resource_goal = {"item": "iron ore", "quantity": 3}

    def sync_memory(target_memory, events):
        target_memory.inventory = {
            str(name).replace("_", " "): float(quantity)
            for name, quantity in zip(
                events["inventory"]["name"].tolist(),
                events["inventory"]["quantity"].tolist(),
            )
            if str(name) != "air" and quantity > 0
        }

    monkeypatch.setattr(structured_actions, "share_memory", sync_memory)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(structured_actions, "mine_ahead", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        structured_actions,
        "world_heading_turn_and_restore",
        lambda events, direction: (
            [0, 0, 0, 12, 12, 0, 0, 0],
            [0, 0, 0, 12, 12, 0, 0, 0],
            0.0,
            0,
        ),
    )

    assert not structured_actions.move_one_block(
        env, memory, movedir=0, underground=1, jumpornot=1
    )
    assert memory._dc3pa_execution_failure["reason"] == "player_respawned"
    assert memory._dc3pa_execution_failure["observed_underground"] is False
    assert memory.inventory == {}


def test_underground_move_classifies_respawn_inside_mine_ahead(monkeypatch):
    env = _RespawnDuringTunnelMoveEnv()
    memory = _Memory()
    memory.inventory = {"stone pickaxe": 1.0}
    memory._dc3pa_active_resource_goal = {"item": "iron ore", "quantity": 3}

    def sync_memory(target_memory, events):
        target_memory.inventory = {
            str(name).replace("_", " "): float(quantity)
            for name, quantity in zip(
                events["inventory"]["name"].tolist(),
                events["inventory"]["quantity"].tolist(),
            )
            if str(name) != "air" and quantity > 0
        }

    def respawn_while_clearing(_env, target_memory, *_args, **_kwargs):
        env.events["location_stats"]["pos"] = np.array([3.5, 64.0, 247.5])
        env.events["inventory"] = {
            "name": np.array(["air"], dtype=object),
            "quantity": np.array([0.0]),
        }
        target_memory._dc3pa_execution_failure = {
            "reason": "required_tool_missing",
            "observed_underground": None,
        }
        return False

    monkeypatch.setattr(structured_actions, "share_memory", sync_memory)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(structured_actions, "mine_ahead", respawn_while_clearing)
    monkeypatch.setattr(
        structured_actions,
        "world_heading_turn_and_restore",
        lambda events, direction: (
            [0, 0, 0, 12, 12, 0, 0, 0],
            [0, 0, 0, 12, 12, 0, 0, 0],
            0.0,
            0,
        ),
    )

    assert not structured_actions.move_one_block(
        env, memory, movedir=0, underground=1, jumpornot=1
    )
    failure = memory._dc3pa_execution_failure
    assert failure["reason"] == "player_respawned"
    assert failure["observed_underground"] is False
    assert "tunnel-clearance observation" in failure["feedback"]
    assert memory.inventory == {}


def test_underground_move_classifies_inventory_loss_before_coordinate_jump(monkeypatch):
    env = _RespawnDuringTunnelMoveEnv()
    memory = _Memory()
    memory.inventory = {
        "stone pickaxe": 1.0,
        "cobblestone": 34.0,
        "furnace": 1.0,
    }
    memory._dc3pa_active_resource_goal = {"item": "iron ore", "quantity": 3}

    def sync_memory(target_memory, events):
        target_memory.inventory = {
            str(name).replace("_", " "): float(quantity)
            for name, quantity in zip(
                events["inventory"]["name"].tolist(),
                events["inventory"]["quantity"].tolist(),
            )
            if str(name) != "air" and quantity > 0
        }

    def lose_inventory_while_coordinate_lags(_env, _memory, *_args, **_kwargs):
        env.events["inventory"] = {
            "name": np.array(["air"], dtype=object),
            "quantity": np.array([0.0]),
        }
        return False

    monkeypatch.setattr(structured_actions, "share_memory", sync_memory)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(
        structured_actions, "mine_ahead", lose_inventory_while_coordinate_lags
    )
    monkeypatch.setattr(
        structured_actions,
        "world_heading_turn_and_restore",
        lambda events, direction: (
            [0, 0, 0, 12, 12, 0, 0, 0],
            [0, 0, 0, 12, 12, 0, 0, 0],
            0.0,
            0,
        ),
    )

    assert not structured_actions.move_one_block(
        env, memory, movedir=0, underground=1, jumpornot=1
    )
    failure = memory._dc3pa_execution_failure
    assert failure["reason"] == "player_respawned"
    assert failure["observed_underground"] is False
    assert "complete underground inventory" in failure["feedback"]
    assert memory.inventory == {}


def test_respawn_discontinuity_helper_syncs_inventory_and_reports_phase(monkeypatch):
    env = _RespawnDuringTunnelMoveEnv()
    memory = _Memory()
    memory.inventory = {"stone pickaxe": 1.0}
    memory._dc3pa_active_resource_goal = {"item": "iron ore", "quantity": 3}
    env.events["location_stats"]["pos"] = np.array([3.5, 64.0, 247.5])
    env.events["inventory"] = {
        "name": np.array(["air"], dtype=object),
        "quantity": np.array([0.0]),
    }

    def sync_memory(target_memory, events):
        target_memory.inventory = {
            str(name).replace("_", " "): float(quantity)
            for name, quantity in zip(
                events["inventory"]["name"].tolist(),
                events["inventory"]["quantity"].tolist(),
            )
            if str(name) != "air" and quantity > 0
        }

    monkeypatch.setattr(structured_actions, "share_memory", sync_memory)

    structured_actions._record_player_respawn_failure(
        memory,
        env.events,
        np.array([11.7, 29.8, 237.2]),
        np.array([3.5, 64.0, 247.5]),
        "successive underground exploration observations",
    )

    failure = memory._dc3pa_execution_failure
    assert failure["reason"] == "player_respawned"
    assert failure["observed_underground"] is False
    assert "successive underground exploration observations" in failure["feedback"]
    assert memory.inventory == {}


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
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    names, quantities = structured_actions.action_craft(
        env, "wooden_pickaxe", memory, True, False, craft_num=1
    )

    assert names == ["crafting table", "planks", "stick"]
    assert quantities == [1.0, 6.0, 4.0]
    # No table-use (1) nor item-craft (4) action is sent after failed prep.
    assert all(action[5] not in {1, 4} for action in env.calls)


class _NoPickaxeEightHeadingTableEnv(_SolidCraftEnv):
    def __init__(self):
        super().__init__()
        self.placement_attempts = 0
        self.events["location_stats"]["pos"] = np.array([0.0, 63.0, 0.0])
        self.events["inventory"] = {
            "name": np.array(
                ["crafting table", "planks", "stick", "wooden pickaxe"],
                dtype=object,
            ),
            "quantity": np.array([1.0, 10.0, 4.0, 0.0]),
        }
        self.events["nearby_tools"] = {"table": False}

    def step(self, action):
        action = list(action)
        self.calls.append(action)
        if action[5] == 6:
            self.placement_attempts += 1
            # The front is blocked, but the second (front-left) heading has a
            # valid exposed face for physical table placement.
            if self.placement_attempts == 2:
                self.events["inventory"]["quantity"][0] = 0.0
                self.events["nearby_tools"]["table"] = True
                self.events["voxels"]["block_name"][
                    structured_actions.vradius,
                    structured_actions.vradius,
                    structured_actions.vradius - 1,
                ] = "crafting table"
        if action[5] == 4 and self.events["inventory"]["quantity"][0] == 0.0:
            self.events["inventory"]["quantity"][3] = 1.0
        return self.events, 0.0, False, {}


def test_first_pickaxe_uses_eight_heading_table_placement_without_mining(monkeypatch):
    env = _NoPickaxeEightHeadingTableEnv()
    memory = _CraftMemory()
    monkeypatch.setattr(structured_actions, "move_to_middle", lambda _env: None)
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(
        structured_actions,
        "mine_ahead",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("the first pickaxe must not require mining stone")
        ),
    )

    names, quantities = structured_actions.action_craft(
        env, "wooden_pickaxe", memory, True, False, craft_num=1
    )

    assert dict(zip(names, quantities))["wooden pickaxe"] == 1.0
    operation_codes = [action[5] for action in env.calls]
    assert operation_codes.count(6) == 2
    # Attacks after crafting recover the physical table; no attack may be
    # required before the first placement attempt.
    assert 3 not in operation_codes[: operation_codes.index(6)]


class _UndergroundTablePlacementEnv(_StoneAheadEnv):
    def __init__(self):
        super().__init__()
        self.events["location_stats"]["pos"] = np.array([0.0, 50.0, 0.0])
        self.events["inventory"] = {
            "name": np.array(["crafting table", "cobblestone"], dtype=object),
            "quantity": np.array([1.0, 8.0]),
        }
        self.events["nearby_tools"] = {"table": False}

    def step(self, action):
        self.calls.append(list(action))
        if action[5] == 6:
            # Physical placement removes the selected table from inventory.
            self.events["inventory"]["quantity"][0] = 0.0
            self.events["nearby_tools"]["table"] = True
            self.events["voxels"]["block_name"][
                structured_actions.vradius + 1,
                structured_actions.vradius,
                structured_actions.vradius,
            ] = "crafting table"
        if action[5] == 4 and self.events["nearby_tools"]["table"]:
            self.events["inventory"]["name"][0] = "furnace"
            self.events["inventory"]["quantity"][0] = 1.0
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
    assert operation_codes.index(4) > placement_index
    assert 1 not in operation_codes


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
    monkeypatch.setattr(structured_actions, "direction", 0)

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


def test_underground_exploration_keeps_successful_heading(monkeypatch):
    env = _UndergroundExploreEnv()
    memory = _Memory()
    attempted_directions = []
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "surrounding_voxel_detect", lambda *args: False)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(structured_actions, "explore_steps", 0)
    monkeypatch.setattr(structured_actions, "direction", 0)

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
        max_try_steps=2,
    )
    assert attempted_directions == [0, 1, 2, 2]


class _DirectionalMoveEnv(_UndergroundExploreEnv):
    def __init__(self):
        super().__init__()
        self.calls = []

    def step(self, action):
        self.calls.append(list(action))
        if action[0] == 1:
            self.events["location_stats"]["pos"][2] += 0.25
        return self.events, 0.0, False, {}


def test_backward_underground_move_mines_requested_direction_once_and_uses_real_displacement(monkeypatch):
    env = _DirectionalMoveEnv()
    memory = _Memory()
    mine_directions = []
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(
        structured_actions,
        "mine_ahead",
        lambda _env, _memory, direction=0: mine_directions.append(direction) or True,
    )

    assert structured_actions.move_one_block(env, memory, 3, 1, 1)
    assert mine_directions == [3]
    assert len([action for action in env.calls if action[0] == 1]) == 4
    # -180 and +180 are the same heading; the normalized encoder chooses bin 0
    # for both the turn and its inverse restore.
    assert env.calls.count([0, 0, 0, 12, 0, 0, 0, 0]) == 2


def test_lateral_underground_move_checks_the_same_world_direction_it_mines(monkeypatch):
    env = _DirectionalMoveEnv()
    memory = _Memory()
    mine_directions = []
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(
        structured_actions,
        "mine_ahead",
        lambda _env, _memory, direction=0: mine_directions.append(direction) or True,
    )

    assert structured_actions.move_one_block(env, memory, 1, 1, 1)
    assert mine_directions == [1]
    assert [0, 0, 0, 12, 6, 0, 0, 0] in env.calls
    assert [0, 0, 0, 12, 18, 0, 0, 0] in env.calls
    assert env.calls.index([0, 0, 0, 12, 6, 0, 0, 0]) < env.calls.index(
        [0, 0, 0, 12, 18, 0, 0, 0]
    )


class _YawAwareSideTunnelEnv(_SideTunnelPitchEnv):
    def __init__(self):
        super().__init__()
        # Simulate a 45-degree yaw leaked by an earlier placement/escape
        # action.  A fixed -90-degree turn would miss the world-left tunnel.
        self.yaw = -45.0
        self.events["location_stats"]["yaw"] = np.array([self.yaw])

    def step(self, action):
        action = list(action)
        self.calls.append(action)
        self.yaw = (
            (self.yaw + (action[4] - 12) * 15.0 + 180.0) % 360.0
        ) - 180.0
        self.events["location_stats"]["yaw"][0] = self.yaw
        if action[3] == 15:
            self.looking_down = True
        elif action[3] == 9:
            self.looking_down = False
        facing_world_left = abs(abs(self.yaw) - 180.0) < 1e-6
        if action[5] == 3 and facing_world_left:
            y_index = (
                structured_actions.vradius
                if self.looking_down
                else structured_actions.vradius + 1
            )
            self.events["voxels"]["block_name"][
                structured_actions.vradius,
                y_index,
                structured_actions.vradius - 1,
            ] = "air"
        if action[0] == 1 and facing_world_left:
            self.events["location_stats"]["pos"][2] -= 0.2
        return self.events, 0.0, False, {}


def test_left_move_attack_heading_clearance_check_and_displacement_agree(monkeypatch):
    env = _YawAwareSideTunnelEnv()
    memory = _Memory()
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    start_z = float(env.events["location_stats"]["pos"][2])
    assert structured_actions.move_one_block(env, memory, 1, 1, 1)
    assert float(env.events["location_stats"]["pos"][2]) <= start_z - 0.45
    assert env.yaw == -45.0
    assert [0, 0, 0, 12, 3, 0, 0, 0] in env.calls
    assert [0, 0, 0, 12, 21, 0, 0, 0] in env.calls


def test_eight_heading_recovery_stops_after_first_viable_diagonal(monkeypatch):
    env = _DirectionalMoveEnv()
    memory = _Memory()
    attempted_directions = []
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(
        structured_actions,
        "mine_ahead",
        lambda _env, _memory, direction=0, max_hits=12: (
            attempted_directions.append(direction) or direction == 4
        ),
    )

    assert structured_actions.recover_through_eight_underground_headings(
        env, memory
    )
    assert attempted_directions == [0, 4]
    assert [0, 0, 0, 12, 9, 0, 0, 0] in env.calls
    assert [0, 0, 0, 12, 15, 0, 0, 0] in env.calls
    assert env.calls.index([0, 0, 0, 12, 9, 0, 0, 0]) < env.calls.index(
        [0, 0, 0, 12, 15, 0, 0, 0]
    )


def test_approach_preserves_underground_mode_when_moving_toward_visible_ore(monkeypatch):
    events = {"location_stats": {"pos": np.array([0.0, 40.0, 0.0])}}
    targets = iter(
        [
            {"forward_offset": 2, "side_offset": 0, "vertical_offset": 0},
            {"forward_offset": 2, "side_offset": 0, "vertical_offset": 0},
            {"forward_offset": 1, "side_offset": 0, "vertical_offset": 0},
        ]
    )
    forward_calls = []
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: events)
    monkeypatch.setattr(
        structured_actions,
        "select_target_block",
        lambda _events, _target: next(targets),
    )
    monkeypatch.setattr(
        structured_actions,
        "interaction_ready",
        lambda target, _object: target["forward_offset"] == 1,
    )
    # Merely being inside the nominal lidar reach must not short-circuit the
    # physical approach while the target is still two voxels away.
    monkeypatch.setattr(
        structured_actions,
        "lidar_target_is_reachable",
        lambda _events, _object: True,
    )
    monkeypatch.setattr(
        structured_actions,
        "try_forward",
        lambda _env, _memory, underground, approach=0: (
            forward_calls.append((underground, approach)) or True
        ),
    )

    assert structured_actions.approach(object(), _Memory(), "iron ore", 1)
    assert forward_calls == [(1, 1)]


def test_underground_move_never_walks_after_failed_tunnel_clear(monkeypatch):
    env = _DirectionalMoveEnv()
    memory = _Memory()
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)
    monkeypatch.setattr(structured_actions, "mine_ahead", lambda *args, **kwargs: False)

    assert not structured_actions.move_one_block(env, memory, 3, 1, 1)
    assert all(action[0] != 1 for action in env.calls)


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
    assert len(attack_actions) == 36


class _SlowCollectingCobblestoneEnv(_StoneAheadEnv):
    def __init__(self):
        super().__init__()
        size = structured_actions.vradius * 2 + 3
        self.events["voxels"]["block_name"] = np.full(
            (size, size, size), "air", dtype=object
        )
        self.events["voxels"]["block_name"][
            structured_actions.vradius + 1,
            structured_actions.vradius + 1,
            structured_actions.vradius,
        ] = "stone"
        self.events["inventory"] = {
            "name": np.array(["wooden pickaxe", "cobblestone"], dtype=object),
            "quantity": np.array([1.0, 0.0]),
        }
        self.events["delta_inv"] = {
            "inc_name_by_other": np.array([], dtype=object)
        }
        self._attacks = 0

    def step(self, action):
        action = list(action)
        self.calls.append(action)
        if action[5] == 3:
            self._attacks += 1
            if self._attacks == 20:
                self.events["inventory"]["quantity"][1] = 1.0
                self.events["delta_inv"]["inc_name_by_other"] = np.array(
                    ["cobblestone"], dtype=object
                )
        return self.events, 0.0, False, {}


def test_underground_resource_mine_allows_slow_physical_break(monkeypatch):
    env = _SlowCollectingCobblestoneEnv()
    memory = _Memory()
    monkeypatch.setattr(structured_actions, "share_memory", lambda *args: None)
    monkeypatch.setattr(structured_actions, "sleep", lambda _env: env.events)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    names, quantities = structured_actions.mine(
        "cobblestone", "wooden pickaxe", True, env, memory
    )

    assert dict(zip(names, quantities))["cobblestone"] == 1.0
    assert len([action for action in env.calls if action[5] == 3]) == 20


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
        self.yaw_degrees = 0
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
        if action[3] == 12:
            self.yaw_degrees = (
                self.yaw_degrees + (action[4] - 12) * 15
            ) % 360
            self.heading = int(round(self.yaw_degrees / 45.0)) % 8
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
    assert env.yaw_degrees == 0


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
    assert env.yaw_degrees == 0


def test_go_up_does_not_report_success_for_partial_elevation(monkeypatch):
    env = _DirectionalGoUpEnv(lateral_elevation_heading=1)
    monkeypatch.setattr(structured_actions, "save_rgb_for_video", lambda _events: None)

    assert not structured_actions.go_up(
        env,
        60,
        max_vertical_attempts=2,
        stalled_limit=1,
    )
    heading_turns = [action for action in env.calls if action[3:5] == [12, 15]]
    assert len(heading_turns) == 8
    assert env.y_level == 51.0
    assert env.yaw_degrees == 0
