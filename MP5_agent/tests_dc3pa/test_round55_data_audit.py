from __future__ import annotations

from dc3pa.reliability.data_audit import DataSufficiencyPolicy, audit_role
from dc3pa.reliability.fusion_dataset import FusionExample


def _example(index, label):
    return FusionExample(
        episode_id=str(index),
        task=f"task-{index % 2}",
        seed=str(index),
        plan_id=f"plan-{index}",
        plan_version=1,
        step_id=f"step-{index}",
        step_index=0,
        group_id=f"group-{index}",
        split="train",
        label=label,
        features={
            "knowledge": 0.5,
            "model": 0.5,
            "environment": 0.5,
            "environment_coverage": 0.5,
        },
        metadata={
            "difficulty": "medium",
            "environment_status": "matched" if index % 2 else "unknown",
        },
    )


def test_audit_detects_missing_negative_examples():
    policy = DataSufficiencyPolicy(
        minimum_examples_per_role={"dev_train": 4},
        minimum_positive_per_role={"dev_train": 2},
        minimum_negative_per_role={"dev_train": 1},
        minimum_groups_per_role={"dev_train": 2},
        minimum_tasks_per_role={"dev_train": 2},
        required_metadata_strata={
            "environment_status": ("matched", "unknown"),
        },
    )
    result = audit_role(
        [_example(i, 1) for i in range(4)],
        role="dev_train",
        policy=policy,
    )
    assert not result.eligible
    assert any("negative" in reason for reason in result.reasons)
