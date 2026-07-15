from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from importlib import import_module
from typing import Any, Dict, Mapping

from ..errors import ContractValidationError
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

    def validate(self) -> None:
        visual = _finite_number(self.visual_similarity_weight, "visual_similarity_weight")
        cap = _finite_number(self.learned_weight_cap, "learned_weight_cap")
        growth = _finite_number(self.memory_weight_growth, "memory_weight_growth")
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
        if self.model_failure_mode not in {"unavailable", "raise"}:
            raise ContractValidationError(
                "model_failure_mode must be 'unavailable' or 'raise'"
            )
        try:
            validate_knowledge_impl(self.knowledge_impl)
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
