"""Five-level ordinal confidence calibration with Laplace + PAV.

The model emits one of five ordered verbal confidence levels. ``dev_train``
fits per-level correctness probabilities with symmetric Laplace smoothing,
then weighted PAV enforces monotonicity. ``dev_tune`` is used only to audit
calibration metrics. ``dev_holdout`` is not accepted by this module.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence

from .development_records import (
    CONFIDENCE_LEVELS,
    DevelopmentDecisionRecord,
)


SCHEMA_VERSION = 1
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


def weighted_pav(
    values: Sequence[float],
    weights: Sequence[float],
) -> tuple[float, ...]:
    if len(values) != len(weights) or not values:
        raise ValueError("PAV values/weights are empty or mismatched")
    blocks: list[dict[str, Any]] = []
    for index, (value, weight) in enumerate(zip(values, weights)):
        if weight <= 0:
            raise ValueError("PAV weights must be positive")
        blocks.append(
            {
                "start": index,
                "end": index,
                "weight": float(weight),
                "sum": float(value) * float(weight),
            }
        )
        while len(blocks) >= 2:
            left = blocks[-2]
            right = blocks[-1]
            left_mean = left["sum"] / left["weight"]
            right_mean = right["sum"] / right["weight"]
            if left_mean <= right_mean:
                break
            merged = {
                "start": left["start"],
                "end": right["end"],
                "weight": left["weight"] + right["weight"],
                "sum": left["sum"] + right["sum"],
            }
            blocks[-2:] = [merged]
    result = [0.0] * len(values)
    for block in blocks:
        mean = block["sum"] / block["weight"]
        for index in range(block["start"], block["end"] + 1):
            result[index] = mean
    return tuple(result)


@dataclass(frozen=True)
class ConfidenceLevelCalibration:
    level: str
    train_count: int
    train_correct: int
    laplace_probability: float
    calibrated_probability: float

    def __post_init__(self) -> None:
        if self.level not in CONFIDENCE_LEVELS:
            raise ValueError("Unknown confidence level")
        if self.train_count < 0 or not 0 <= self.train_correct <= self.train_count:
            raise ValueError("Confidence calibration counts are invalid")
        if not 0.0 <= self.laplace_probability <= 1.0:
            raise ValueError("Laplace probability is invalid")
        if not 0.0 <= self.calibrated_probability <= 1.0:
            raise ValueError("Calibrated probability is invalid")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationMetrics:
    record_count: int
    brier: float
    log_loss: float
    ece: float
    accuracy: float
    level_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        if self.record_count < 0:
            raise ValueError("Metric record count cannot be negative")
        for value in (self.brier, self.log_loss, self.ece, self.accuracy):
            if not math.isfinite(value) or value < 0:
                raise ValueError("Calibration metric is invalid")
        if self.accuracy > 1.0 or self.ece > 1.0:
            raise ValueError("Calibration metric is outside [0,1]")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["level_counts"] = dict(sorted(self.level_counts.items()))
        return payload


@dataclass(frozen=True)
class ConfidenceCalibrationRelease:
    release_name: str
    source_commit: str
    development_input_release_id: str
    collection_audit_id: str
    paper_memory_v5_release_id: str
    active_taskset_release_id: str
    train_dataset_id: str
    tune_dataset_id: str
    alpha: float
    levels: tuple[ConfidenceLevelCalibration, ...]
    train_metrics: CalibrationMetrics
    tune_metrics: CalibrationMetrics
    monotonic: bool
    holdout_used: bool
    final_evaluation_used: bool
    eligible: bool
    warnings: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        if self.alpha <= 0:
            raise ValueError("Laplace alpha must be positive")
        if tuple(item.level for item in self.levels) != CONFIDENCE_LEVELS:
            raise ValueError("Confidence levels are incomplete or misordered")
        probabilities = [item.calibrated_probability for item in self.levels]
        if probabilities != sorted(probabilities):
            raise ValueError("Confidence calibration is not monotonic")
        if not self.monotonic:
            raise ValueError("Confidence release must be monotonic")
        if self.holdout_used or self.final_evaluation_used:
            raise ValueError("Confidence calibration used protected data")
        if not self.eligible:
            raise ValueError("Cannot freeze an ineligible confidence release")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("Confidence calibration release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        payload["levels"] = [item.to_dict() for item in self.levels]
        payload["train_metrics"] = self.train_metrics.to_dict()
        payload["tune_metrics"] = self.tune_metrics.to_dict()
        payload["warnings"] = list(self.warnings)
        return payload

    def compute_release_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "ConfidenceCalibrationRelease":
        return replace(self, release_id=self.compute_release_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.release_id else self.with_id()
        payload = item.payload_without_id()
        payload["release_id"] = item.release_id
        return payload

    def probability_for(self, level: str) -> float:
        mapping = {
            item.level: item.calibrated_probability for item in self.levels
        }
        if level not in mapping:
            raise KeyError(level)
        return mapping[level]


def _dataset_id(records: Sequence[DevelopmentDecisionRecord]) -> str:
    return _sha(
        [
            {
                "record_id": item.record_id,
                "record_hash": item.record_hash or item.compute_record_hash(),
            }
            for item in sorted(records, key=lambda value: value.record_id)
        ]
    )


def _metrics(
    records: Sequence[DevelopmentDecisionRecord],
    probability_by_level: Mapping[str, float],
) -> CalibrationMetrics:
    if not records:
        raise ValueError("Calibration metric dataset is empty")
    brier_total = log_total = correct_total = 0.0
    level_counts: Counter[str] = Counter()
    level_correct: Counter[str] = Counter()
    for item in records:
        probability = min(
            1.0 - EPSILON,
            max(EPSILON, float(probability_by_level[item.confidence_level])),
        )
        label = 1.0 if item.decision_correct else 0.0
        brier_total += (probability - label) ** 2
        log_total += -(
            label * math.log(probability)
            + (1.0 - label) * math.log(1.0 - probability)
        )
        correct_total += label
        level_counts[item.confidence_level] += 1
        level_correct[item.confidence_level] += int(item.decision_correct)

    ece = 0.0
    for level in CONFIDENCE_LEVELS:
        count = level_counts[level]
        if count <= 0:
            continue
        empirical = level_correct[level] / count
        ece += (
            count
            / len(records)
            * abs(float(probability_by_level[level]) - empirical)
        )
    return CalibrationMetrics(
        record_count=len(records),
        brier=brier_total / len(records),
        log_loss=log_total / len(records),
        ece=ece,
        accuracy=correct_total / len(records),
        level_counts={level: level_counts[level] for level in CONFIDENCE_LEVELS},
    )


def fit_confidence_calibration(
    *,
    release_name: str,
    source_commit: str,
    development_input_release_id: str,
    collection_audit_id: str,
    paper_memory_v5_release_id: str,
    active_taskset_release_id: str,
    train_records: Sequence[DevelopmentDecisionRecord],
    tune_records: Sequence[DevelopmentDecisionRecord],
    alpha: float = 1.0,
) -> ConfidenceCalibrationRelease:
    if alpha <= 0:
        raise ValueError("Laplace alpha must be positive")
    if not train_records or not tune_records:
        raise ValueError("Confidence train/tune datasets must be nonempty")
    if any(item.role != "dev_train" for item in train_records):
        raise ValueError("Confidence train dataset contains non-train records")
    if any(item.role != "dev_tune" for item in tune_records):
        raise ValueError("Confidence tune dataset contains non-tune records")

    counts = Counter(item.confidence_level for item in train_records)
    correct = Counter(
        item.confidence_level
        for item in train_records
        if item.decision_correct
    )
    raw = [
        (correct[level] + alpha) / (counts[level] + 2.0 * alpha)
        for level in CONFIDENCE_LEVELS
    ]
    weights = [counts[level] + 2.0 * alpha for level in CONFIDENCE_LEVELS]
    calibrated = weighted_pav(raw, weights)

    levels = tuple(
        ConfidenceLevelCalibration(
            level=level,
            train_count=counts[level],
            train_correct=correct[level],
            laplace_probability=raw[index],
            calibrated_probability=calibrated[index],
        )
        for index, level in enumerate(CONFIDENCE_LEVELS)
    )
    mapping = {
        item.level: item.calibrated_probability for item in levels
    }
    warnings: list[str] = []
    for item in levels:
        if item.train_count == 0:
            warnings.append(
                f"{item.level}: no train observations; probability is pooled "
                "through Laplace/PAV"
            )
        elif item.train_count < 5:
            warnings.append(
                f"{item.level}: fewer than five train observations"
            )
    return ConfidenceCalibrationRelease(
        release_name=release_name,
        source_commit=source_commit,
        development_input_release_id=development_input_release_id,
        collection_audit_id=collection_audit_id,
        paper_memory_v5_release_id=paper_memory_v5_release_id,
        active_taskset_release_id=active_taskset_release_id,
        train_dataset_id=_dataset_id(train_records),
        tune_dataset_id=_dataset_id(tune_records),
        alpha=alpha,
        levels=levels,
        train_metrics=_metrics(train_records, mapping),
        tune_metrics=_metrics(tune_records, mapping),
        monotonic=True,
        holdout_used=False,
        final_evaluation_used=False,
        eligible=True,
        warnings=tuple(warnings),
    ).with_id()
