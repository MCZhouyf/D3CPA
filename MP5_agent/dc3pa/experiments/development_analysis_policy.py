"""Pre-outcome analysis policy for Round 5.11."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any

from .environment_parameter_selection import EnvironmentCandidate


SCHEMA_VERSION = 1
CONFIDENCE_LEVELS = (
    "very_low",
    "low",
    "medium",
    "high",
    "very_high",
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class Round511AnalysisPolicy:
    policy_name: str
    confidence_levels: tuple[str, ...]
    confidence_alpha: float
    confidence_method: str
    environment_alpha: float
    environment_candidates: tuple[EnvironmentCandidate, ...]
    environment_selection_objective: str
    environment_top_k: int
    fusion_feature_order: tuple[str, ...]
    fusion_fitting_permitted: bool
    holdout_use_permitted: bool
    final_evaluation_use_permitted: bool
    outcome_adaptive_changes_permitted: bool
    policy_frozen_before_collection: bool
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        if self.confidence_levels != CONFIDENCE_LEVELS:
            raise ValueError("Confidence level order changed")
        if self.confidence_alpha <= 0 or self.environment_alpha <= 0:
            raise ValueError("Laplace alpha must be positive")
        if self.confidence_method != "symmetric_laplace_then_weighted_pav":
            raise ValueError("Unexpected Confidence calibration method")
        if not self.environment_candidates:
            raise ValueError("Environment candidate grid is empty")
        normalized = tuple(
            candidate if candidate.candidate_id else candidate.with_id()
            for candidate in self.environment_candidates
        )
        if len({item.candidate_id for item in normalized}) != len(normalized):
            raise ValueError("Environment candidate grid contains duplicates")
        if any(item.top_k != 3 for item in normalized):
            raise ValueError("Environment top-k must remain 3")
        if self.environment_top_k != 3:
            raise ValueError("Environment top-k policy changed")
        if self.environment_selection_objective != (
            "min_tune_brier_then_logloss_then_unknown_rate_then_id"
        ):
            raise ValueError("Unexpected Environment selection objective")
        if self.fusion_feature_order != (
            "knowledge_coverage",
            "knowledge_unknown",
            "confidence_probability",
            "environment_probability",
        ):
            raise ValueError("Fusion feature order changed")
        if any(
            (
                self.fusion_fitting_permitted,
                self.holdout_use_permitted,
                self.final_evaluation_use_permitted,
                self.outcome_adaptive_changes_permitted,
            )
        ):
            raise ValueError("Round 5.11 policy opens a protected operation")
        if not self.policy_frozen_before_collection:
            raise ValueError("Analysis policy must be frozen before collection")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("Round 5.11 analysis policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["confidence_levels"] = list(self.confidence_levels)
        payload["environment_candidates"] = [
            item.to_dict()
            for item in sorted(
                self.environment_candidates,
                key=lambda value: value.candidate_id
                or value.compute_candidate_id(),
            )
        ]
        payload["fusion_feature_order"] = list(self.fusion_feature_order)
        return payload

    def compute_policy_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "Round511AnalysisPolicy":
        normalized = tuple(
            candidate if candidate.candidate_id else candidate.with_id()
            for candidate in self.environment_candidates
        )
        item = replace(self, environment_candidates=normalized)
        return replace(item, policy_id=item.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.policy_id else self.with_id()
        payload = item.payload_without_id()
        payload["policy_id"] = item.policy_id
        payload["environment_candidate_grid_id"] = _sha(
            [
                candidate.to_dict()
                for candidate in sorted(
                    item.environment_candidates,
                    key=lambda value: value.candidate_id,
                )
            ]
        )
        return payload
