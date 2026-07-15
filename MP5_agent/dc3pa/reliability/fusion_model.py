"""Runtime monotonic Logistic fusion and non-invasive shadow wrapper."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from ..contracts import AgentState, Plan
from .contracts import DIMENSIONS, DimensionScore, FusionEvidence, ReliabilityContext, ReliabilityResult
from .fusion_artifact import FusionArtifact
from .fusion_features import (
    FeatureExtractionPolicy,
    ReliabilityFeatureVector,
    extract_reliability_features,
)


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


@dataclass(frozen=True)
class FusionComputation:
    method: str
    probability: Optional[float]
    hard_gate_applied: bool
    features: Mapping[str, float]
    intercept: float
    coefficients: Mapping[str, float]
    artifact_id: str
    available: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["features"] = dict(self.features)
        payload["coefficients"] = dict(self.coefficients)
        return payload


class MonotonicLogisticFusion:
    def __init__(
        self,
        artifact: FusionArtifact,
        *,
        policy: Optional[FeatureExtractionPolicy] = None,
    ):
        self.artifact = artifact if artifact.artifact_id else artifact.with_id()
        self.policy = policy or FeatureExtractionPolicy(
            knowledge_unknown_prior=artifact.knowledge_unknown_prior,
            environment_unknown_compatibility=(
                artifact.environment_unknown_compatibility
            ),
            require_calibrated_model=True,
            require_environment_v2=True,
            exclude_technical_environment=True,
            exclude_unavailable_model=True,
        )

    def compute_from_scores(
        self,
        scores: Mapping[str, DimensionScore],
    ) -> FusionComputation:
        vector = extract_reliability_features(scores, policy=self.policy)

        if vector.hard_conflict:
            feature_values = vector.as_feature_dict() if vector.available else {}
            return FusionComputation(
                method="monotonic_logistic_v2",
                probability=0.0,
                hard_gate_applied=True,
                features=feature_values,
                intercept=float(self.artifact.intercept),
                coefficients=dict(self.artifact.coefficients),
                artifact_id=self.artifact.artifact_id,
                available=True,
                reason="Overall reliability forced to zero by knowledge hard gate",
            )

        if not vector.available:
            return FusionComputation(
                method="monotonic_logistic_v2",
                probability=None,
                hard_gate_applied=False,
                features={},
                intercept=float(self.artifact.intercept),
                coefficients=dict(self.artifact.coefficients),
                artifact_id=self.artifact.artifact_id,
                available=False,
                reason=vector.exclusion_reason,
            )

        features = vector.as_feature_dict()
        logit = float(self.artifact.intercept) + sum(
            float(self.artifact.coefficients[name]) * features[name]
            for name in features
        )
        return FusionComputation(
            method="monotonic_logistic_v2",
            probability=float(_sigmoid(logit)),
            hard_gate_applied=False,
            features=features,
            intercept=float(self.artifact.intercept),
            coefficients=dict(self.artifact.coefficients),
            artifact_id=self.artifact.artifact_id,
            available=True,
            reason="Four-feature nonnegative Logistic reliability fusion",
        )


class ReliabilityStrategy(Protocol):
    def score(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> DimensionScore:
        ...


def _fusion_evidence(computation: FusionComputation, *, method: str | None = None) -> FusionEvidence:
    return FusionEvidence(
        method=method or computation.method,
        probability=computation.probability,
        features=dict(computation.features),
        coefficients=dict(computation.coefficients),
        intercept=computation.intercept,
        artifact_id=computation.artifact_id,
        hard_gate_applied=computation.hard_gate_applied,
        available=computation.available,
        reason=computation.reason,
    )


class MonotonicLogisticHybridModel:
    """Active Round 5 fusion model with no memory-count weighting."""

    def __init__(
        self,
        *,
        knowledge: ReliabilityStrategy,
        model: ReliabilityStrategy,
        environment: ReliabilityStrategy,
        fusion: MonotonicLogisticFusion,
    ) -> None:
        self.knowledge = knowledge
        self.model = model
        self.environment = environment
        self.fusion = fusion

    def score_step(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
        successful_memory_count: Optional[int] = None,
    ) -> ReliabilityResult:
        del successful_memory_count
        if not 0 <= step_index < len(plan.steps):
            raise IndexError(f"step_index {step_index} out of range")
        context = context or ReliabilityContext()
        scores = {
            "knowledge": self.knowledge.score(plan, step_index, state, context),
            "model": self.model.score(plan, step_index, state, context),
            "environment": self.environment.score(plan, step_index, state, context),
        }
        for expected, score in scores.items():
            if score.dimension != expected:
                raise ValueError(
                    f"Strategy registered as {expected!r} returned {score.dimension!r}"
                )
        computation = self.fusion.compute_from_scores(scores)
        step = plan.steps[step_index]
        notes = (computation.reason,) if computation.reason else ()
        return ReliabilityResult(
            plan_id=plan.plan_id,
            plan_version=plan.version,
            step_id=step.step_id,
            step_index=step_index,
            probability=computation.probability,
            scores=scores,
            fusion=_fusion_evidence(computation),
            notes=notes,
        )

    def score_window(
        self,
        plan: Plan,
        step_indices: Sequence[int],
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
        successful_memory_count: Optional[int] = None,
    ) -> list[ReliabilityResult]:
        return [
            self.score_step(
                plan=plan,
                step_index=index,
                state=state,
                context=context,
                successful_memory_count=successful_memory_count,
            )
            for index in step_indices
        ]


class LogisticFusionShadowModel:
    """Call the legacy hybrid exactly once and record a candidate computation.

    The returned legacy result object is not replaced or mutated. This is the
    safest Round 5C shadow mode until the repository contract is migrated to
    carry explicit ``FusionEvidence``.
    """

    def __init__(
        self,
        legacy_model: Any,
        candidate: MonotonicLogisticFusion,
        *,
        observer: Optional[Callable[[Any, FusionComputation], None]] = None,
        fail_open: bool = True,
        attach_to_result: bool = False,
    ):
        self.legacy_model = legacy_model
        self.candidate = candidate
        self.observer = observer
        self.fail_open = bool(fail_open)
        self.attach_to_result = bool(attach_to_result)

    def score_step(self, *args: Any, **kwargs: Any):
        legacy_result = self.legacy_model.score_step(*args, **kwargs)
        try:
            computation = self.candidate.compute_from_scores(legacy_result.scores)
            if self.observer is not None:
                self.observer(legacy_result, computation)
            if self.attach_to_result:
                return replace(
                    legacy_result,
                    shadow_fusion=_fusion_evidence(
                        computation,
                        method="monotonic_logistic_shadow",
                    ),
                )
        except Exception:
            if not self.fail_open:
                raise
        return legacy_result

    def score_window(self, *args: Any, **kwargs: Any):
        # Do not delegate to legacy score_window, because that would bypass this
        # wrapper's score_step observation. Reuse exactly one legacy score_step
        # call for each requested index.
        plan = kwargs.get("plan", args[0] if args else None)
        step_indices = kwargs.get(
            "step_indices", args[1] if len(args) > 1 else None
        )
        state = kwargs.get("state", args[2] if len(args) > 2 else None)
        context = kwargs.get("context")
        successful_memory_count = kwargs.get("successful_memory_count")
        return [
            self.score_step(
                plan=plan,
                step_index=index,
                state=state,
                context=context,
                successful_memory_count=successful_memory_count,
            )
            for index in step_indices
        ]
