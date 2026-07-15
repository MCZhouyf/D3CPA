from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from importlib import import_module
from typing import Any, Dict, Mapping

from ..errors import ContractValidationError
from .environment_v2 import validate_environment_impl, validate_environment_scope
from .fusion_artifact import validate_fusion_impl
from .knowledge_v2 import validate_knowledge_impl
from .ordinal_levels import validate_model_confidence_impl


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ContractValidationError(f"{label} must be numeric, not bool")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ContractValidationError(f"{label} must be finite")
    return number


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractValidationError(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True)
class HybridProbabilityConfig:
    """Configuration for the Stage-3 reliability model.

    ``visual_similarity_weight=0.7`` and ``learned_weight_cap=0.4`` follow the
    manuscript. The manuscript does not disambiguate the coefficient used for
    memory-weight growth from the visual alpha. ``memory_weight_growth=0.02`` is
    therefore an explicit engineering default, not a claimed paper hyperparameter.
    """

    visual_similarity_weight: float = 0.7
    learned_weight_cap: float = 0.4
    memory_weight_growth: float = 0.02
    require_environment_text_relevance: bool = True
    model_failure_mode: str = "unavailable"
    task_name_filter_environment: bool = False
    knowledge_impl: str = "legacy_v1"
    graph_hard_min_support: int = 2
    model_confidence_impl: str = "legacy_numeric"
    model_confidence_model_id: str = ""
    model_confidence_prompt_version: str = "ordinal-v1"
    model_confidence_artifact_path: str = ""
    environment_impl: str = "legacy_v1"
    environment_top_k: int = 3
    environment_text_threshold: float = 0.5
    environment_match_threshold: float = 0.5
    environment_scope: str = "legacy_all_steps"
    environment_allow_legacy_text_fallback: bool = True
    fusion_impl: str = "legacy_memory_weighted"
    fusion_artifact_path: str = ""
    fusion_knowledge_unknown_prior: float = 0.5
    fusion_environment_unknown_compatibility: float = 0.5
    fusion_shadow_fail_open: bool = True
    fusion_memory_snapshot_sha256: str = ""

    def validate(self) -> None:
        visual = _finite_number(self.visual_similarity_weight, "visual_similarity_weight")
        cap = _finite_number(self.learned_weight_cap, "learned_weight_cap")
        growth = _finite_number(self.memory_weight_growth, "memory_weight_growth")
        text_threshold = _finite_number(
            self.environment_text_threshold, "environment_text_threshold"
        )
        match_threshold = _finite_number(
            self.environment_match_threshold, "environment_match_threshold"
        )
        knowledge_prior = _finite_number(
            self.fusion_knowledge_unknown_prior,
            "fusion_knowledge_unknown_prior",
        )
        environment_unknown = _finite_number(
            self.fusion_environment_unknown_compatibility,
            "fusion_environment_unknown_compatibility",
        )
        if not 0.0 <= visual <= 1.0:
            raise ContractValidationError("visual_similarity_weight must be in [0, 1]")
        if not 0.0 <= cap <= 0.5:
            raise ContractValidationError("learned_weight_cap must be in [0, 0.5]")
        if growth < 0.0:
            raise ContractValidationError("memory_weight_growth must be non-negative")
        if not isinstance(self.require_environment_text_relevance, bool):
            raise ContractValidationError("require_environment_text_relevance must be bool")
        if not isinstance(self.task_name_filter_environment, bool):
            raise ContractValidationError("task_name_filter_environment must be bool")
        _positive_int(self.environment_top_k, "environment_top_k")
        if not 0.0 <= text_threshold <= 1.0:
            raise ContractValidationError("environment_text_threshold must be in [0, 1]")
        if not 0.0 <= match_threshold <= 1.0:
            raise ContractValidationError("environment_match_threshold must be in [0, 1]")
        if not isinstance(self.environment_allow_legacy_text_fallback, bool):
            raise ContractValidationError(
                "environment_allow_legacy_text_fallback must be bool"
            )
        if not 0.0 <= knowledge_prior <= 1.0:
            raise ContractValidationError(
                "fusion_knowledge_unknown_prior must be in [0, 1]"
            )
        if not 0.0 <= environment_unknown <= 1.0:
            raise ContractValidationError(
                "fusion_environment_unknown_compatibility must be in [0, 1]"
            )
        if not isinstance(self.fusion_shadow_fail_open, bool):
            raise ContractValidationError("fusion_shadow_fail_open must be bool")
        try:
            environment_impl = validate_environment_impl(self.environment_impl)
            environment_scope = validate_environment_scope(self.environment_scope)
        except ValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        if self.model_failure_mode not in {"unavailable", "raise"}:
            raise ContractValidationError(
                "model_failure_mode must be 'unavailable' or 'raise'"
            )
        try:
            knowledge_impl = validate_knowledge_impl(self.knowledge_impl)
        except ValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        _positive_int(self.graph_hard_min_support, "graph_hard_min_support")
        try:
            confidence_impl = validate_model_confidence_impl(self.model_confidence_impl)
        except ValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        if confidence_impl != "legacy_numeric":
            if not str(self.model_confidence_model_id).strip():
                raise ContractValidationError(
                    "ordinal model confidence modes require model_confidence_model_id"
                )
            if not str(self.model_confidence_prompt_version).strip():
                raise ContractValidationError(
                    "ordinal model confidence modes require model_confidence_prompt_version"
                )
        if confidence_impl in {"ordinal_shadow", "ordinal_calibrated"} and not str(
            self.model_confidence_artifact_path
        ).strip():
            raise ContractValidationError(
                f"{confidence_impl} requires model_confidence_artifact_path"
            )
        try:
            fusion_impl = validate_fusion_impl(self.fusion_impl)
        except ValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        if fusion_impl != "legacy_memory_weighted":
            if not str(self.fusion_artifact_path).strip():
                raise ContractValidationError(
                    f"{fusion_impl} requires fusion_artifact_path"
                )
        if fusion_impl == "monotonic_logistic_v2":
            requirements = {
                "knowledge_impl": (knowledge_impl, "hard_gate_v2"),
                "model_confidence_impl": (confidence_impl, "ordinal_calibrated"),
                "environment_impl": (environment_impl, "topk_v2"),
                "environment_scope": (environment_scope, "current_context_only"),
            }
            mismatches = [
                f"{name}={actual!r} must be {expected!r}"
                for name, (actual, expected) in requirements.items()
                if actual != expected
            ]
            if mismatches:
                raise ContractValidationError(
                    "monotonic_logistic_v2 requires paper V2 settings: "
                    + "; ".join(mismatches)
                )
            if not str(self.fusion_memory_snapshot_sha256).strip():
                raise ContractValidationError(
                    "monotonic_logistic_v2 requires fusion_memory_snapshot_sha256"
                )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "HybridProbabilityConfig":
        allowed = set(cls.__dataclass_fields__)
        unknown = set(data) - allowed
        if unknown:
            raise ContractValidationError(
                f"Unknown HybridProbabilityConfig fields: {sorted(unknown)}"
            )
        config = cls(**dict(data))
        config.validate()
        return config

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class DualChainConfig:
    confidence_threshold: float = 0.8
    max_revision_rounds: int = 2
    evaluate_when_unavailable: bool = True
    constraint_repair_policy: str = "legacy"

    def validate(self) -> None:
        threshold = _finite_number(self.confidence_threshold, "confidence_threshold")
        if not 0.0 <= threshold <= 1.0:
            raise ContractValidationError("confidence_threshold must be in [0, 1]")
        if (
            isinstance(self.max_revision_rounds, bool)
            or not isinstance(self.max_revision_rounds, int)
            or self.max_revision_rounds < 0
        ):
            raise ContractValidationError("max_revision_rounds must be a non-negative integer")
        if not isinstance(self.evaluate_when_unavailable, bool):
            raise ContractValidationError("evaluate_when_unavailable must be bool")
        try:
            validate_policy = import_module(
                "dc3pa.planner.constraint_repair_policy"
            ).validate_constraint_repair_policy
            validate_policy(self.constraint_repair_policy)
        except ValueError as exc:
            raise ContractValidationError(str(exc)) from exc

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DualChainConfig":
        allowed = set(cls.__dataclass_fields__)
        unknown = set(data) - allowed
        if unknown:
            raise ContractValidationError(
                f"Unknown DualChainConfig fields: {sorted(unknown)}"
            )
        config = cls(**dict(data))
        config.validate()
        return config

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class AdaptiveTriggerConfig:
    threshold: float = 0.8
    initial_interval: int = 3
    window_size: int = 3
    minimum_interval: int = 1
    maximum_interval: int = 64
    increase_step: int = 1
    decrease_step: int = 1

    def validate(self) -> None:
        threshold = _finite_number(self.threshold, "trigger threshold")
        if not 0.0 <= threshold <= 1.0:
            raise ContractValidationError("trigger threshold must be in [0, 1]")
        integer_fields = {
            "initial_interval": self.initial_interval,
            "window_size": self.window_size,
            "minimum_interval": self.minimum_interval,
            "maximum_interval": self.maximum_interval,
            "increase_step": self.increase_step,
            "decrease_step": self.decrease_step,
        }
        for label, value in integer_fields.items():
            _positive_int(value, label)
        if not self.minimum_interval <= self.initial_interval <= self.maximum_interval:
            raise ContractValidationError(
                "minimum_interval <= initial_interval <= maximum_interval is required"
            )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AdaptiveTriggerConfig":
        allowed = set(cls.__dataclass_fields__)
        unknown = set(data) - allowed
        if unknown:
            raise ContractValidationError(
                f"Unknown AdaptiveTriggerConfig fields: {sorted(unknown)}"
            )
        config = cls(**dict(data))
        config.validate()
        return config

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return asdict(self)
