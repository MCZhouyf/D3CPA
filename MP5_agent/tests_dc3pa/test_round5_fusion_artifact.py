from __future__ import annotations

import json

import pytest

from dc3pa.reliability.fusion_artifact import FusionArtifact
from dc3pa.reliability.fusion_features import FEATURE_SCHEMA_VERSION


def _artifact(**updates):
    payload = dict(
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        knowledge_impl="hard_gate_v2",
        model_confidence_impl="ordinal_calibrated",
        environment_impl="topk_v2",
        environment_scope="current_context_only",
        knowledge_unknown_prior=0.5,
        environment_unknown_compatibility=0.5,
        intercept=-0.1,
        coefficients={
            "knowledge": 1.0,
            "model": 2.0,
            "environment": 0.5,
            "environment_coverage": 0.25,
        },
        dataset_sha256="dataset",
        memory_snapshot_sha256="memory",
        confidence_artifact_id="confidence",
        created_from_commit="commit",
    )
    payload.update(updates)
    return FusionArtifact(**payload)


def test_artifact_id_is_deterministic():
    assert _artifact().with_id().artifact_id == _artifact().with_id().artifact_id


def test_negative_coefficient_is_rejected():
    with pytest.raises(ValueError):
        _artifact(
            coefficients={
                "knowledge": -0.1,
                "model": 1.0,
                "environment": 1.0,
                "environment_coverage": 1.0,
            }
        )


def test_runtime_binding_mismatch_is_rejected():
    artifact = _artifact().with_id()
    with pytest.raises(ValueError):
        artifact.validate_runtime(
            knowledge_impl="hard_gate_v2",
            model_confidence_impl="ordinal_calibrated",
            environment_impl="topk_v2",
            environment_scope="current_context_only",
            memory_snapshot_sha256="other-memory",
            confidence_artifact_id="confidence",
        )
