from __future__ import annotations

from tests_dc3pa.helpers_stage6_cobblestone import (
    ACCEPT_CONFLICT_SCENARIO,
    GOAL_FALSE_SCENARIO,
    HAPPY_PATH_SCENARIO,
    run_controlled_cobblestone_scenario,
    stable_projection,
    validate_accept_conflict_payload,
    validate_goal_false_payload,
    validate_happy_payload,
)


def test_stage6_controlled_cobblestone_happy_path(tmp_path):
    payload = run_controlled_cobblestone_scenario(
        tmp_path / "happy",
        scenario=HAPPY_PATH_SCENARIO,
    )
    validate_happy_payload(payload)


def test_stage6_controlled_cobblestone_is_repeatable_across_fresh_roots(tmp_path):
    first = run_controlled_cobblestone_scenario(
        tmp_path / "run_a",
        scenario=HAPPY_PATH_SCENARIO,
    )
    second = run_controlled_cobblestone_scenario(
        tmp_path / "run_b",
        scenario=HAPPY_PATH_SCENARIO,
    )
    validate_happy_payload(first)
    validate_happy_payload(second)
    assert stable_projection(first) == stable_projection(second)


def test_stage6_controlled_cobblestone_blocks_accepted_hard_conflict(tmp_path):
    payload = run_controlled_cobblestone_scenario(
        tmp_path / "accept_conflict",
        scenario=ACCEPT_CONFLICT_SCENARIO,
    )
    validate_accept_conflict_payload(payload)


def test_stage6_controlled_cobblestone_goal_false_writes_no_memory(tmp_path):
    payload = run_controlled_cobblestone_scenario(
        tmp_path / "goal_false",
        scenario=GOAL_FALSE_SCENARIO,
    )
    validate_goal_false_payload(payload)
