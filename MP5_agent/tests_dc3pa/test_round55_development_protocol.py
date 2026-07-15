from __future__ import annotations

import pytest

from dc3pa.reliability.development_protocol import (
    DevelopmentProtocolManifest,
    GroupAssignment,
)


def _assign(group, role, task=None, seed=None):
    return GroupAssignment(
        group_id=group,
        task=task or group,
        seed=seed or group,
        role=role,
    )


def _manifest(assignments):
    return DevelopmentProtocolManifest(
        protocol_name="paper-dev-v1",
        assignments=tuple(assignments),
        memory_snapshot_sha256="memory",
        confidence_artifact_id="confidence",
        knowledge_impl="hard_gate_v2",
        model_confidence_impl="ordinal_calibrated",
        environment_impl="topk_v2",
        environment_scope="current_context_only",
        environment_parameters={"top_k": 3, "text_threshold": 0.5},
        activation_policy_sha256="policy",
        created_from_commit="commit",
    )


def test_three_roles_are_required_and_disjoint():
    manifest = _manifest(
        [
            _assign("train", "dev_train"),
            _assign("tune", "dev_tune"),
            _assign("holdout", "dev_holdout"),
        ]
    ).with_id()
    assert manifest.groups_for("dev_holdout") == {"holdout"}
    assert manifest.protocol_id == manifest.compute_protocol_id()


def test_task_seed_cannot_cross_roles():
    with pytest.raises(ValueError):
        _manifest(
            [
                _assign("train", "dev_train", task="same", seed="1"),
                _assign("tune", "dev_tune", task="same", seed="1"),
                _assign("holdout", "dev_holdout"),
            ]
        )
