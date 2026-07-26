import json
from pathlib import Path

import pytest

from scripts_dc3pa.audit_round513e7_d2_semantics import (
    build_decision_input,
    build_go_no_go,
    build_iron_safety_audit,
    choose_go_no_go,
    classify_action_boundary,
    classify_action_goal_relation,
    classify_safety_stop,
    future_y_action_candidate,
    run_audit,
)


def _tree_record(task: str) -> dict:
    return {
        "pre": {
            "binding": {"task": task, "terminal_task": task},
            "action": {"name": "find", "args": {"obj": "tree"}},
            "subgoal": f"Find a tree to obtain {task}s from it.",
        },
        "outcome": {
            "observed_action_postcondition": "minecraft:block/wood",
            "expected_action_postcondition": "minecraft:block/wood",
            "y_action": 1,
            "y_goal": 0,
        },
    }


def _iron_chain(**overrides: object) -> dict:
    chain = {
        "assignment": "01-iron_ore",
        "controller_terminal_reason": "safety_clearance_stop",
        "observed_local_postcondition": "",
        "search_budget_exhausted": False,
        "search_trace_complete": True,
        "sensor_complete": True,
        "technical_failure": "",
        "y_action": 0,
        "y_goal": None,
        "frozen_search_budget": 120,
        "search_steps_consumed": 120,
        "observation_step_count": 120,
        "target_directly_observed": False,
    }
    chain.update(overrides)
    return chain


def test_summary_sha_mismatch_fail_closed(tmp_path: Path) -> None:
    d2_root = tmp_path / "d2"
    d2_root.mkdir()
    (d2_root / "D2_FOLLOWUP_RESULT_SUMMARY.json").write_text(
        json.dumps({"source_commit": "not-the-frozen-summary"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="summary SHA-256 mismatch"):
        run_audit(
            repo=Path.cwd().parent,
            d2_root=d2_root,
            d1_root=tmp_path / "d1",
            output_root=tmp_path / "out",
        )


def test_tree_relation_keeps_labels_orthogonal_and_rejects_crude_equivalence() -> None:
    log_record = _tree_record("log")
    sapling_record = _tree_record("sapling")

    log_relation, log_evidence, _ = classify_action_goal_relation(log_record)
    sapling_relation, sapling_evidence, _ = classify_action_goal_relation(sapling_record)

    assert log_relation == "enabling_subgoal"
    assert "local_postcondition=minecraft:block/wood" in log_evidence
    assert log_record["outcome"]["y_action"] == 1
    assert log_record["outcome"]["y_goal"] == 0
    assert sapling_relation == "unresolved"
    assert "no_frozen_dependency_path_from_wood_to_sapling_was_bound" in sapling_evidence
    assert sapling_record["outcome"]["y_action"] == 1
    assert sapling_record["outcome"]["y_goal"] == 0


def test_action_boundary_closed_open_unknown() -> None:
    assert classify_action_boundary(
        termination_reason="safety_clearance_stop",
        local_postcondition_success=False,
        search_budget_exhausted=False,
        technical_failure="",
        search_trace_complete=True,
    ) == "closed"
    assert classify_action_boundary(
        termination_reason="safety_replan_requested",
        local_postcondition_success=False,
        search_budget_exhausted=False,
        technical_failure="",
        search_trace_complete=True,
    ) == "open"
    assert classify_action_boundary(
        termination_reason="unrecognized",
        local_postcondition_success=False,
        search_budget_exhausted=False,
        technical_failure="",
        search_trace_complete=True,
    ) == "unknown"


def test_safety_stop_policy_distinguishes_scientific_technical_and_recoverable() -> None:
    assert classify_safety_stop(
        termination_reason="safety_clearance_stop",
        search_budget_exhausted=False,
        technical_failure="",
        search_trace_complete=True,
        sensor_complete=True,
    ) == "final_scientific_safety_stop"
    assert future_y_action_candidate(
        action_boundary_closed="closed",
        safety_stop_classification="final_scientific_safety_stop",
        technical_failure="",
        sensor_complete=True,
        observed_postcondition="",
    ) == 0
    assert classify_safety_stop(
        termination_reason="safety_clearance_stop",
        search_budget_exhausted=False,
        technical_failure="sensor_error",
        search_trace_complete=True,
        sensor_complete=True,
    ) == "technical_safety_error"
    assert future_y_action_candidate(
        action_boundary_closed="closed",
        safety_stop_classification="technical_safety_error",
        technical_failure="sensor_error",
        sensor_complete=True,
        observed_postcondition="",
    ) is None
    assert classify_safety_stop(
        termination_reason="recoverable_replan_signal",
        search_budget_exhausted=False,
        technical_failure="",
        search_trace_complete=True,
        sensor_complete=True,
    ) == "recoverable_controller_signal"


def test_counterfactual_cannot_override_historical_iron_record() -> None:
    audit = build_iron_safety_audit(_iron_chain(y_action=None))

    assert audit["future_y_action_candidate"] == 0
    assert audit["historical_y_action"] is None
    assert audit["policy_counterfactual_adjudication"]["permitted_to_override_historical_record"] is False
    assert audit["historical_labels_remain_unchanged"] is True


@pytest.mark.parametrize(
    ("tree_relation", "iron_closed", "expected"),
    [
        ("enabling_subgoal", True, "G0"),
        ("enabling_subgoal", False, "G1"),
        ("unresolved", False, "G2"),
        ("unresolved", True, "G3"),
    ],
)
def test_go_no_go_states_are_deterministic(
    tree_relation: str, iron_closed: bool, expected: str
) -> None:
    tree_semantic = {"overall_relation_classification": tree_relation}
    iron_audit = {"action_boundary_closed": iron_closed}

    assert choose_go_no_go(tree_semantic, iron_audit) == expected


def test_g3_decision_input_does_not_create_blueprint_or_assignments() -> None:
    tree_semantic = {
        "overall_relation_classification": "unresolved",
        "audit_id": "tree-audit",
    }
    iron_audit = {
        "action_boundary_closed": True,
        "audit_id": "iron-audit",
    }

    decision_input = build_decision_input(tree_semantic, iron_audit)
    decision = build_go_no_go(tree_semantic, iron_audit, decision_input)

    assert decision["status"] == "G3"
    assert decision["decision_input_id"] == decision_input["decision_input_id"]
    assert decision["d3_blueprint_created"] is False
    assert decision["d3_assignments_created"] is False
    assert decision["d3_seal_created"] is False
    assert decision["provider_launch_count"] == 0
    assert decision["minedojo_launch_count"] == 0
