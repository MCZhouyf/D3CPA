from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

from ..contracts import AgentState, Plan
from ..errors import ContractValidationError

DIMENSIONS = ("knowledge", "model", "environment")


def _validate_probability(value: Optional[float], label: str) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        raise ContractValidationError(f"{label} must be numeric, not bool")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ContractValidationError(f"{label} must be finite and in [0, 1]")


@dataclass(frozen=True)
class ReliabilityContext:
    """Runtime inputs that are intentionally kept outside ``AgentState``.

    Raw images and vectors are excluded from manifests and prompt payloads by default.
    This avoids accidentally serializing large tensors or sensitive observations.
    """

    task_context: str = ""
    image: Any = None
    image_vector: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def prompt_metadata(self) -> Dict[str, Any]:
        return {
            "task_context": self.task_context,
            "metadata": dict(self.metadata),
            "has_image": self.image is not None,
            "has_image_vector": self.image_vector is not None,
        }


@dataclass(frozen=True)
class DimensionScore:
    dimension: str
    probability: Optional[float]
    available: bool
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    hard_conflict: bool = False

    def __post_init__(self) -> None:
        if self.dimension not in DIMENSIONS:
            raise ContractValidationError(
                f"Unknown reliability dimension {self.dimension!r}"
            )
        _validate_probability(self.probability, f"{self.dimension}.probability")
        if self.available != (self.probability is not None):
            raise ContractValidationError(
                "DimensionScore.available must match whether probability is present"
            )
        if self.hard_conflict and self.dimension != "knowledge":
            raise ContractValidationError(
                "Only the knowledge dimension may declare a hard prerequisite conflict"
            )

    @classmethod
    def unavailable(
        cls, dimension: str, reason: str, evidence: Optional[Mapping[str, Any]] = None
    ) -> "DimensionScore":
        return cls(
            dimension=dimension,
            probability=None,
            available=False,
            reason=reason,
            evidence=dict(evidence or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyWeights:
    knowledge: float
    model: float
    environment: float

    def __post_init__(self) -> None:
        values = (self.knowledge, self.model, self.environment)
        if any(isinstance(value, bool) for value in values):
            raise ContractValidationError("Strategy weights cannot be booleans")
        if any(not math.isfinite(float(value)) or float(value) < 0.0 for value in values):
            raise ContractValidationError("Strategy weights must be finite and non-negative")
        if not math.isclose(sum(values), 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise ContractValidationError(
                f"Strategy weights must sum to one, got {sum(values)!r}"
            )

    def as_dict(self) -> Dict[str, float]:
        return {
            "knowledge": float(self.knowledge),
            "model": float(self.model),
            "environment": float(self.environment),
        }


@dataclass(frozen=True)
class FusionEvidence:
    method: str
    probability: Optional[float]
    features: Mapping[str, float] = field(default_factory=dict)
    coefficients: Mapping[str, float] = field(default_factory=dict)
    intercept: Optional[float] = None
    artifact_id: str = ""
    hard_gate_applied: bool = False
    available: bool = True
    reason: str = ""

    def __post_init__(self) -> None:
        method = str(self.method or "").strip()
        if method not in {
            "memory_weighted_v1",
            "monotonic_logistic_shadow",
            "monotonic_logistic_v2",
        }:
            raise ContractValidationError(f"Unknown fusion method {self.method!r}")
        _validate_probability(self.probability, "fusion.probability")
        if self.available != (self.probability is not None):
            raise ContractValidationError(
                "FusionEvidence.available must match whether probability is present"
            )
        for label, values in (
            ("fusion.features", self.features),
            ("fusion.coefficients", self.coefficients),
        ):
            for name, value in dict(values).items():
                if isinstance(value, bool):
                    raise ContractValidationError(f"{label}.{name} cannot be bool")
                number = float(value)
                if not math.isfinite(number):
                    raise ContractValidationError(f"{label}.{name} must be finite")
                if label == "fusion.features" and not 0.0 <= number <= 1.0:
                    raise ContractValidationError(
                        f"{label}.{name} must be in [0, 1]"
                    )
        if self.intercept is not None:
            if isinstance(self.intercept, bool) or not math.isfinite(
                float(self.intercept)
            ):
                raise ContractValidationError("fusion.intercept must be finite")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "probability": self.probability,
            "features": dict(self.features),
            "coefficients": dict(self.coefficients),
            "intercept": self.intercept,
            "artifact_id": self.artifact_id,
            "hard_gate_applied": self.hard_gate_applied,
            "available": self.available,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ReliabilityResult:
    plan_id: str
    plan_version: int
    step_id: str
    step_index: int
    probability: Optional[float]
    scores: Dict[str, DimensionScore]
    base_weights: Optional[StrategyWeights] = None
    effective_weights: Optional[StrategyWeights] = None
    successful_memory_count: Optional[int] = None
    fusion: Optional[FusionEvidence] = None
    shadow_fusion: Optional[FusionEvidence] = None
    notes: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _validate_probability(self.probability, "reliability.probability")
        if self.step_index < 0:
            raise ContractValidationError("step_index must be non-negative")
        if set(self.scores) != set(DIMENSIONS):
            raise ContractValidationError(
                f"scores must contain exactly {DIMENSIONS}, got {sorted(self.scores)}"
            )
        method = self.fusion.method if self.fusion is not None else "memory_weighted_v1"
        if method == "memory_weighted_v1":
            if self.base_weights is None:
                raise ContractValidationError("legacy fusion requires base_weights")
            if self.probability is None and self.effective_weights is not None:
                raise ContractValidationError(
                    "effective_weights must be None when no overall probability is available"
                )
            if self.probability is not None and self.effective_weights is None:
                raise ContractValidationError(
                    "effective_weights are required when probability is available"
                )
            if self.successful_memory_count is None or self.successful_memory_count < 0:
                raise ContractValidationError(
                    "legacy fusion requires non-negative successful_memory_count"
                )
        elif method == "monotonic_logistic_v2":
            if self.base_weights is not None or self.effective_weights is not None:
                raise ContractValidationError(
                    "logistic fusion must not fabricate legacy weights"
                )
            if self.successful_memory_count is not None:
                raise ContractValidationError(
                    "logistic fusion must not depend on successful_memory_count"
                )
        else:
            raise ContractValidationError(
                f"ReliabilityResult.fusion cannot use method {method!r}"
            )
        if self.fusion is not None and self.fusion.probability != self.probability:
            raise ContractValidationError(
                "fusion.probability must match result probability"
            )

    @property
    def hard_conflict(self) -> bool:
        return any(score.hard_conflict for score in self.scores.values())

    def is_low_confidence(self, threshold: float) -> bool:
        _validate_probability(float(threshold), "threshold")
        return self.probability is None or self.probability < threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "step_id": self.step_id,
            "step_index": self.step_index,
            "probability": self.probability,
            "scores": {name: score.to_dict() for name, score in self.scores.items()},
            "base_weights": (
                self.base_weights.as_dict() if self.base_weights is not None else None
            ),
            "effective_weights": (
                self.effective_weights.as_dict()
                if self.effective_weights is not None
                else None
            ),
            "successful_memory_count": self.successful_memory_count,
            "fusion": self.fusion.to_dict() if self.fusion is not None else None,
            "shadow_fusion": (
                self.shadow_fusion.to_dict()
                if self.shadow_fusion is not None
                else None
            ),
            "hard_conflict": self.hard_conflict,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ConfidenceRequest:
    plan: Plan
    state: AgentState
    step_index: int
    context: ReliabilityContext = field(default_factory=ReliabilityContext)

    @property
    def step(self):
        return self.plan.steps[self.step_index]

    def to_prompt_payload(self) -> Dict[str, Any]:
        return {
            "task": self.plan.task,
            "plan_id": self.plan.plan_id,
            "plan_version": self.plan.version,
            "step_index": self.step_index,
            "step": self.step.to_dict(),
            "state": self.state.to_dict(),
            "context": self.context.prompt_metadata(),
        }
