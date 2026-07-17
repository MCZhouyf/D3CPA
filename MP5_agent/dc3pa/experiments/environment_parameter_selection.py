"""Pre-registered Environment evidence parameter selection.

The candidate grid is frozen before ``dev_tune`` evaluation. Each candidate:
- uses action-conditioned top-3 evidence;
- classifies a decision as matched, mismatch, or unknown;
- fits one Laplace-smoothed correctness probability per state on dev_train;
- enforces mismatch <= unknown <= matched with weighted PAV;
- is selected on dev_tune by Brier, then log loss, then lower unknown rate,
  then candidate ID.

No holdout or final-evaluation record is accepted.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence

from .development_records import DevelopmentDecisionRecord
from .ordinal_confidence_calibration import weighted_pav


SCHEMA_VERSION = 1
STATES = ("mismatch", "unknown", "matched")
EPSILON = 1e-12


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class EnvironmentCandidate:
    top_k: int
    minimum_similarity: float
    minimum_coverage: float
    mismatch_compatibility_threshold: float
    match_compatibility_threshold: float
    candidate_id: str = ""

    def __post_init__(self) -> None:
        if self.top_k != 3:
            raise ValueError("Environment candidate must use top_k=3")
        for value in (
            self.minimum_similarity,
            self.minimum_coverage,
            self.mismatch_compatibility_threshold,
            self.match_compatibility_threshold,
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError("Environment threshold is outside [0,1]")
        if self.mismatch_compatibility_threshold >= (
            self.match_compatibility_threshold
        ):
            raise ValueError("Mismatch threshold must be below match threshold")
        expected = self.compute_candidate_id()
        if self.candidate_id and self.candidate_id != expected:
            raise ValueError("Environment candidate hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("candidate_id", None)
        return payload

    def compute_candidate_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "EnvironmentCandidate":
        return replace(self, candidate_id=self.compute_candidate_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.candidate_id else self.with_id()
        payload = item.payload_without_id()
        payload["candidate_id"] = item.candidate_id
        return payload

    def classify(self, record: DevelopmentDecisionRecord) -> str:
        similarities = tuple(record.environment_topk_similarities)
        maximum_similarity = max(similarities, default=0.0)
        if (
            not record.environment_topk_exemplar_ids
            or maximum_similarity < self.minimum_similarity
            or record.environment_coverage < self.minimum_coverage
        ):
            return "unknown"
        if record.environment_compatibility >= (
            self.match_compatibility_threshold
        ):
            return "matched"
        if record.environment_compatibility <= (
            self.mismatch_compatibility_threshold
        ):
            return "mismatch"
        return "unknown"


@dataclass(frozen=True)
class EnvironmentCandidateResult:
    candidate: EnvironmentCandidate
    train_state_counts: Mapping[str, int]
    train_state_correct: Mapping[str, int]
    state_probabilities: Mapping[str, float]
    tune_record_count: int
    tune_brier: float
    tune_log_loss: float
    tune_unknown_rate: float
    tune_accuracy: float

    def __post_init__(self) -> None:
        if set(self.train_state_counts) != set(STATES):
            raise ValueError("Environment train state counts are incomplete")
        if set(self.train_state_correct) != set(STATES):
            raise ValueError("Environment train correct counts are incomplete")
        if set(self.state_probabilities) != set(STATES):
            raise ValueError("Environment state probabilities are incomplete")
        probabilities = [self.state_probabilities[state] for state in STATES]
        if probabilities != sorted(probabilities):
            raise ValueError("Environment probabilities are not monotonic")
        for value in (
            self.tune_brier,
            self.tune_log_loss,
            self.tune_unknown_rate,
            self.tune_accuracy,
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError("Environment candidate metric is invalid")
        if self.tune_unknown_rate > 1.0 or self.tune_accuracy > 1.0:
            raise ValueError("Environment candidate rate is outside [0,1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "train_state_counts": dict(sorted(self.train_state_counts.items())),
            "train_state_correct": dict(
                sorted(self.train_state_correct.items())
            ),
            "state_probabilities": dict(
                sorted(self.state_probabilities.items())
            ),
            "tune_record_count": self.tune_record_count,
            "tune_brier": self.tune_brier,
            "tune_log_loss": self.tune_log_loss,
            "tune_unknown_rate": self.tune_unknown_rate,
            "tune_accuracy": self.tune_accuracy,
        }


@dataclass(frozen=True)
class EnvironmentEvidenceRelease:
    release_name: str
    source_commit: str
    development_input_release_id: str
    collection_audit_id: str
    paper_memory_v5_release_id: str
    active_taskset_release_id: str
    candidate_grid_id: str
    selected_candidate_id: str
    selected_result: EnvironmentCandidateResult
    all_results: tuple[EnvironmentCandidateResult, ...]
    selection_objective: str
    holdout_used: bool
    final_evaluation_used: bool
    outcome_adaptive_grid_changes: bool
    eligible: bool
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        if self.holdout_used or self.final_evaluation_used:
            raise ValueError("Environment release used protected data")
        if self.outcome_adaptive_grid_changes:
            raise ValueError("Environment grid changed after outcomes")
        if self.selection_objective != (
            "min_tune_brier_then_logloss_then_unknown_rate_then_id"
        ):
            raise ValueError("Unexpected Environment selection objective")
        if self.selected_candidate_id != (
            self.selected_result.candidate.candidate_id
        ):
            raise ValueError("Selected Environment candidate/result mismatch")
        if not any(
            result.candidate.candidate_id == self.selected_candidate_id
            for result in self.all_results
        ):
            raise ValueError("Selected candidate is absent from all results")
        if not self.eligible:
            raise ValueError("Cannot freeze an ineligible Environment release")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("Environment release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        payload["selected_result"] = self.selected_result.to_dict()
        payload["all_results"] = [item.to_dict() for item in self.all_results]
        return payload

    def compute_release_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "EnvironmentEvidenceRelease":
        return replace(self, release_id=self.compute_release_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.release_id else self.with_id()
        payload = item.payload_without_id()
        payload["release_id"] = item.release_id
        return payload

    def probability_for_record(self, record: DevelopmentDecisionRecord) -> float:
        state = self.selected_result.candidate.classify(record)
        return float(self.selected_result.state_probabilities[state])


def _candidate_result(
    candidate: EnvironmentCandidate,
    train_records: Sequence[DevelopmentDecisionRecord],
    tune_records: Sequence[DevelopmentDecisionRecord],
    *,
    alpha: float,
) -> EnvironmentCandidateResult:
    counts: Counter[str] = Counter()
    correct: Counter[str] = Counter()
    for item in train_records:
        state = candidate.classify(item)
        counts[state] += 1
        correct[state] += int(item.decision_correct)
    raw = [
        (correct[state] + alpha) / (counts[state] + 2.0 * alpha)
        for state in STATES
    ]
    weights = [counts[state] + 2.0 * alpha for state in STATES]
    calibrated = weighted_pav(raw, weights)
    probabilities = {
        state: calibrated[index] for index, state in enumerate(STATES)
    }

    if not tune_records:
        raise ValueError("Environment tune dataset is empty")
    brier = log_loss = correct_total = unknown_total = 0.0
    for item in tune_records:
        state = candidate.classify(item)
        probability = min(
            1.0 - EPSILON,
            max(EPSILON, float(probabilities[state])),
        )
        label = 1.0 if item.decision_correct else 0.0
        brier += (probability - label) ** 2
        log_loss += -(
            label * math.log(probability)
            + (1.0 - label) * math.log(1.0 - probability)
        )
        correct_total += label
        unknown_total += int(state == "unknown")
    count = len(tune_records)
    return EnvironmentCandidateResult(
        candidate=candidate if candidate.candidate_id else candidate.with_id(),
        train_state_counts={state: counts[state] for state in STATES},
        train_state_correct={state: correct[state] for state in STATES},
        state_probabilities=probabilities,
        tune_record_count=count,
        tune_brier=brier / count,
        tune_log_loss=log_loss / count,
        tune_unknown_rate=unknown_total / count,
        tune_accuracy=correct_total / count,
    )


def select_environment_evidence(
    *,
    release_name: str,
    source_commit: str,
    development_input_release_id: str,
    collection_audit_id: str,
    paper_memory_v5_release_id: str,
    active_taskset_release_id: str,
    candidates: Sequence[EnvironmentCandidate],
    train_records: Sequence[DevelopmentDecisionRecord],
    tune_records: Sequence[DevelopmentDecisionRecord],
    alpha: float = 1.0,
) -> EnvironmentEvidenceRelease:
    if alpha <= 0:
        raise ValueError("Environment Laplace alpha must be positive")
    if not candidates:
        raise ValueError("Environment candidate grid is empty")
    if any(item.role != "dev_train" for item in train_records):
        raise ValueError("Environment train dataset contains non-train records")
    if any(item.role != "dev_tune" for item in tune_records):
        raise ValueError("Environment tune dataset contains non-tune records")
    normalized_candidates = tuple(
        item if item.candidate_id else item.with_id() for item in candidates
    )
    if len({item.candidate_id for item in normalized_candidates}) != len(
        normalized_candidates
    ):
        raise ValueError("Environment candidate grid contains duplicates")
    results = tuple(
        _candidate_result(
            candidate,
            train_records,
            tune_records,
            alpha=alpha,
        )
        for candidate in normalized_candidates
    )
    selected = min(
        results,
        key=lambda item: (
            item.tune_brier,
            item.tune_log_loss,
            item.tune_unknown_rate,
            item.candidate.candidate_id,
        ),
    )
    grid_id = _sha(
        [
            item.to_dict()
            for item in sorted(
                normalized_candidates,
                key=lambda value: value.candidate_id,
            )
        ]
    )
    return EnvironmentEvidenceRelease(
        release_name=release_name,
        source_commit=source_commit,
        development_input_release_id=development_input_release_id,
        collection_audit_id=collection_audit_id,
        paper_memory_v5_release_id=paper_memory_v5_release_id,
        active_taskset_release_id=active_taskset_release_id,
        candidate_grid_id=grid_id,
        selected_candidate_id=selected.candidate.candidate_id,
        selected_result=selected,
        all_results=results,
        selection_objective=(
            "min_tune_brier_then_logloss_then_unknown_rate_then_id"
        ),
        holdout_used=False,
        final_evaluation_used=False,
        outcome_adaptive_grid_changes=False,
        eligible=True,
    ).with_id()
