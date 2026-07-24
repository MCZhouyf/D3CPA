from dataclasses import asdict

import pytest

from dc3pa.contracts import Action
from dc3pa.experiments.round513e6d2 import (
    ActionGoalOutcomeSchemaV2,
    ActionObjectSignatureRegistryV2,
    ActionGoalOutcomeV2,
    AtomicDecisionStoreV2,
    DecisionRecordV2,
    PreExecutionRecordV2,
    D1LabelFreeSceneCompatibilityAudit,
    FindObservationEvidenceContractV2,
    GAMMA_TEXT,
    SafetyTerminationPolicyV2,
    SafetyTerminationSemanticsAudit,
    action_goal_outcome_v2,
    build_label_free_scene_audit,
    canonical_sha256,
    controller_canonical_object_v2,
    find_evidence_from_telemetry_v2,
    outcome_target_canonical_object_v2,
    retrieval_canonical_object_v2,
)


def _safety_policy() -> SafetyTerminationPolicyV2:
    audit = SafetyTerminationSemanticsAudit(
        controller_source_sha256="a" * 64,
        structured_actions_source_sha256="b" * 64,
    ).with_id()
    return SafetyTerminationPolicyV2(semantics_audit_id=audit.audit_id).with_id()


def _step(**overrides):
    item = {
        "observation_index": 0,
        "observation_id": "frame-1",
        "observation_sha256": "1" * 64,
        "image_sha256": "2" * 64,
        "detector_sensor_status": "ok",
        "raw_detected_target_ids": ["wood"],
        "canonical_target_candidates": [],
        "target_position_evidence": {"forward_offset": 2},
        "visibility_flag": True,
        "line_of_sight_flag": None,
        "line_of_sight_available": False,
        "distance_estimate": 2.0,
        "distance_unit": "voxel_blocks",
        "agent_pose": {"position": [0.0, 64.0, 0.0], "yaw": 0.0, "pitch": 0.0},
        "search_frontier_progress": {"observations_recorded": 1, "frozen_budget": 120},
        "controller_step_result": "target_visible_in_voxel_volume",
        "sensor_missing": False,
        "sensor_error": "",
        "missing_sensor_fields": [],
        "spatial_relation": "within_frozen_voxel_observation_volume",
    }
    item.update(overrides)
    return item


def _telemetry(*, step=None, termination="target_visible_in_voxel_volume", exhausted=False, complete=True):
    raw = {
        "raw_requested_target": "log",
        "raw_controller_target": "wood",
        "observation_steps_v2": [step or _step()],
        "search_trace_id": "trace-1",
        "search_steps_consumed": 1,
        "search_seconds_consumed": 0.2,
        "frozen_search_budget": 120,
        "search_budget_exhausted": exhausted,
        "search_trace_complete": complete,
        "termination_reason": termination,
        "technical_failure": "",
    }
    return [{"event_type": "action_finished", "payload": {"result": {"post_state_evidence": {"find_observation": raw}}}}]


def _outcome(evidence, **overrides):
    values = {
        "controller_called": True,
        "controller_success": True,
        "controller_exception": "",
        "find_evidence": evidence,
        "task_completed": False,
        "evaluator_called": True,
        "evaluator_error": "",
        "safety_policy": _safety_policy(),
    }
    values.update(overrides)
    return action_goal_outcome_v2(**values)


def test_v2_schema_keeps_controller_action_and_goal_independent():
    schema = ActionGoalOutcomeSchemaV2().with_id()
    assert schema.chrm_primary_label == "y_action"
    assert not schema.goal_may_backfill_action
    assert not schema.controller_may_override_labels


def test_find_success_requires_direct_identity_visibility_distance_and_sensors():
    registry = ActionObjectSignatureRegistryV2().with_id()
    evidence = find_evidence_from_telemetry_v2(
        Action("find", {"obj": "tree"}), _telemetry(), registry
    )
    outcome = _outcome(evidence)
    assert outcome.y_action == 1
    assert outcome.y_goal == 0
    assert outcome.record_disposition == "accepted_scientific_action"


def test_find_complete_bounded_failure_is_zero():
    registry = ActionObjectSignatureRegistryV2().with_id()
    evidence = find_evidence_from_telemetry_v2(
        Action("find", {"obj": "iron_ore"}),
        _telemetry(
            step=_step(
                raw_detected_target_ids=["stone"],
                visibility_flag=False,
                distance_estimate=None,
                spatial_relation="",
                controller_step_result="bounded_search_budget_exhausted",
            ),
            termination="bounded_search_budget_exhausted",
            exhausted=True,
        ),
        registry,
    )
    outcome = _outcome(evidence, controller_success=False)
    assert outcome.y_action == 0
    assert outcome.failure_type == "bounded_search_exhausted"


@pytest.mark.parametrize(
    "missing",
    [
        {"visibility_flag": None},
        {"distance_estimate": None},
        {"image_sha256": ""},
        {"sensor_missing": True, "missing_sensor_fields": ["voxels"]},
    ],
)
def test_find_missing_success_evidence_remains_null(missing):
    registry = ActionObjectSignatureRegistryV2().with_id()
    evidence = find_evidence_from_telemetry_v2(
        Action("find", {"obj": "tree"}),
        _telemetry(step=_step(**missing)),
        registry,
    )
    assert _outcome(evidence).y_action is None


def test_sapling_goal_success_does_not_backfill_missing_action_evidence():
    outcome = _outcome(None, task_completed=True)
    assert (outcome.y_action, outcome.y_goal) == (None, 1)
    assert outcome.record_disposition == "audit_only_ambiguous"


def test_log_action_success_and_terminal_goal_failure_are_allowed():
    registry = ActionObjectSignatureRegistryV2().with_id()
    evidence = find_evidence_from_telemetry_v2(
        Action("find", {"obj": "tree"}), _telemetry(), registry
    )
    assert (_outcome(evidence).y_action, _outcome(evidence).y_goal) == (1, 0)


def test_final_scientific_safety_stop_is_zero_only_with_complete_evidence():
    registry = ActionObjectSignatureRegistryV2().with_id()
    evidence = find_evidence_from_telemetry_v2(
        Action("find", {"obj": "iron_ore"}),
        _telemetry(
            step=_step(
                raw_detected_target_ids=["stone"],
                visibility_flag=False,
                distance_estimate=None,
                spatial_relation="",
                controller_step_result="safety_clearance_stop",
            ),
            termination="safety_clearance_stop",
            exhausted=False,
        ),
        registry,
    )
    outcome = _outcome(evidence, controller_success=False)
    assert outcome.y_action == 0
    assert outcome.failure_type == "controller_safety_termination"


def test_recoverable_or_technical_safety_signal_is_not_scientific_zero():
    registry = ActionObjectSignatureRegistryV2().with_id()
    recoverable = find_evidence_from_telemetry_v2(
        Action("find", {"obj": "iron_ore"}),
        _telemetry(
            step=_step(raw_detected_target_ids=["stone"], visibility_flag=False, distance_estimate=None, spatial_relation=""),
            termination="safety_replan_requested",
        ),
        registry,
    )
    assert _outcome(recoverable, controller_success=False).y_action is None
    technical = _outcome(recoverable, controller_exception="SafetySensorError")
    assert technical.y_action is None
    assert technical.record_disposition == "technical_quarantine"


def test_signature_layers_share_retrieval_but_not_outcome_identity():
    registry = ActionObjectSignatureRegistryV2().with_id()
    assert controller_canonical_object_v2("tree", registry) == "wood"
    assert retrieval_canonical_object_v2("tree", registry) == retrieval_canonical_object_v2("oak_log", registry)
    assert outcome_target_canonical_object_v2("wood", registry) != outcome_target_canonical_object_v2("oak_log", registry)
    assert outcome_target_canonical_object_v2("redstone", registry) != outcome_target_canonical_object_v2("redstone_ore", registry)
    assert outcome_target_canonical_object_v2("iron_ingot", registry) != outcome_target_canonical_object_v2("iron_ore", registry)


def test_unknown_signature_fails_closed_per_layer():
    registry = ActionObjectSignatureRegistryV2().with_id()
    assert controller_canonical_object_v2("mystery", registry).startswith("unknown:controller:")
    assert retrieval_canonical_object_v2("mystery", registry).startswith("unknown:retrieval:")
    assert outcome_target_canonical_object_v2("mystery", registry).startswith("unknown:outcome:")


def test_unknown_outcome_target_cannot_create_positive_or_negative_label():
    registry = ActionObjectSignatureRegistryV2().with_id()
    telemetry = _telemetry(step=_step(raw_detected_target_ids=["mystery"]))
    telemetry[0]["payload"]["result"]["post_state_evidence"]["find_observation"]["raw_controller_target"] = "mystery"
    evidence = find_evidence_from_telemetry_v2(
        Action("find", {"obj": "mystery"}), telemetry, registry
    )
    assert _outcome(evidence).y_action is None


def test_label_free_scene_audit_reads_only_pre_action_fields():
    registry = ActionObjectSignatureRegistryV2().with_id()
    records = []
    for task, obj in (("sapling", "sapling"), ("iron ore", "iron_ore"), ("log", "tree")):
        records.append({
            "pre": {
                "action": {"name": "find", "args": {"obj": obj}},
                "binding": {"task": task},
                "environment": {
                    "compatible_pool": [],
                    "incompatible_pool": [{"exemplar_id": "x", "action_signature": "craft:stick", "score": 0.9}],
                    "coverage_positive": 0.0,
                    "coverage_negative": 1.0,
                    "contrast": None,
                    "raw_state": "unknown",
                },
            },
            "action_outcome": {"raise_if_accessed": True},
            "goal_outcome": {"raise_if_accessed": True},
        })
    audit = build_label_free_scene_audit(
        records, closeout_id="c" * 64, registry=registry
    )
    assert isinstance(audit, D1LabelFreeSceneCompatibilityAudit)
    assert all(row.conclusion == "memory_support_gap" for row in audit.rows)
    assert audit.gamma_text == GAMMA_TEXT


def test_find_contract_lists_every_required_step_field():
    contract = FindObservationEvidenceContractV2().with_id()
    assert {
        "raw_detected_target_ids",
        "canonical_target_candidates",
        "visibility_flag",
        "line_of_sight_flag",
        "distance_estimate",
        "agent_position",
        "search_frontier_progress",
        "controller_step_result",
        "sensor_missing",
        "sensor_error",
    }.issubset(contract.per_step_fields)
    assert canonical_sha256(asdict(contract))


def test_v2_atomic_store_routes_only_by_action_evidence(tmp_path):
    pre = PreExecutionRecordV2(
        record_id="a" * 64,
        binding={"diagnostic": True},
        decision_index=0,
        action={"name": "find", "args": {"obj": "sapling"}},
        subgoal="find sapling",
        raw_object_signature="find:sapling",
        controller_canonical_signature="find:sapling",
        retrieval_canonical_signature="find:minecraft:family/sapling",
        outcome_target_canonical_identity="minecraft:block/sapling",
        confidence="likely",
        failure_mode="not_visible",
        same_generation_confidence=True,
        planner_call_count=1,
        pre_state={},
        knowledge={"support": 0},
        raw_environment={"raw_state": "unknown"},
        environment={"raw_state": "unknown"},
    )
    store = AtomicDecisionStoreV2(tmp_path)
    assert store.persist_pre(pre) == "created"
    outcome = ActionGoalOutcomeV2(
        controller_status="success",
        controller_terminal_reason="preparation_satisfied_without_find_observation",
        expected_action_postcondition="minecraft:block/sapling",
        observed_action_postcondition="",
        y_action=None,
        y_action_evidence_status="incomplete_or_ambiguous_evidence",
        terminal_goal_status="success",
        y_goal=1,
        y_goal_evidence_status="evaluator_complete",
        record_disposition="audit_only_ambiguous",
    )
    record = DecisionRecordV2(
        pre=pre,
        post_state={"inventory": {"sapling": 1}},
        controller={"called": True, "success": True},
        outcome=outcome,
    )
    path = store.join_post(record)
    assert path.parent.name == "audit_only_ambiguous"
    assert not (tmp_path / "accepted_scientific_action" / f"{pre.record_id}.json").exists()
