from __future__ import annotations

from dataclasses import replace

import pytest

from dc3pa.experiments.round5124_fusion_data import (
    FINAL_FEATURE_ORDER,
    FusionFeatureDirectionPolicy,
    PreFusionQualificationReport,
    transform_raw_record,
)


def raw_record(*, unknown: bool = True, hard_feasible: bool = True):
    return {
        "feature_record_id": "feature-1",
        "source_decision_record_id": "decision-1",
        "source_decision_record_hash": "decision-hash",
        "feature_hash": "raw-feature-hash",
        "role": "dev_train",
        "group_id": "group-1",
        "task": "craft stick",
        "seed": "1",
        "decision_index": 0,
        "hard_feasible": hard_feasible,
        "knowledge_coverage": 0.75,
        "knowledge_unknown": unknown,
        "confidence_probability": 0.8,
        "environment_probability": 0.6,
        "decision_correct": True,
        "development_input_release_id": "development",
        "confidence_calibration_release_id": "confidence",
        "environment_evidence_release_id": "environment",
        "paper_memory_v5_release_id": "memory",
        "numeric_features": [0.75, 1.0 if unknown else 0.0, 0.8, 0.6],
    }


def direction_policy() -> FusionFeatureDirectionPolicy:
    return FusionFeatureDirectionPolicy(
        source_commit="source",
        raw_fusion_feature_release_id="raw-release",
        raw_train_sha256="raw-train",
        raw_tune_sha256="raw-tune",
        transformed_train_sha256="directed-train",
        transformed_tune_sha256="directed-tune",
        raw_feature_order=(
            "knowledge_coverage",
            "knowledge_unknown",
            "confidence_probability",
            "environment_probability",
        ),
        final_feature_order=FINAL_FEATURE_ORDER,
        transform="knowledge_known=1-knowledge_unknown",
        hard_feasibility_is_external_gate=True,
        train_record_count=528,
        tune_record_count=153,
        train_record_ids_preserved=True,
        tune_record_ids_preserved=True,
        train_labels_preserved=True,
        tune_labels_preserved=True,
        outcome_dependent_transform=False,
        interaction_terms_added=False,
        forbidden_predictive_features_added=False,
        legacy_baseline_definition={"successful_memory_count": 40},
        equal_weight_baseline_definition={"weight_per_feature": 0.25},
        holdout_used=False,
        final_evaluation_used=False,
    ).with_id()


def qualification() -> PreFusionQualificationReport:
    return PreFusionQualificationReport(
        source_commit="source",
        standard_acceptance_id="acceptance",
        standard_closeout_id="closeout",
        confidence_release_id="confidence",
        environment_release_id="environment",
        fusion_feature_release_id="features",
        feature_direction_policy_id=direction_policy().policy_id,
        l2_provenance_audit_id="l2",
        bootstrap_policy_id="bootstrap",
        train_rows=528,
        tune_rows=153,
        train_units=45,
        tune_units=15,
        train_tune_group_overlap=0,
        train_tune_task_seed_overlap=0,
        duplicate_feature_ids=0,
        nan_or_inf_values=0,
        missing_labels_or_features=0,
        holdout_or_final_rows=0,
        both_labels_present_train=True,
        both_labels_present_tune=True,
        all_component_release_bindings_valid=True,
        legacy_baseline_reproducible=True,
        equal_weight_baseline_reproducible=True,
        runtime_segment_is_predictive_feature=False,
        eligible=True,
    ).with_id()


def test_knowledge_unknown_is_transformed_to_adverse_direction():
    unknown = transform_raw_record(raw_record(unknown=True))
    known = transform_raw_record(raw_record(unknown=False))
    assert unknown.features["knowledge_known"] == 0.0
    assert known.features["knowledge_known"] == 1.0
    assert tuple(unknown.features) == FINAL_FEATURE_ORDER


def test_hard_infeasible_forces_both_baselines_to_zero():
    item = transform_raw_record(raw_record(hard_feasible=False))
    assert item.legacy_probability == 0.0
    assert item.equal_weight_probability == 0.0


def test_legacy_baseline_uses_frozen_memory_weight_policy():
    item = transform_raw_record(raw_record(unknown=False))
    expected = 0.4 * 0.75 + 0.2 * 0.8 + 0.4 * 0.6
    assert item.legacy_probability == pytest.approx(expected)


def test_direction_policy_rejects_forbidden_feature_addition():
    with pytest.raises(ValueError, match="forbidden information"):
        replace(
            direction_policy(),
            forbidden_predictive_features_added=True,
            policy_id="",
        )


def test_pre_fusion_qualification_requires_group_disjointness():
    with pytest.raises(ValueError, match="accounting failed"):
        replace(
            qualification(),
            train_tune_group_overlap=1,
            report_id="",
        )


def test_pre_fusion_qualification_requires_reproducible_legacy():
    with pytest.raises(ValueError, match="prerequisite failed"):
        replace(
            qualification(),
            legacy_baseline_reproducible=False,
            report_id="",
        )
