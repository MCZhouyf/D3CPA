"""Freeze Round 5.11 train/tune Fusion features without fitting Fusion.

Round 5.11 ends after exporting immutable features derived from the frozen
Knowledge evidence, ordinal Confidence release, and Environment release.
Monotonic logistic fitting and locked holdout use belong to Round 5.12.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
ACTIVE_ROLES = frozenset({"dev_train", "dev_tune"})


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class FusionFeatureExportRecord:
    feature_record_id: str
    source_decision_record_id: str
    source_decision_record_hash: str
    role: str
    group_id: str
    task: str
    seed: str
    decision_index: int
    hard_feasible: bool
    knowledge_coverage: float
    knowledge_unknown: bool
    confidence_probability: float
    environment_probability: float
    decision_correct: bool
    development_input_release_id: str
    confidence_calibration_release_id: str
    environment_evidence_release_id: str
    paper_memory_v5_release_id: str
    schema_version: int = SCHEMA_VERSION
    feature_hash: str = ""

    def __post_init__(self) -> None:
        required = (
            self.feature_record_id,
            self.source_decision_record_id,
            self.source_decision_record_hash,
            self.group_id,
            self.task,
            self.seed,
            self.development_input_release_id,
            self.confidence_calibration_release_id,
            self.environment_evidence_release_id,
            self.paper_memory_v5_release_id,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Fusion feature identity is incomplete")
        if self.role not in ACTIVE_ROLES:
            raise ValueError("Fusion feature role must be train or tune")
        if self.task == "mine sand":
            raise ValueError("Fusion feature contains superseded task")
        if self.decision_index < 0:
            raise ValueError("Fusion decision index cannot be negative")
        for value in (
            self.knowledge_coverage,
            self.confidence_probability,
            self.environment_probability,
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError("Fusion feature is outside [0,1]")
        expected = self.compute_feature_hash()
        if self.feature_hash and self.feature_hash != expected:
            raise ValueError("Fusion feature hash mismatch")

    @property
    def numeric_features(self) -> tuple[float, float, float, float]:
        return (
            float(self.knowledge_coverage),
            1.0 if self.knowledge_unknown else 0.0,
            float(self.confidence_probability),
            float(self.environment_probability),
        )

    def payload_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("feature_hash", None)
        payload["numeric_features"] = list(self.numeric_features)
        return payload

    def compute_feature_hash(self) -> str:
        return _sha(self.payload_without_hash())

    def with_hash(self) -> "FusionFeatureExportRecord":
        return replace(self, feature_hash=self.compute_feature_hash())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.feature_hash else self.with_hash()
        payload = item.payload_without_hash()
        payload["feature_hash"] = item.feature_hash
        return payload


@dataclass(frozen=True)
class FusionFeatureDatasetRelease:
    release_name: str
    source_commit: str
    development_input_release_id: str
    collection_audit_id: str
    confidence_calibration_release_id: str
    environment_evidence_release_id: str
    paper_memory_v5_release_id: str
    active_taskset_release_id: str
    train_jsonl_sha256: str
    tune_jsonl_sha256: str
    train_dataset_id: str
    tune_dataset_id: str
    train_record_count: int
    tune_record_count: int
    hard_infeasible_train_count: int
    hard_infeasible_tune_count: int
    feature_order: tuple[str, ...]
    hard_feasibility_is_external_gate: bool
    fusion_fitted: bool
    holdout_used: bool
    final_evaluation_used: bool
    eligible: bool
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        if self.train_record_count <= 0 or self.tune_record_count <= 0:
            raise ValueError("Fusion train/tune datasets must be nonempty")
        if self.feature_order != (
            "knowledge_coverage",
            "knowledge_unknown",
            "confidence_probability",
            "environment_probability",
        ):
            raise ValueError("Fusion feature order changed")
        if not self.hard_feasibility_is_external_gate:
            raise ValueError("Knowledge hard feasibility must remain an external gate")
        if self.fusion_fitted:
            raise ValueError("Round 5.11 may not fit Fusion")
        if self.holdout_used or self.final_evaluation_used:
            raise ValueError("Fusion feature release used protected data")
        if not self.eligible:
            raise ValueError("Cannot freeze an ineligible Fusion feature release")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("Fusion feature release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        payload["feature_order"] = list(self.feature_order)
        return payload

    def compute_release_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FusionFeatureDatasetRelease":
        return replace(self, release_id=self.compute_release_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.release_id else self.with_id()
        payload = item.payload_without_id()
        payload["release_id"] = item.release_id
        return payload


def write_jsonl_immutable(
    path: str | Path,
    records: Sequence[FusionFeatureExportRecord],
) -> None:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(
            json.dumps(item.to_dict(), sort_keys=True) + "\n"
            for item in sorted(records, key=lambda value: value.feature_record_id)
        ),
        encoding="utf-8",
    )


def _dataset_id(records: Sequence[FusionFeatureExportRecord]) -> str:
    return _sha(
        [
            {
                "feature_record_id": item.feature_record_id,
                "feature_hash": item.feature_hash or item.compute_feature_hash(),
            }
            for item in sorted(records, key=lambda value: value.feature_record_id)
        ]
    )


def freeze_fusion_feature_dataset(
    *,
    release_name: str,
    source_commit: str,
    development_input_release_id: str,
    collection_audit_id: str,
    confidence_calibration_release_id: str,
    environment_evidence_release_id: str,
    paper_memory_v5_release_id: str,
    active_taskset_release_id: str,
    train_records: Sequence[FusionFeatureExportRecord],
    tune_records: Sequence[FusionFeatureExportRecord],
    train_jsonl_path: str | Path,
    tune_jsonl_path: str | Path,
) -> FusionFeatureDatasetRelease:
    if any(item.role != "dev_train" for item in train_records):
        raise ValueError("Fusion train export contains non-train records")
    if any(item.role != "dev_tune" for item in tune_records):
        raise ValueError("Fusion tune export contains non-tune records")
    all_records = tuple(train_records) + tuple(tune_records)
    for item in all_records:
        expected = (
            development_input_release_id,
            confidence_calibration_release_id,
            environment_evidence_release_id,
            paper_memory_v5_release_id,
        )
        actual = (
            item.development_input_release_id,
            item.confidence_calibration_release_id,
            item.environment_evidence_release_id,
            item.paper_memory_v5_release_id,
        )
        if actual != expected:
            raise ValueError(
                f"{item.feature_record_id}: Fusion release binding mismatch"
            )
    if len({item.feature_record_id for item in all_records}) != len(all_records):
        raise ValueError("Fusion feature IDs are not unique")

    write_jsonl_immutable(train_jsonl_path, train_records)
    write_jsonl_immutable(tune_jsonl_path, tune_records)
    return FusionFeatureDatasetRelease(
        release_name=release_name,
        source_commit=source_commit,
        development_input_release_id=development_input_release_id,
        collection_audit_id=collection_audit_id,
        confidence_calibration_release_id=confidence_calibration_release_id,
        environment_evidence_release_id=environment_evidence_release_id,
        paper_memory_v5_release_id=paper_memory_v5_release_id,
        active_taskset_release_id=active_taskset_release_id,
        train_jsonl_sha256=sha256_file(train_jsonl_path),
        tune_jsonl_sha256=sha256_file(tune_jsonl_path),
        train_dataset_id=_dataset_id(train_records),
        tune_dataset_id=_dataset_id(tune_records),
        train_record_count=len(train_records),
        tune_record_count=len(tune_records),
        hard_infeasible_train_count=sum(
            not item.hard_feasible for item in train_records
        ),
        hard_infeasible_tune_count=sum(
            not item.hard_feasible for item in tune_records
        ),
        feature_order=(
            "knowledge_coverage",
            "knowledge_unknown",
            "confidence_probability",
            "environment_probability",
        ),
        hard_feasibility_is_external_gate=True,
        fusion_fitted=False,
        holdout_used=False,
        final_evaluation_used=False,
        eligible=True,
    ).with_id()
