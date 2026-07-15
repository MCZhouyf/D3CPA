from __future__ import annotations

import pytest

from dc3pa.reliability.fusion_artifact import FusionArtifact
from dc3pa.reliability.fusion_features import FEATURE_SCHEMA_VERSION
from dc3pa.reliability.holdout_evaluation import HoldoutActivationReport
from dc3pa.reliability.paper_release import build_paper_release


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
        dataset_sha256="data",
        memory_snapshot_sha256="memory",
        confidence_artifact_id="confidence",
        created_from_commit="commit",
    ).with_id()


def _report(eligible):
    return HoldoutActivationReport(
        artifact_id=_artifact().artifact_id,
        policy_id="policy",
        protocol_id="protocol",
        holdout_dataset_sha256="holdout",
        group_count=2,
        example_count=4,
        positive_count=2,
        negative_count=2,
        comparisons={},
        candidate_metrics={},
        legacy_metrics={},
        equal_weight_metrics={},
        stratified_metrics={},
        eligible=eligible,
        eligibility_reasons=() if eligible else ("failed",),
        source_commit="commit",
    ).with_id()


def test_ineligible_report_cannot_be_frozen():
    with pytest.raises(ValueError):
        build_paper_release(
            release_name="paper",
            artifact=_artifact(),
            artifact_sha256="artifact-sha",
            report=_report(False),
            report_sha256="report-sha",
            development_protocol_id="protocol",
            activation_policy_id="policy",
            environment_parameters={"top_k": 3},
            source_commit="commit",
        )
