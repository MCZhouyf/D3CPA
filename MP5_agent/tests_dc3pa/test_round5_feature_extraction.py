from __future__ import annotations

import pytest

from dc3pa.reliability.contracts import DimensionScore
from dc3pa.reliability.fusion_features import (
    FeatureExtractionPolicy,
    extract_reliability_features,
)


def _scores(*, hard=False, knowledge=True, model=True, environment="matched"):
    knowledge_score = (
        DimensionScore(
            dimension="knowledge",
            probability=0.8,
            available=True,
            evidence={"knowledge_v2": {"coverage": 0.8}},
            hard_conflict=hard,
        )
        if knowledge
        else DimensionScore.unavailable("knowledge", "unknown")
    )
    model_score = (
        DimensionScore(
            dimension="model",
            probability=0.7,
            available=True,
            evidence={
                "decision_probability_source": "calibrated",
                "calibration_artifact_id": "confidence-artifact",
            },
        )
        if model
        else DimensionScore.unavailable("model", "provider failed")
    )
    if environment == "matched":
        environment_score = DimensionScore(
            dimension="environment",
            probability=0.6,
            available=True,
            evidence={"status": "matched", "coverage": 0.9},
        )
    elif environment == "mismatch":
        environment_score = DimensionScore(
            dimension="environment",
            probability=0.1,
            available=True,
            evidence={"status": "mismatch", "coverage": 0.9},
        )
    elif environment == "unknown":
        environment_score = DimensionScore.unavailable(
            "environment",
            "unknown",
            evidence={
                "status": "unknown",
                "coverage": 0.0,
                "neutral_compatibility_for_future_fusion": 0.5,
            },
        )
    else:
        environment_score = DimensionScore.unavailable(
            "environment",
            "encoder failure",
            evidence={"status": "technical_unavailable", "coverage": 0.0},
        )
    return {
        "knowledge": knowledge_score,
        "model": model_score,
        "environment": environment_score,
    }


def test_unknown_knowledge_and_environment_use_neutral_priors():
    vector = extract_reliability_features(
        _scores(knowledge=False, environment="unknown"),
        policy=FeatureExtractionPolicy(
            require_calibrated_model=True,
            require_environment_v2=True,
        ),
    )
    assert vector.available
    assert vector.knowledge == 0.5
    assert vector.environment == 0.5
    assert vector.environment_coverage == 0.0


def test_mismatch_preserves_low_compatibility_and_high_coverage():
    vector = extract_reliability_features(
        _scores(environment="mismatch"),
        policy=FeatureExtractionPolicy(
            require_calibrated_model=True,
            require_environment_v2=True,
        ),
    )
    assert vector.available
    assert vector.environment == pytest.approx(0.1)
    assert vector.environment_coverage == pytest.approx(0.9)


def test_technical_environment_failure_is_excluded():
    vector = extract_reliability_features(
        _scores(environment="technical"),
        policy=FeatureExtractionPolicy(
            require_calibrated_model=True,
            require_environment_v2=True,
        ),
    )
    assert not vector.available
    assert "technical" in vector.exclusion_reason


def test_uncalibrated_model_is_rejected_in_paper_policy():
    scores = _scores()
    scores["model"] = DimensionScore(
        dimension="model",
        probability=0.7,
        available=True,
        evidence={"decision_probability_source": "base"},
    )
    vector = extract_reliability_features(
        scores,
        policy=FeatureExtractionPolicy(require_calibrated_model=True),
    )
    assert not vector.available
    assert "not calibrated" in vector.exclusion_reason
