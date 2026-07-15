"""Feature extraction for DC3PA monotonic reliability fusion.

This module deliberately separates:
- hard logical infeasibility;
- unknown evidence;
- technical evidence failure;
- scalar feature values used by the four-parameter Logistic model.

It performs no provider call, environment call, memory write, or model fitting.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

from .contracts import DIMENSIONS, DimensionScore


FEATURE_SCHEMA_VERSION = "dc3pa-fusion-features-v1"
FUSION_FEATURE_NAMES = (
    "knowledge",
    "model",
    "environment",
    "environment_coverage",
)

_ENV_UNKNOWN_STATUSES = {
    "unknown",
    "future_context_unavailable",
}
_ENV_TECHNICAL_STATUSES = {
    "technical_unavailable",
}


def _probability(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric, not bool")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be finite and in [0, 1]")
    return number


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class FeatureExtractionPolicy:
    knowledge_unknown_prior: float = 0.5
    environment_unknown_compatibility: float = 0.5
    require_calibrated_model: bool = False
    require_environment_v2: bool = False
    exclude_technical_environment: bool = True
    exclude_unavailable_model: bool = True

    def __post_init__(self) -> None:
        _probability(self.knowledge_unknown_prior, "knowledge_unknown_prior")
        _probability(
            self.environment_unknown_compatibility,
            "environment_unknown_compatibility",
        )


@dataclass(frozen=True)
class ReliabilityFeatureVector:
    hard_conflict: bool
    available: bool
    knowledge: Optional[float]
    model: Optional[float]
    environment: Optional[float]
    environment_coverage: Optional[float]
    knowledge_available: bool
    model_available: bool
    environment_status: str
    exclusion_reason: str = ""
    confidence_artifact_id: str = ""
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
        values = (
            self.knowledge,
            self.model,
            self.environment,
            self.environment_coverage,
        )
        if self.available:
            if any(value is None for value in values):
                raise ValueError("available feature vectors require all four features")
            for name, value in zip(FUSION_FEATURE_NAMES, values):
                _probability(value, name)
            if self.exclusion_reason:
                raise ValueError("available feature vectors cannot have exclusion_reason")
        elif not self.exclusion_reason and not self.hard_conflict:
            raise ValueError("unavailable feature vectors need an exclusion reason")

    @property
    def values(self) -> tuple[float, float, float, float]:
        if not self.available:
            raise ValueError("Unavailable feature vector has no numeric values")
        assert self.knowledge is not None
        assert self.model is not None
        assert self.environment is not None
        assert self.environment_coverage is not None
        return (
            float(self.knowledge),
            float(self.model),
            float(self.environment),
            float(self.environment_coverage),
        )

    def as_feature_dict(self) -> dict[str, float]:
        return dict(zip(FUSION_FEATURE_NAMES, self.values))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata)
        return payload


def _knowledge_feature(
    score: DimensionScore,
    policy: FeatureExtractionPolicy,
) -> tuple[float, bool, Mapping[str, Any]]:
    evidence = _mapping(score.evidence)
    knowledge_v2 = _mapping(evidence.get("knowledge_v2"))
    if score.available:
        value = knowledge_v2.get("coverage", score.probability)
        return _probability(value, "knowledge coverage"), True, knowledge_v2
    return float(policy.knowledge_unknown_prior), False, knowledge_v2


def _model_feature(
    score: DimensionScore,
    policy: FeatureExtractionPolicy,
) -> tuple[Optional[float], bool, str, Mapping[str, Any]]:
    evidence = _mapping(score.evidence)
    if not score.available or score.probability is None:
        if policy.exclude_unavailable_model:
            return None, False, "model evidence unavailable", evidence
        return 0.5, False, "", evidence

    source = str(evidence.get("decision_probability_source", "")).strip().lower()
    artifact_id = str(evidence.get("calibration_artifact_id", "")).strip()
    if policy.require_calibrated_model:
        if source != "calibrated":
            return None, True, "model score is not calibrated", evidence
        if not artifact_id:
            return None, True, "calibrated model score lacks artifact ID", evidence
    return _probability(score.probability, "model confidence"), True, "", evidence


def _environment_feature(
    score: DimensionScore,
    policy: FeatureExtractionPolicy,
) -> tuple[Optional[float], Optional[float], str, str, Mapping[str, Any]]:
    evidence = _mapping(score.evidence)
    status = str(evidence.get("status", "")).strip().lower()

    if policy.require_environment_v2 and not status:
        return None, None, "", "environment score is not Environment V2", evidence

    if status in _ENV_UNKNOWN_STATUSES:
        return (
            float(policy.environment_unknown_compatibility),
            0.0,
            status,
            "",
            evidence,
        )

    if status in _ENV_TECHNICAL_STATUSES:
        if policy.exclude_technical_environment:
            return None, None, status, "technical environment evidence failure", evidence
        return (
            float(policy.environment_unknown_compatibility),
            0.0,
            status,
            "",
            evidence,
        )

    if score.available and score.probability is not None:
        compatibility = _probability(score.probability, "environment compatibility")
        coverage = _probability(evidence.get("coverage", 1.0), "environment coverage")
        return compatibility, coverage, status or "legacy_available", "", evidence

    # Unavailable environment without an explicit technical status is unknown.
    if not score.available:
        return (
            float(policy.environment_unknown_compatibility),
            0.0,
            status or "unknown",
            "",
            evidence,
        )

    return None, None, status, "invalid environment evidence", evidence


def extract_reliability_features(
    scores: Mapping[str, DimensionScore],
    *,
    policy: Optional[FeatureExtractionPolicy] = None,
) -> ReliabilityFeatureVector:
    """Extract the four Logistic features from already-computed dimension scores.

    Dimension strategies must be called exactly once upstream. This function only
    reads their values/evidence and therefore cannot increase LLM, encoder, or
    environment calls.
    """

    policy = policy or FeatureExtractionPolicy()
    if set(scores) != set(DIMENSIONS):
        raise ValueError(
            f"scores must contain exactly {DIMENSIONS}, got {sorted(scores)}"
        )

    knowledge_score = scores["knowledge"]
    model_score = scores["model"]
    environment_score = scores["environment"]

    hard_conflict = bool(knowledge_score.hard_conflict)
    knowledge, knowledge_available, knowledge_evidence = _knowledge_feature(
        knowledge_score, policy
    )

    model, model_available, model_error, model_evidence = _model_feature(
        model_score, policy
    )
    environment, coverage, environment_status, environment_error, env_evidence = (
        _environment_feature(environment_score, policy)
    )

    exclusion = model_error or environment_error
    available = not exclusion and all(
        value is not None for value in (knowledge, model, environment, coverage)
    )

    return ReliabilityFeatureVector(
        hard_conflict=hard_conflict,
        available=available,
        knowledge=knowledge if available else None,
        model=model if available else None,
        environment=environment if available else None,
        environment_coverage=coverage if available else None,
        knowledge_available=knowledge_available,
        model_available=model_available,
        environment_status=environment_status,
        exclusion_reason=exclusion,
        confidence_artifact_id=str(
            model_evidence.get("calibration_artifact_id", "")
        ),
        metadata={
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "knowledge_evidence_available": knowledge_available,
            "environment_evidence": {
                "status": environment_status,
                "coverage": coverage,
            },
            "knowledge_source": "knowledge_v2" if knowledge_evidence else "prior",
        },
    )
