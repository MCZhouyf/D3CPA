"""Deterministic five-level confidence calibration for DC3PA Round 3.

No neural model or additional runtime dependency is introduced.  Empirical rates are
Laplace-smoothed, monotonized with weighted pool-adjacent-violators (PAV), and persisted
as a strict, model/prompt-specific artifact.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .ordinal_levels import BASE_ORDINAL_MAPPING, ORDINAL_LEVELS, normalize_ordinal_level, validate_mapping

_EPS = 1e-12


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class OrdinalCalibrationSample:
    confidence_level: str
    label: int
    source_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence_level", normalize_ordinal_level(self.confidence_level))
        if isinstance(self.label, bool):
            object.__setattr__(self, "label", int(self.label))
        if self.label not in {0, 1}:
            raise ValueError("label must be 0 or 1")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confidence_level": self.confidence_level,
            "label": self.label,
            "source_id": self.source_id,
        }


@dataclass(frozen=True)
class OrdinalCalibrationArtifact:
    schema_version: int
    artifact_id: str
    model_id: str
    prompt_version: str
    prompt_sha256: str
    dataset_sha256: str
    created_from_commit: str
    base_mapping: Dict[str, float]
    calibrated_mapping: Dict[str, float]
    sample_counts: Dict[str, Dict[str, int]]
    metrics: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ordinal calibration artifact schema")
        if not self.artifact_id or not self.model_id or not self.prompt_version:
            raise ValueError("artifact_id, model_id, and prompt_version are required")
        validate_mapping(self.base_mapping, label="base_mapping")
        validate_mapping(self.calibrated_mapping, label="calibrated_mapping")
        if set(self.sample_counts) != set(ORDINAL_LEVELS):
            raise ValueError("sample_counts must contain all ordinal levels")

    def probability(self, level: str) -> float:
        return float(self.calibrated_mapping[normalize_ordinal_level(level)])

    def validate_compatibility(
        self, *, model_id: str, prompt_version: str, prompt_sha256: str
    ) -> None:
        mismatches = []
        if self.model_id != model_id:
            mismatches.append(f"model_id {self.model_id!r} != {model_id!r}")
        if self.prompt_version != prompt_version:
            mismatches.append(
                f"prompt_version {self.prompt_version!r} != {prompt_version!r}"
            )
        if self.prompt_sha256 != prompt_sha256:
            mismatches.append("prompt_sha256 mismatch")
        if mismatches:
            raise ValueError("incompatible calibration artifact: " + "; ".join(mismatches))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_sha256,
            "dataset_sha256": self.dataset_sha256,
            "created_from_commit": self.created_from_commit,
            "base_mapping": dict(self.base_mapping),
            "calibrated_mapping": dict(self.calibrated_mapping),
            "sample_counts": {key: dict(value) for key, value in self.sample_counts.items()},
            "metrics": dict(self.metrics),
            "metadata": dict(self.metadata),
        }

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        return destination

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "OrdinalCalibrationArtifact":
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            artifact_id=str(data.get("artifact_id", "")),
            model_id=str(data.get("model_id", "")),
            prompt_version=str(data.get("prompt_version", "")),
            prompt_sha256=str(data.get("prompt_sha256", "")),
            dataset_sha256=str(data.get("dataset_sha256", "")),
            created_from_commit=str(data.get("created_from_commit", "")),
            base_mapping={key: float(value) for key, value in dict(data.get("base_mapping", {})).items()},
            calibrated_mapping={
                key: float(value)
                for key, value in dict(data.get("calibrated_mapping", {})).items()
            },
            sample_counts={
                key: {name: int(value) for name, value in dict(counts).items()}
                for key, counts in dict(data.get("sample_counts", {})).items()
            },
            metrics={key: float(value) for key, value in dict(data.get("metrics", {})).items()},
            metadata=dict(data.get("metadata", {})),
        )

    @classmethod
    def load(cls, path: str | Path) -> "OrdinalCalibrationArtifact":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("calibration artifact must be a JSON object")
        return cls.from_mapping(payload)


def _weighted_pav(values: Sequence[float], weights: Sequence[float]) -> List[float]:
    if len(values) != len(weights) or not values:
        raise ValueError("PAV requires equally sized non-empty values and weights")
    blocks: List[Dict[str, Any]] = []
    for index, (value, weight) in enumerate(zip(values, weights)):
        if weight <= 0:
            raise ValueError("PAV weights must be positive")
        blocks.append(
            {"start": index, "end": index, "weight": float(weight), "mean": float(value)}
        )
        while len(blocks) >= 2 and blocks[-2]["mean"] > blocks[-1]["mean"]:
            right = blocks.pop()
            left = blocks.pop()
            total_weight = left["weight"] + right["weight"]
            blocks.append(
                {
                    "start": left["start"],
                    "end": right["end"],
                    "weight": total_weight,
                    "mean": (
                        left["mean"] * left["weight"]
                        + right["mean"] * right["weight"]
                    )
                    / total_weight,
                }
            )
    result = [0.0] * len(values)
    for block in blocks:
        for index in range(block["start"], block["end"] + 1):
            result[index] = float(block["mean"])
    return result


def _fill_missing_monotone(
    observed_indices: Sequence[int], observed_values: Sequence[float]
) -> List[float]:
    if not observed_indices:
        raise ValueError("at least one observed ordinal level is required")
    result = [0.0] * len(ORDINAL_LEVELS)
    for index in range(len(ORDINAL_LEVELS)):
        if index <= observed_indices[0]:
            result[index] = float(observed_values[0])
            continue
        if index >= observed_indices[-1]:
            result[index] = float(observed_values[-1])
            continue
        for left_pos in range(len(observed_indices) - 1):
            left_index = observed_indices[left_pos]
            right_index = observed_indices[left_pos + 1]
            if left_index <= index <= right_index:
                if right_index == left_index:
                    result[index] = float(observed_values[left_pos])
                else:
                    fraction = (index - left_index) / (right_index - left_index)
                    result[index] = (
                        observed_values[left_pos]
                        + fraction
                        * (observed_values[left_pos + 1] - observed_values[left_pos])
                    )
                break
    return result


def _metrics(samples: Sequence[OrdinalCalibrationSample], mapping: Mapping[str, float]) -> Dict[str, float]:
    if not samples:
        raise ValueError("metrics require at least one sample")
    squared = 0.0
    nll = 0.0
    grouped: Dict[str, List[int]] = {level: [] for level in ORDINAL_LEVELS}
    for sample in samples:
        probability = min(1.0 - _EPS, max(_EPS, float(mapping[sample.confidence_level])))
        squared += (probability - sample.label) ** 2
        nll -= sample.label * math.log(probability) + (1 - sample.label) * math.log(
            1.0 - probability
        )
        grouped[sample.confidence_level].append(sample.label)
    ece = 0.0
    total = len(samples)
    for level in ORDINAL_LEVELS:
        labels = grouped[level]
        if not labels:
            continue
        empirical = sum(labels) / len(labels)
        ece += (len(labels) / total) * abs(float(mapping[level]) - empirical)
    return {
        "brier": squared / total,
        "nll": nll / total,
        "ece": ece,
    }


def fit_ordinal_calibration(
    samples: Iterable[OrdinalCalibrationSample],
    *,
    model_id: str,
    prompt_version: str,
    prompt_sha256: str,
    created_from_commit: str,
    alpha: float = 1.0,
    min_total_samples: int = 1,
    min_observed_levels: int = 1,
    metadata: Mapping[str, Any] | None = None,
) -> OrdinalCalibrationArtifact:
    if alpha <= 0:
        raise ValueError("alpha must be positive")
    normalized_samples = tuple(samples)
    if len(normalized_samples) < min_total_samples:
        raise ValueError(
            f"need at least {min_total_samples} samples, got {len(normalized_samples)}"
        )
    per_level: Dict[str, List[int]] = {level: [] for level in ORDINAL_LEVELS}
    for sample in normalized_samples:
        per_level[sample.confidence_level].append(sample.label)
    observed_levels = [level for level in ORDINAL_LEVELS if per_level[level]]
    if len(observed_levels) < min_observed_levels:
        raise ValueError(
            f"need at least {min_observed_levels} observed levels, got {len(observed_levels)}"
        )

    observed_indices: List[int] = []
    smoothed_rates: List[float] = []
    pav_weights: List[float] = []
    sample_counts: Dict[str, Dict[str, int]] = {}
    for index, level in enumerate(ORDINAL_LEVELS):
        labels = per_level[level]
        positives = sum(labels)
        negatives = len(labels) - positives
        sample_counts[level] = {
            "total": len(labels),
            "positive": positives,
            "negative": negatives,
        }
        if labels:
            observed_indices.append(index)
            smoothed_rates.append((positives + alpha) / (len(labels) + 2.0 * alpha))
            pav_weights.append(len(labels) + 2.0 * alpha)

    monotone_observed = _weighted_pav(smoothed_rates, pav_weights)
    all_values = _fill_missing_monotone(observed_indices, monotone_observed)
    calibrated_mapping = {
        level: float(all_values[index]) for index, level in enumerate(ORDINAL_LEVELS)
    }
    validate_mapping(calibrated_mapping, label="calibrated_mapping")

    canonical_samples = sorted(
        (sample.to_dict() for sample in normalized_samples),
        key=lambda item: (
            ORDINAL_LEVELS.index(item["confidence_level"]),
            item["label"],
            item["source_id"],
        ),
    )
    dataset_sha256 = _sha256(canonical_samples)
    base_metrics = _metrics(normalized_samples, BASE_ORDINAL_MAPPING)
    calibrated_metrics = _metrics(normalized_samples, calibrated_mapping)
    metrics = {
        "base_brier": base_metrics["brier"],
        "base_nll": base_metrics["nll"],
        "base_ece": base_metrics["ece"],
        "calibrated_brier": calibrated_metrics["brier"],
        "calibrated_nll": calibrated_metrics["nll"],
        "calibrated_ece": calibrated_metrics["ece"],
    }
    artifact_payload = {
        "schema_version": 1,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "dataset_sha256": dataset_sha256,
        "created_from_commit": created_from_commit,
        "base_mapping": BASE_ORDINAL_MAPPING,
        "calibrated_mapping": calibrated_mapping,
        "sample_counts": sample_counts,
        "metrics": metrics,
        "metadata": dict(metadata or {}),
    }
    artifact_id = _sha256(artifact_payload)
    return OrdinalCalibrationArtifact(
        schema_version=1,
        artifact_id=artifact_id,
        model_id=str(model_id),
        prompt_version=str(prompt_version),
        prompt_sha256=str(prompt_sha256),
        dataset_sha256=dataset_sha256,
        created_from_commit=str(created_from_commit),
        base_mapping=dict(BASE_ORDINAL_MAPPING),
        calibrated_mapping=calibrated_mapping,
        sample_counts=sample_counts,
        metrics=metrics,
        metadata=dict(metadata or {}),
    )
