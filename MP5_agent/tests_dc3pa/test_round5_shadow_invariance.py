from __future__ import annotations

from types import SimpleNamespace

from dc3pa.reliability.fusion_artifact import FusionArtifact
from dc3pa.reliability.fusion_features import FEATURE_SCHEMA_VERSION
from dc3pa.reliability.fusion_model import (
    LogisticFusionShadowModel,
    MonotonicLogisticFusion,
)


def _artifact():
    return FusionArtifact(
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        knowledge_impl="hard_gate_v2",
        model_confidence_impl="ordinal_calibrated",
        environment_impl="topk_v2",
        environment_scope="current_context_only",
        knowledge_unknown_prior=0.5,
        environment_unknown_compatibility=0.5,
        intercept=0.0,
        coefficients={
            "knowledge": 1.0,
            "model": 1.0,
            "environment": 1.0,
            "environment_coverage": 1.0,
        },
        dataset_sha256="dataset",
        memory_snapshot_sha256="memory",
        confidence_artifact_id="confidence",
        created_from_commit="commit",
    ).with_id()


def test_shadow_calls_legacy_once_and_returns_same_object(monkeypatch):
    result = SimpleNamespace(scores={})
    calls = {"count": 0}

    class Legacy:
        def score_step(self, *args, **kwargs):
            calls["count"] += 1
            return result

    candidate = MonotonicLogisticFusion(_artifact())
    monkeypatch.setattr(
        candidate,
        "compute_from_scores",
        lambda scores: SimpleNamespace(probability=0.8),
    )
    observed = []
    wrapper = LogisticFusionShadowModel(
        Legacy(), candidate, observer=lambda legacy, computation: observed.append(computation)
    )
    returned = wrapper.score_step()
    assert returned is result
    assert calls["count"] == 1
    assert len(observed) == 1
