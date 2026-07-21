from __future__ import annotations

from dataclasses import replace

import pytest

from dc3pa.experiments.round5124_audit import (
    HISTORICAL_ACTIVATION_POLICY_ID,
    HISTORICAL_L2_COMMIT,
)
from dc3pa.experiments.round5124_contracts import (
    L2ProvenanceAudit,
    Round5124BootstrapPolicy,
    STANDARDIZATION_DECISION,
    StandardDevelopmentCloseout,
    StandardDevelopmentDatasetAcceptance,
    StandardIntegrityCounts,
    StandardizationDecision,
    StandardReplacementLineage,
    assert_standard_fusion_feature_names,
)
from dc3pa.experiments.development_records import load_development_record
from tests_dc3pa.round511_test_utils import make_record


def decision() -> StandardizationDecision:
    return StandardizationDecision(
        approved_by="ZYF",
        decision_text=STANDARDIZATION_DECISION,
        source_prompt_sha256="prompt-sha",
        effective_date="2026-07-21",
        all_60_units_accepted=True,
        all_681_records_accepted=True,
        no_development_rerun=True,
        standard_scientific_condition=True,
        runtime_segment_modeling=False,
        runtime_segment_is_predictive_feature=False,
        runtime_segment_is_eligibility_gate=False,
        one_frozen_runtime_required_for_holdout=True,
        model_identity_differences_ignored=True,
    ).with_id()


def integrity() -> StandardIntegrityCounts:
    return StandardIntegrityCounts(
        resolved_units=60,
        train_units=45,
        tune_units=15,
        task_successes=36,
        scientific_failures=24,
        pending_units=0,
        train_decisions=528,
        tune_decisions=153,
        failed_attempt_decision_contamination=0,
        duplicate_accepted_decision_ids=0,
        formal_memory_writes=0,
        acquisition_store_writes=0,
        evaluation_chain_calls=0,
        holdout_accesses_or_records=0,
        final_accesses_or_records=0,
        mine_sand_records=0,
        paper_memory_v5_snapshot_roots=1,
    )


def lineage() -> StandardReplacementLineage:
    return StandardReplacementLineage(
        assignment_id="dev_train:medium:mine coal ore:3",
        task="mine coal ore",
        seed="1143777324",
        role="dev_train",
        old_failed_attempt_ids=("old:attempt-0",),
        old_failed_attempt_sha256=("old-sha",),
        replacement_attempt_id="new:attempt-0",
        replacement_attempt_sha256="new-sha",
        authorization_id="authorization",
        old_failed_attempt_rows=17,
        old_failed_attempt_rows_included=0,
        resumed_accepted_rows=8,
        accepted_final_attempts=1,
        final_status="completed_success",
    ).with_id()


def acceptance() -> StandardDevelopmentDatasetAcceptance:
    return StandardDevelopmentDatasetAcceptance(
        acceptance_name="standard",
        source_commit="source",
        standardization_decision_id=decision().decision_id,
        assignment_manifest_id="assignments",
        assignment_manifest_sha256="assignment-sha",
        effective_status_sha256="status-sha",
        train_dataset_id="train-id",
        train_jsonl_sha256="train-sha",
        tune_dataset_id="tune-id",
        tune_jsonl_sha256="tune-sha",
        paper_memory_v5_release_id="memory-release",
        paper_memory_v5_snapshot_root_sha256="memory-root",
        active_taskset_release_id="taskset",
        analysis_policy_id="analysis",
        formal_log_bootstrap_policy_id="bootstrap",
        historical_runtime_segment_manifest_id="historical-segments",
        historical_runtime_segment_manifest_sha256="historical-sha",
        replacement_lineage=lineage(),
        integrity=integrity(),
        standard_scientific_condition=True,
        mixed_runtime_modeling=False,
        runtime_segment_is_predictive_feature=False,
        runtime_segment_is_eligibility_gate=False,
        holdout_opened=False,
        fusion_fitted=False,
        final_evaluation_opened=False,
        eligible=True,
    ).with_id()


def l2_audit() -> L2ProvenanceAudit:
    return L2ProvenanceAudit(
        case=2,
        source_commit=HISTORICAL_L2_COMMIT,
        source_paths=("trainer.py", "fit.py"),
        source_json_pointers=("/TrainerConfig/l2", "/argparse/--l2/default"),
        candidate_values=(1e-3,),
        loss_definition="mean_binary_negative_log_likelihood",
        regularization_definition="0.5*l2*sum(beta_j^2)",
        intercept_regularized=False,
        feature_scaling="none_features_used_on_native_0_1_scale",
        sample_weighting="equal_per_decision_record",
        development_outcomes_existed_when_frozen=False,
        numeric_value_invented=False,
        eligible_for_fit=True,
    ).with_id()


def bootstrap_policy() -> Round5124BootstrapPolicy:
    return Round5124BootstrapPolicy(
        historical_activation_policy_id=HISTORICAL_ACTIVATION_POLICY_ID,
        historical_activation_policy_sha256="policy-sha",
        primary_bootstrap_unit="task",
        secondary_sensitivity_bootstrap_unit="task_seed_run",
        decision_row_iid_bootstrap_forbidden=True,
        primary_controls_activation=True,
        secondary_can_override_activation=False,
        bootstrap_replicates=2000,
        bootstrap_seed=5102026,
        confidence_level=0.95,
        reliability_bins=10,
        noninferiority_margins={"brier": 0.01, "ece": 0.02, "nll": 0.02},
        minimum_effects={"brier": 0.005, "ece": 0.0, "nll": 0.01},
        minimum_primary_improvements=1,
        require_improvement_ci_upper_at_most_zero=True,
    ).with_id()


def test_standard_acceptance_binds_all_60_units_and_681_rows():
    item = acceptance()
    assert item.integrity.total_decisions == 681
    assert item.standard_scientific_condition
    assert not item.runtime_segment_is_eligibility_gate


def test_failed_attempt_contamination_is_rejected():
    with pytest.raises(ValueError, match="integrity failed"):
        replace(integrity(), failed_attempt_decision_contamination=1)


def test_resumed_lineage_requires_17_excluded_and_8_accepted():
    with pytest.raises(ValueError, match="accounting changed"):
        replace(lineage(), old_failed_attempt_rows_included=1, lineage_id="")


def test_runtime_segment_is_neither_feature_nor_gate():
    with pytest.raises(ValueError, match="Runtime segment"):
        replace(
            acceptance(),
            runtime_segment_is_eligibility_gate=True,
            acceptance_id="",
        )
    with pytest.raises(ValueError, match="Forbidden Fusion"):
        assert_standard_fusion_feature_names(
            ("knowledge_coverage", "runtime_segment")
        )


def test_standard_closeout_freezes_label_and_group_counts():
    item = StandardDevelopmentCloseout(
        closeout_name="closeout",
        source_commit="source",
        acceptance_id=acceptance().acceptance_id,
        development_success_rate=0.6,
        train_label_counts={"false": 80, "true": 448},
        tune_label_counts={"false": 25, "true": 128},
        train_group_count=45,
        tune_group_count=15,
        train_task_count=15,
        tune_task_count=5,
        holdout_opened=False,
        fusion_fitted=False,
        final_evaluation_opened=False,
        eligible=True,
    ).with_id()
    assert item.closeout_id


def test_l2_case_2_is_exactly_one_historical_value():
    item = l2_audit()
    assert item.case == 2
    assert item.candidate_values == (1e-3,)
    with pytest.raises(ValueError, match="one-element grid"):
        replace(item, candidate_values=(1e-4, 1e-3), audit_id="")


def test_l2_case_3_forbids_fit_and_numeric_invention():
    item = replace(
        l2_audit(),
        case=3,
        source_commit="",
        source_paths=(),
        source_json_pointers=(),
        candidate_values=(),
        eligible_for_fit=False,
        audit_id="",
    )
    assert not item.eligible_for_fit
    with pytest.raises(ValueError, match="invented"):
        replace(item, numeric_value_invented=True, audit_id="")


def test_task_bootstrap_is_primary_and_run_grouping_is_sensitivity_only():
    item = bootstrap_policy()
    assert item.primary_bootstrap_unit == "task"
    assert item.secondary_sensitivity_bootstrap_unit == "task_seed_run"
    assert not item.secondary_can_override_activation
    with pytest.raises(ValueError, match="cannot control activation"):
        replace(item, secondary_can_override_activation=True, policy_id="")


def test_effective_outcome_annotations_round_trip_without_weakening_schema():
    payload = make_record("effective-annotation").to_dict()
    payload["effective_outcome_source"] = "selected_final_attempt"
    payload["original_outcome_superseded"] = False
    assert load_development_record(payload).record_id == payload["record_id"]
    payload["unknown_reconciliation_field"] = "not-allowed"
    with pytest.raises(TypeError, match="unexpected keyword"):
        load_development_record(payload)
