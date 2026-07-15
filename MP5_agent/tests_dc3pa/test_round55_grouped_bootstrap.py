from __future__ import annotations

from dc3pa.reliability.activation_policy import ActivationPolicy
from dc3pa.reliability.fusion_artifact import FusionArtifact
from dc3pa.reliability.fusion_dataset import FusionExample
from dc3pa.reliability.fusion_features import FEATURE_SCHEMA_VERSION
from dc3pa.reliability.holdout_evaluation import evaluate_holdout


def _artifact():
    return FusionArtifact(
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        knowledge_impl="hard_gate_v2",
        model_confidence_impl="ordinal_calibrated",
        environment_impl="topk_v2",
        environment_scope="current_context_only",
        knowledge_unknown_prior=0.5,
        environment_unknown_compatibility=0.5,
        intercept=-3.0,
        coefficients={
            "knowledge": 1.5,
            "model": 2.0,
            "environment": 1.5,
            "environment_coverage": 0.5,
        },
        dataset_sha256="train-tune",
        memory_snapshot_sha256="memory",
        confidence_artifact_id="confidence",
        created_from_commit="commit",
    ).with_id()


def _example(index, label, task):
    value = 0.9 if label else 0.1
    return FusionExample(
        episode_id=f"episode-{index}",
        task=task,
        seed=str(index),
        plan_id=f"plan-{index}",
        plan_version=1,
        step_id=f"step-{index}",
        step_index=0,
        group_id=f"group-{index}",
        split="test",
        label=label,
        features={
            "knowledge": value,
            "model": value,
            "environment": value,
            "environment_coverage": value,
        },
        legacy_probability=0.5,
        metadata={"difficulty": "medium", "goal_status": "experience_covered"},
    )


def _policy():
    return ActivationPolicy(
        policy_name="test",
        noninferiority_margins={"brier": 0.02, "nll": 0.05, "ece": 0.05},
        primary_metrics=("brier", "nll"),
        calibration_metrics=("ece",),
        minimum_primary_improvements=1,
        minimum_effects={"brier": 0.0, "nll": 0.0, "ece": 0.0},
        bootstrap_replicates=200,
        bootstrap_seed=3,
        bootstrap_grouping="task",
    ).with_id()


def test_grouped_bootstrap_is_deterministic():
    examples = [
        _example(index, int(index % 2 == 0), f"task-{index % 4}")
        for index in range(40)
    ]
    first = evaluate_holdout(
        examples,
        artifact=_artifact(),
        policy=_policy(),
        protocol_id="protocol",
        source_commit="commit",
    )
    second = evaluate_holdout(
        examples,
        artifact=_artifact(),
        policy=_policy(),
        protocol_id="protocol",
        source_commit="commit",
    )
    assert first.report_id == second.report_id
    assert first.group_count == 4
    assert first.comparisons["brier"].ci_upper == second.comparisons["brier"].ci_upper
