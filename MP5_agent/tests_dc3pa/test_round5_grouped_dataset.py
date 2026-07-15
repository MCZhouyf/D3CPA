from __future__ import annotations

import pytest

from dc3pa.reliability.fusion_dataset import (
    FusionExample,
    FusionObservationStore,
    PendingFusionObservation,
    join_observations_and_labels,
    validate_group_isolation,
)
from dc3pa.reliability.fusion_features import ReliabilityFeatureVector


def _example(group, split, step):
    return FusionExample(
        episode_id=group,
        task="task",
        seed="1",
        plan_id="plan",
        plan_version=1,
        step_id=step,
        step_index=0,
        group_id=group,
        split=split,
        label=1,
        features={
            "knowledge": 0.5,
            "model": 0.5,
            "environment": 0.5,
            "environment_coverage": 0.0,
        },
    )


def test_group_cannot_cross_train_and_validation():
    with pytest.raises(ValueError):
        validate_group_isolation(
            [_example("episode-1", "train", "a"), _example("episode-1", "validation", "b")]
        )


def test_different_groups_are_valid():
    validate_group_isolation(
        [_example("episode-1", "train", "a"), _example("episode-2", "validation", "b")]
    )


def _vector():
    return ReliabilityFeatureVector(
        hard_conflict=False,
        available=True,
        knowledge=0.5,
        model=0.5,
        environment=0.5,
        environment_coverage=0.0,
        knowledge_available=False,
        model_available=True,
        environment_status="unknown",
        confidence_artifact_id="confidence",
    )


def test_label_join_uses_plan_version_and_excludes_ambiguous_steps():
    observations = [
        PendingFusionObservation(
            episode_id="episode-1",
            task="task",
            seed="1",
            plan_id="plan",
            plan_version=1,
            step_id="same-step",
            step_index=0,
            group_id="episode-1",
            split="train",
            vector=_vector(),
        ),
        PendingFusionObservation(
            episode_id="episode-1",
            task="task",
            seed="1",
            plan_id="plan",
            plan_version=2,
            step_id="same-step",
            step_index=0,
            group_id="episode-1",
            split="train",
            vector=_vector(),
        ),
    ]
    examples, exclusions = join_observations_and_labels(
        observations,
        {("plan", 2, "same-step"): 1, ("plan", 1, "same-step"): None},
    )
    assert [(item.plan_version, item.label) for item in examples] == [(2, 1)]
    assert exclusions[0]["key"] == ("plan", 1, "same-step")


def test_pending_observation_store_is_separate_jsonl(tmp_path):
    path = tmp_path / "fusion_observations.jsonl"
    store = FusionObservationStore(path)
    store.append(
        PendingFusionObservation(
            episode_id="episode-1",
            task="task",
            seed="1",
            plan_id="plan",
            plan_version=1,
            step_id="step",
            step_index=0,
            group_id="episode-1",
            split="train",
            vector=_vector(),
        )
    )
    assert path.read_text(encoding="utf-8").count("\n") == 1
