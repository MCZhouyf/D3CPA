from dataclasses import dataclass
from pathlib import Path

import pytest

from dc3pa.contracts import Action
from dc3pa.experiments.round513_instrumentation import (
    BilateralEvidenceV4_1,
    BilateralMatchV4_1,
    ControllerReceiptV4_1,
    StateEvidenceV4_1,
)
from dc3pa.experiments.round513e5 import (
    ActionTransitionOutcomeV4_1_3,
    AtomicDecisionStoreV4_1_3,
    DecisionRecordV4_1_3,
    FindObservationEvidenceV4_1_3,
    GAMMA_CANDIDATE_B,
    GAMMA_TEXT,
    canonical_action_signature_v4_1_3,
    canonicalize_bilateral_evidence_v4_1_3,
    canonicalize_object_v4_1_3,
    action_outcome_v4_1_3,
    terminal_goal_outcome_v4_1_3,
)


def _state() -> StateEvidenceV4_1:
    return StateEvidenceV4_1(inventory={})


def _controller(success: bool = True) -> ControllerReceiptV4_1:
    return ControllerReceiptV4_1(
        called=True,
        success=success,
        return_payload={"success": success},
        elapsed_steps=0,
        elapsed_seconds=0.0,
    )


def _find_evidence(**overrides) -> FindObservationEvidenceV4_1_3:
    values = {
        "raw_requested_target": "log",
        "canonical_requested_target": "minecraft:block/log_source",
        "observation_frame_ids": ("frame-1",),
        "visible_candidate_ids": ("wood",),
        "canonical_candidate_ids": ("minecraft:block/log_source",),
        "target_identity_matched": True,
        "target_visible": True,
        "target_distance": 2.0,
        "spatial_relation": "within_frozen_voxel_observation_volume",
        "search_trace_id": "trace-1",
        "search_steps_consumed": 1,
        "search_seconds_consumed": 0.2,
        "frozen_search_budget": 120,
        "search_budget_exhausted": False,
        "search_trace_complete": True,
        "termination_reason": "target_visible_in_voxel_volume",
    }
    values.update(overrides)
    return FindObservationEvidenceV4_1_3(**values)


def test_find_success_requires_identity_visibility_and_frozen_spatial_relation():
    outcome = action_outcome_v4_1_3(
        action=Action("find", {"obj": "log"}),
        pre=_state(),
        post=_state(),
        controller=_controller(),
        find_evidence=_find_evidence(),
    )
    assert outcome.action_outcome_status == "success"
    assert outcome.y_action == 1


def test_find_complete_bounded_exhaustion_is_scientific_failure():
    outcome = action_outcome_v4_1_3(
        action=Action("find", {"obj": "iron ore"}),
        pre=_state(),
        post=_state(),
        controller=_controller(False),
        find_evidence=_find_evidence(
            raw_requested_target="iron ore",
            canonical_requested_target="minecraft:block/iron_ore",
            visible_candidate_ids=("stone",),
            canonical_candidate_ids=("minecraft:block/stone",),
            target_identity_matched=False,
            target_visible=False,
            target_distance=None,
            spatial_relation="",
            search_steps_consumed=120,
            search_budget_exhausted=True,
            termination_reason="bounded_search_budget_exhausted",
        ),
    )
    assert outcome.action_outcome_status == "scientific_failure"
    assert outcome.y_action == 0


def test_controller_success_without_find_evidence_remains_ambiguous():
    outcome = action_outcome_v4_1_3(
        action=Action("find", {"obj": "sapling"}),
        pre=_state(),
        post=_state(),
        controller=_controller(True),
        find_evidence=None,
    )
    assert outcome.action_outcome_status == "ambiguous_unobservable"
    assert outcome.y_action is None


def test_goal_success_does_not_override_ambiguous_sapling_action():
    action_outcome = action_outcome_v4_1_3(
        action=Action("find", {"obj": "sapling"}),
        pre=_state(),
        post=_state(),
        controller=_controller(True),
    )
    goal_outcome = terminal_goal_outcome_v4_1_3(
        task_completed=True,
        evaluator_called=True,
        evaluator_error="",
        terminal_state_hash=_state().state_hash,
    )
    assert action_outcome.y_action is None
    assert goal_outcome.goal_outcome_status == "success"
    assert goal_outcome.y_goal == 1


def test_controller_failure_does_not_override_verified_action_success():
    outcome = action_outcome_v4_1_3(
        action=Action("find", {"obj": "log"}),
        pre=_state(),
        post=_state(),
        controller=_controller(False),
        find_evidence=_find_evidence(),
    )
    assert outcome.action_outcome_status == "success"
    assert outcome.evidence["controller_success"] is False


def test_goal_not_checked_is_unresolved_not_failure():
    goal = terminal_goal_outcome_v4_1_3(
        task_completed=False,
        evaluator_called=False,
        evaluator_error="",
        terminal_state_hash=_state().state_hash,
    )
    assert goal.goal_outcome_status == "unresolved"
    assert goal.y_goal is None


@pytest.mark.parametrize("raw", ["tree", "wood", "log", "oak_log"])
def test_log_source_action_aliases_have_provenance(raw: str):
    item = canonicalize_object_v4_1_3(
        raw,
        source_role="planner_target",
        action_family="find",
    )
    assert item.canonical_signature == "minecraft:block/log_source"
    assert item.normalization_rule_id != "unknown.fail_closed"


def test_ore_products_and_source_blocks_are_not_conflated():
    redstone = canonicalize_object_v4_1_3("redstone", source_role="task_target")
    redstone_ore = canonicalize_object_v4_1_3("redstone ore", source_role="task_target")
    iron_ore = canonicalize_object_v4_1_3("iron ore", source_role="task_target")
    iron_ingot = canonicalize_object_v4_1_3("iron ingot", source_role="task_target")
    assert redstone.canonical_signature != redstone_ore.canonical_signature
    assert iron_ore.canonical_signature != iron_ingot.canonical_signature


def test_unknown_alias_fails_closed():
    unknown = canonicalize_object_v4_1_3(
        "mystery mineral",
        source_role="planner_target",
        action_family="find",
    )
    assert unknown.canonical_signature == "unknown:mystery_mineral"
    assert unknown.normalization_rule_id == "unknown.fail_closed"


def test_action_lineage_preserves_all_raw_targets():
    lineage = canonical_action_signature_v4_1_3(
        Action("find", {"obj": "tree"}),
        raw_task_target="log",
        raw_controller_target="wood",
        raw_scene_target="oak_log",
    )
    assert lineage.raw_task_target == "log"
    assert lineage.raw_planner_target == "tree"
    assert lineage.raw_controller_target == "wood"
    assert lineage.raw_scene_target == "oak_log"
    assert lineage.canonical_action_signature == "find:minecraft:block/log_source"


def test_canonical_retrieval_repartitions_only_metadata_and_preserves_scores():
    evidence = BilateralEvidenceV4_1(
        query_observation_id="obs",
        query_observation_hash="hash",
        action_signature="find:cobblestone",
        compatible_pool=(),
        incompatible_pool=(
            BilateralMatchV4_1("near", "find:stone", 0.9),
            BilateralMatchV4_1("other", "find:iron_ore", 0.8),
        ),
        positive=(),
        negative=(BilateralMatchV4_1("near", "find:stone", 0.9),),
        coverage_positive=0.0,
        coverage_negative=1 / 3,
        contrast=None,
        raw_state="unknown",
    )
    result = canonicalize_bilateral_evidence_v4_1_3(
        evidence,
        action=Action("find", {"obj": "cobblestone"}),
    )
    assert [item.exemplar_id for item in result.compatible_pool] == ["near"]
    assert {item.exemplar_id for item in result.negative}.isdisjoint(
        item.exemplar_id for item in result.positive
    )
    before_scores = {item.exemplar_id: item.score for item in evidence.incompatible_pool}
    after_scores = {
        item.exemplar_id: item.score
        for item in (*result.compatible_pool, *result.incompatible_pool)
    }
    assert after_scores == before_scores
    assert GAMMA_CANDIDATE_B == "0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f"
    assert GAMMA_TEXT == ("1.0", "-0.01040883", "0.00744657")


def test_stage6_exposes_v413_as_an_explicit_opt_in():
    from scripts_dc3pa.stage6_run_minecraft import build_parser

    action = next(
        item
        for item in build_parser()._actions
        if item.dest == "round513e5_diagnostic_contracts"
    )
    assert action.default is False


@dataclass(frozen=True)
class _Pre:
    record_id: str

    def to_dict(self):
        return {"record_id": self.record_id}


@pytest.mark.parametrize(
    ("status", "value", "directory"),
    [
        ("success", 1, "accepted_scientific"),
        ("scientific_failure", 0, "accepted_scientific"),
        ("ambiguous_unobservable", None, "audit_only_ambiguous"),
        ("technical_failure", None, "technical_quarantine"),
    ],
)
def test_atomic_store_uses_action_outcome_only(
    tmp_path: Path,
    status: str,
    value: int | None,
    directory: str,
):
    record_id = {"success": "a", "scientific_failure": "b", "ambiguous_unobservable": "c", "technical_failure": "d"}[status] * 64
    pre = _Pre(record_id)
    store = AtomicDecisionStoreV4_1_3(tmp_path)
    assert store.persist_pre(pre) == "created"
    action = ActionTransitionOutcomeV4_1_3(
        status,
        value,
        "postcondition",
        ("action-evidence",),
        {},
    )
    goal = terminal_goal_outcome_v4_1_3(
        task_completed=True,
        evaluator_called=True,
        evaluator_error="",
        terminal_state_hash=_state().state_hash,
    )
    record = DecisionRecordV4_1_3(
        pre=pre,
        post_state=_state(),
        controller=_controller(True),
        controller_evidence_ids=("controller-evidence",),
        action_outcome=action,
        goal_outcome=goal,
        engineering_only=True,
        formal_fitting_eligible=False,
    )
    path = store.join_post(record)
    assert path.parent.name == directory
    assert not (tmp_path / "incomplete_pending" / f"{record_id}.json").exists()
