from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from dc3pa.experiments.round5124_fusion_data import (
    FINAL_FEATURE_ORDER,
    DirectedFusionFeatureRecord,
)
from dc3pa.experiments.round5124_fusion_fit import (
    Round5124ActivationPolicy,
    Round5124FitPolicy,
    candidate_probabilities,
    fit_candidate,
)


def fit_policy() -> Round5124FitPolicy:
    return Round5124FitPolicy(
        source_commit="source",
        pre_fusion_qualification_id="qualification",
        feature_direction_policy_id="direction",
        l2_provenance_audit_id="l2",
        l2_candidate_values=(1e-3,),
        learning_rate=0.05,
        maximum_epochs=5000,
        patience=200,
        minimum_delta=1e-8,
        initialization="zero_coefficients_prevalence_intercept",
        coefficient_projection="nonnegative_after_each_update",
        intercept_regularized=False,
        feature_scaling="none_native_0_1",
        sample_weighting="equal_per_decision_record",
        train_objective="mean_nll_plus_half_l2_sum_beta_squared",
        tune_selection_objective="minimum_tune_nll_checkpoint",
        hard_infeasible_probability=0.0,
        task_runtime_features_forbidden=True,
        holdout_path_permitted=False,
        final_evaluation_path_permitted=False,
        post_tune_redesign_permitted=False,
    ).with_id()


def activation_policy() -> Round5124ActivationPolicy:
    return Round5124ActivationPolicy(
        source_commit="source",
        bootstrap_policy_id="bootstrap",
        historical_activation_policy_id="historical",
        primary_bootstrap_unit="task",
        secondary_sensitivity_bootstrap_unit="task_seed_run",
        primary_controls_activation=True,
        secondary_can_override_activation=False,
        primary_metrics=("brier", "nll"),
        calibration_metrics=("ece",),
        noninferiority_margins={"brier": 0.01, "ece": 0.02, "nll": 0.02},
        minimum_effects={"brier": 0.005, "ece": 0.0, "nll": 0.01},
        minimum_primary_improvements=1,
        require_improvement_ci_upper_at_most_zero=True,
        bootstrap_replicates=2000,
        bootstrap_seed=5102026,
        confidence_level=0.95,
        reliability_bins=10,
        post_holdout_tuning_forbidden=True,
    ).with_id()


def record(index: int, *, role: str, label: int, feasible: bool = True):
    value = 0.15 + (index % 8) * 0.1
    features = {
        "knowledge_coverage": value,
        "knowledge_known": value,
        "confidence_probability": value,
        "environment_probability": value,
    }
    return DirectedFusionFeatureRecord(
        feature_record_id=f"{role}-{index}",
        source_decision_record_id=f"decision-{role}-{index}",
        source_decision_record_hash="decision-hash",
        source_feature_hash="source-feature-hash",
        role=role,
        group_id=f"group-{role}-{index // 2}",
        task=f"task-{index // 4}",
        seed=str(index // 2),
        decision_index=index,
        hard_feasible=feasible,
        features=features,
        label=label,
        legacy_probability=0.0 if not feasible else value,
        equal_weight_probability=0.0 if not feasible else value,
        development_input_release_id="development",
        confidence_calibration_release_id="confidence",
        environment_evidence_release_id="environment",
        paper_memory_v5_release_id="memory",
    ).with_hash()


def datasets():
    train = [
        record(i, role="dev_train", label=int(i % 3 != 0), feasible=i != 0)
        for i in range(24)
    ]
    tune = [
        record(i, role="dev_tune", label=int(i % 3 != 0), feasible=i != 0)
        for i in range(12)
    ]
    return train, tune


def test_fit_is_deterministic_nonnegative_and_uses_fixed_l2():
    train, tune = datasets()
    kwargs = dict(
        source_commit="source",
        train_records=train,
        tune_records=tune,
        fit_policy=fit_policy(),
        activation_policy=activation_policy(),
        train_dataset_sha256="train-sha",
        tune_dataset_sha256="tune-sha",
    )
    first = fit_candidate(**kwargs)
    second = fit_candidate(**kwargs)
    assert first.artifact_id == second.artifact_id
    assert first.selected_l2 == 1e-3
    assert all(value >= 0 for value in first.coefficients.values())
    assert tuple(first.coefficients) == FINAL_FEATURE_ORDER


def test_hard_infeasible_candidate_probability_is_zero():
    train, tune = datasets()
    artifact = fit_candidate(
        source_commit="source",
        train_records=train,
        tune_records=tune,
        fit_policy=fit_policy(),
        activation_policy=activation_policy(),
        train_dataset_sha256="train-sha",
        tune_dataset_sha256="tune-sha",
    )
    probabilities = candidate_probabilities(tune, artifact)
    assert probabilities[0] == 0.0
    assert np.all((probabilities >= 0.0) & (probabilities <= 1.0))


def test_fit_policy_forbids_l2_grid_invention():
    with pytest.raises(ValueError, match="fixed 1e-3"):
        replace(fit_policy(), l2_candidate_values=(1e-4, 1e-3), policy_id="")


def test_primary_bootstrap_is_task_and_sensitivity_cannot_override():
    with pytest.raises(ValueError, match="cannot control activation"):
        replace(
            activation_policy(),
            secondary_can_override_activation=True,
            policy_id="",
        )


def test_fit_command_has_no_protected_dataset_argument_or_evaluator_import():
    path = Path(__file__).parents[1] / "scripts_dc3pa" / "fit_round5124_monotonic_fusion.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any("holdout" in name for name in imported)
    text = path.read_text(encoding="utf-8")
    assert '"--holdout' not in text
    assert '"--final' not in text
