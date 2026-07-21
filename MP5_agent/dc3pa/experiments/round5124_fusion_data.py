"""Feature direction, baselines, and pre-fit qualification for Round 5.12.4."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .round5124_contracts import assert_standard_fusion_feature_names


SCHEMA_VERSION = 1
RAW_FEATURE_ORDER = (
    "knowledge_coverage",
    "knowledge_unknown",
    "confidence_probability",
    "environment_probability",
)
FINAL_FEATURE_ORDER = (
    "knowledge_coverage",
    "knowledge_known",
    "confidence_probability",
    "environment_probability",
)
LEGACY_WEIGHTS = {
    "knowledge_coverage": 0.4,
    "confidence_probability": 0.2,
    "environment_probability": 0.4,
}


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


def _probability(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be finite and in [0,1]")
    return result


@dataclass(frozen=True)
class DirectedFusionFeatureRecord:
    feature_record_id: str
    source_decision_record_id: str
    source_decision_record_hash: str
    source_feature_hash: str
    role: str
    group_id: str
    task: str
    seed: str
    decision_index: int
    hard_feasible: bool
    features: Mapping[str, float]
    label: int
    legacy_probability: float
    equal_weight_probability: float
    development_input_release_id: str
    confidence_calibration_release_id: str
    environment_evidence_release_id: str
    paper_memory_v5_release_id: str
    schema_version: int = SCHEMA_VERSION
    transformed_feature_hash: str = ""

    def __post_init__(self) -> None:
        required = (
            self.feature_record_id,
            self.source_decision_record_id,
            self.source_decision_record_hash,
            self.source_feature_hash,
            self.group_id,
            self.task,
            self.seed,
            self.development_input_release_id,
            self.confidence_calibration_release_id,
            self.environment_evidence_release_id,
            self.paper_memory_v5_release_id,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Directed Fusion feature identity is incomplete")
        if self.role not in {"dev_train", "dev_tune"}:
            raise ValueError("Directed Fusion role is not train/tune")
        if self.task == "mine sand":
            raise ValueError("Directed Fusion record contains mine sand")
        if self.decision_index < 0 or self.label not in {0, 1}:
            raise ValueError("Directed Fusion index or label is invalid")
        if tuple(self.features) != FINAL_FEATURE_ORDER:
            raise ValueError("Directed Fusion feature order changed")
        assert_standard_fusion_feature_names(tuple(self.features))
        for name, value in self.features.items():
            _probability(value, name)
        _probability(self.legacy_probability, "legacy_probability")
        _probability(self.equal_weight_probability, "equal_weight_probability")
        if not self.hard_feasible and (
            self.legacy_probability != 0.0
            or self.equal_weight_probability != 0.0
        ):
            raise ValueError("Hard infeasible baselines must be zero")
        expected = self.compute_transformed_feature_hash()
        if self.transformed_feature_hash and self.transformed_feature_hash != expected:
            raise ValueError("Directed Fusion feature hash mismatch")

    def payload_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("transformed_feature_hash", None)
        payload["features"] = {
            name: float(self.features[name]) for name in FINAL_FEATURE_ORDER
        }
        return payload

    def compute_transformed_feature_hash(self) -> str:
        return _sha(self.payload_without_hash())

    def with_hash(self) -> "DirectedFusionFeatureRecord":
        return replace(
            self,
            transformed_feature_hash=self.compute_transformed_feature_hash(),
        )

    def to_dict(self) -> dict[str, Any]:
        item = self if self.transformed_feature_hash else self.with_hash()
        return {
            **item.payload_without_hash(),
            "transformed_feature_hash": item.transformed_feature_hash,
        }


@dataclass(frozen=True)
class FusionFeatureDirectionPolicy:
    source_commit: str
    raw_fusion_feature_release_id: str
    raw_train_sha256: str
    raw_tune_sha256: str
    transformed_train_sha256: str
    transformed_tune_sha256: str
    raw_feature_order: tuple[str, ...]
    final_feature_order: tuple[str, ...]
    transform: str
    hard_feasibility_is_external_gate: bool
    train_record_count: int
    tune_record_count: int
    train_record_ids_preserved: bool
    tune_record_ids_preserved: bool
    train_labels_preserved: bool
    tune_labels_preserved: bool
    outcome_dependent_transform: bool
    interaction_terms_added: bool
    forbidden_predictive_features_added: bool
    legacy_baseline_definition: Mapping[str, Any]
    equal_weight_baseline_definition: Mapping[str, Any]
    holdout_used: bool
    final_evaluation_used: bool
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        if not self.source_commit:
            raise ValueError("Feature direction source commit is required")
        if self.raw_feature_order != RAW_FEATURE_ORDER:
            raise ValueError("Raw Fusion feature order changed")
        if self.final_feature_order != FINAL_FEATURE_ORDER:
            raise ValueError("Final Fusion feature order changed")
        assert_standard_fusion_feature_names(self.final_feature_order)
        if self.transform != "knowledge_known=1-knowledge_unknown":
            raise ValueError("Knowledge feature direction transform changed")
        if not self.hard_feasibility_is_external_gate:
            raise ValueError("Knowledge hard feasibility gate was removed")
        if (self.train_record_count, self.tune_record_count) != (528, 153):
            raise ValueError("Directed Fusion row counts changed")
        if not all(
            (
                self.train_record_ids_preserved,
                self.tune_record_ids_preserved,
                self.train_labels_preserved,
                self.tune_labels_preserved,
            )
        ):
            raise ValueError("Feature direction changed IDs or labels")
        if any(
            (
                self.outcome_dependent_transform,
                self.interaction_terms_added,
                self.forbidden_predictive_features_added,
                self.holdout_used,
                self.final_evaluation_used,
            )
        ):
            raise ValueError("Feature direction policy used forbidden information")
        if dict(self.legacy_baseline_definition).get("successful_memory_count") != 40:
            raise ValueError("Legacy baseline memory count changed")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("Feature direction policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["raw_feature_order"] = list(self.raw_feature_order)
        payload["final_feature_order"] = list(self.final_feature_order)
        payload["legacy_baseline_definition"] = dict(
            self.legacy_baseline_definition
        )
        payload["equal_weight_baseline_definition"] = dict(
            self.equal_weight_baseline_definition
        )
        return payload

    def compute_policy_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FusionFeatureDirectionPolicy":
        return replace(self, policy_id=self.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.policy_id else self.with_id()
        return {**item.payload_without_id(), "policy_id": item.policy_id}


@dataclass(frozen=True)
class PreFusionQualificationReport:
    source_commit: str
    standard_acceptance_id: str
    standard_closeout_id: str
    confidence_release_id: str
    environment_release_id: str
    fusion_feature_release_id: str
    feature_direction_policy_id: str
    l2_provenance_audit_id: str
    bootstrap_policy_id: str
    train_rows: int
    tune_rows: int
    train_units: int
    tune_units: int
    train_tune_group_overlap: int
    train_tune_task_seed_overlap: int
    duplicate_feature_ids: int
    nan_or_inf_values: int
    missing_labels_or_features: int
    holdout_or_final_rows: int
    both_labels_present_train: bool
    both_labels_present_tune: bool
    all_component_release_bindings_valid: bool
    legacy_baseline_reproducible: bool
    equal_weight_baseline_reproducible: bool
    runtime_segment_is_predictive_feature: bool
    eligible: bool
    errors: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION
    report_id: str = ""

    def __post_init__(self) -> None:
        required = (
            self.source_commit,
            self.standard_acceptance_id,
            self.standard_closeout_id,
            self.confidence_release_id,
            self.environment_release_id,
            self.fusion_feature_release_id,
            self.feature_direction_policy_id,
            self.l2_provenance_audit_id,
            self.bootstrap_policy_id,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Pre-Fusion binding is incomplete")
        exact = (
            self.train_rows,
            self.tune_rows,
            self.train_units,
            self.tune_units,
            self.train_tune_group_overlap,
            self.train_tune_task_seed_overlap,
            self.duplicate_feature_ids,
            self.nan_or_inf_values,
            self.missing_labels_or_features,
            self.holdout_or_final_rows,
        )
        if exact != (528, 153, 45, 15, 0, 0, 0, 0, 0, 0):
            raise ValueError(f"Pre-Fusion accounting failed: {exact}")
        if not all(
            (
                self.both_labels_present_train,
                self.both_labels_present_tune,
                self.all_component_release_bindings_valid,
                self.legacy_baseline_reproducible,
                self.equal_weight_baseline_reproducible,
            )
        ):
            raise ValueError("Pre-Fusion prerequisite failed")
        if self.runtime_segment_is_predictive_feature:
            raise ValueError("Runtime segment entered Fusion features")
        if not self.eligible or self.errors:
            raise ValueError("Cannot freeze ineligible Pre-Fusion report")
        expected = self.compute_report_id()
        if self.report_id and self.report_id != expected:
            raise ValueError("Pre-Fusion report hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("report_id", None)
        payload["errors"] = list(self.errors)
        return payload

    def compute_report_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "PreFusionQualificationReport":
        return replace(self, report_id=self.compute_report_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.report_id else self.with_id()
        return {**item.payload_without_id(), "report_id": item.report_id}


def _read_json(path: str | Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _read_jsonl(path: str | Path) -> list[Mapping[str, Any]]:
    rows = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ValueError(f"Expected JSON object at {path}:{line_number}")
        rows.append(value)
    return rows


def _write_jsonl_immutable(
    path: str | Path,
    records: Sequence[DirectedFusionFeatureRecord],
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


def transform_raw_record(record: Mapping[str, Any]) -> DirectedFusionFeatureRecord:
    if list(record.get("numeric_features", ())) != [
        record.get("knowledge_coverage"),
        1.0 if record.get("knowledge_unknown") else 0.0,
        record.get("confidence_probability"),
        record.get("environment_probability"),
    ]:
        raise ValueError("Raw numeric feature vector is inconsistent")
    features = {
        "knowledge_coverage": _probability(
            record["knowledge_coverage"], "knowledge_coverage"
        ),
        "knowledge_known": 0.0 if bool(record["knowledge_unknown"]) else 1.0,
        "confidence_probability": _probability(
            record["confidence_probability"], "confidence_probability"
        ),
        "environment_probability": _probability(
            record["environment_probability"], "environment_probability"
        ),
    }
    hard_feasible = bool(record["hard_feasible"])
    if hard_feasible:
        legacy = sum(
            LEGACY_WEIGHTS[name] * features[name] for name in LEGACY_WEIGHTS
        )
        equal = sum(features.values()) / len(features)
    else:
        legacy = equal = 0.0
    return DirectedFusionFeatureRecord(
        feature_record_id=str(record["feature_record_id"]),
        source_decision_record_id=str(record["source_decision_record_id"]),
        source_decision_record_hash=str(record["source_decision_record_hash"]),
        source_feature_hash=str(record["feature_hash"]),
        role=str(record["role"]),
        group_id=str(record["group_id"]),
        task=str(record["task"]),
        seed=str(record["seed"]),
        decision_index=int(record["decision_index"]),
        hard_feasible=hard_feasible,
        features=features,
        label=1 if bool(record["decision_correct"]) else 0,
        legacy_probability=legacy,
        equal_weight_probability=equal,
        development_input_release_id=str(record["development_input_release_id"]),
        confidence_calibration_release_id=str(
            record["confidence_calibration_release_id"]
        ),
        environment_evidence_release_id=str(
            record["environment_evidence_release_id"]
        ),
        paper_memory_v5_release_id=str(record["paper_memory_v5_release_id"]),
    ).with_hash()


def freeze_feature_direction(
    *,
    source_commit: str,
    raw_fusion_release_path: str | Path,
    raw_train_path: str | Path,
    raw_tune_path: str | Path,
    transformed_train_path: str | Path,
    transformed_tune_path: str | Path,
) -> tuple[
    FusionFeatureDirectionPolicy,
    tuple[DirectedFusionFeatureRecord, ...],
    tuple[DirectedFusionFeatureRecord, ...],
]:
    release = _read_json(raw_fusion_release_path)
    if tuple(release.get("feature_order", ())) != RAW_FEATURE_ORDER:
        raise ValueError("Raw Fusion release feature order changed")
    if release.get("fusion_fitted") or release.get("holdout_used"):
        raise ValueError("Raw Fusion release opened a protected phase")
    if sha256_file(raw_train_path) != release.get("train_jsonl_sha256"):
        raise ValueError("Raw train feature file hash mismatch")
    if sha256_file(raw_tune_path) != release.get("tune_jsonl_sha256"):
        raise ValueError("Raw tune feature file hash mismatch")
    raw_train = _read_jsonl(raw_train_path)
    raw_tune = _read_jsonl(raw_tune_path)
    train = tuple(transform_raw_record(item) for item in raw_train)
    tune = tuple(transform_raw_record(item) for item in raw_tune)
    _write_jsonl_immutable(transformed_train_path, train)
    _write_jsonl_immutable(transformed_tune_path, tune)
    policy = FusionFeatureDirectionPolicy(
        source_commit=source_commit,
        raw_fusion_feature_release_id=str(release["release_id"]),
        raw_train_sha256=sha256_file(raw_train_path),
        raw_tune_sha256=sha256_file(raw_tune_path),
        transformed_train_sha256=sha256_file(transformed_train_path),
        transformed_tune_sha256=sha256_file(transformed_tune_path),
        raw_feature_order=RAW_FEATURE_ORDER,
        final_feature_order=FINAL_FEATURE_ORDER,
        transform="knowledge_known=1-knowledge_unknown",
        hard_feasibility_is_external_gate=True,
        train_record_count=len(train),
        tune_record_count=len(tune),
        train_record_ids_preserved=(
            [item["feature_record_id"] for item in raw_train]
            == [item.feature_record_id for item in train]
        ),
        tune_record_ids_preserved=(
            [item["feature_record_id"] for item in raw_tune]
            == [item.feature_record_id for item in tune]
        ),
        train_labels_preserved=(
            [bool(item["decision_correct"]) for item in raw_train]
            == [bool(item.label) for item in train]
        ),
        tune_labels_preserved=(
            [bool(item["decision_correct"]) for item in raw_tune]
            == [bool(item.label) for item in tune]
        ),
        outcome_dependent_transform=False,
        interaction_terms_added=False,
        forbidden_predictive_features_added=False,
        legacy_baseline_definition={
            "method": "legacy_memory_weighted_v1_offline_reconstruction",
            "successful_memory_count": 40,
            "learned_weight_cap": 0.4,
            "memory_weight_growth": 0.02,
            "weights": dict(LEGACY_WEIGHTS),
            "hard_feasibility_gate": True,
        },
        equal_weight_baseline_definition={
            "method": "fixed_equal_weight_final_features",
            "weight_per_feature": 0.25,
            "hard_feasibility_gate": True,
        },
        holdout_used=False,
        final_evaluation_used=False,
    ).with_id()
    return policy, train, tune


def qualify_pre_fusion(
    *,
    source_commit: str,
    standard_acceptance_path: str | Path,
    standard_closeout_path: str | Path,
    confidence_release_path: str | Path,
    environment_release_path: str | Path,
    fusion_feature_release_path: str | Path,
    feature_direction_policy: FusionFeatureDirectionPolicy,
    l2_provenance_path: str | Path,
    bootstrap_policy_path: str | Path,
    train_records: Sequence[DirectedFusionFeatureRecord],
    tune_records: Sequence[DirectedFusionFeatureRecord],
) -> PreFusionQualificationReport:
    acceptance = _read_json(standard_acceptance_path)
    closeout = _read_json(standard_closeout_path)
    confidence = _read_json(confidence_release_path)
    environment = _read_json(environment_release_path)
    fusion = _read_json(fusion_feature_release_path)
    l2 = _read_json(l2_provenance_path)
    bootstrap = _read_json(bootstrap_policy_path)
    all_records = tuple(train_records) + tuple(tune_records)
    ids = [item.feature_record_id for item in all_records]
    train_groups = {item.group_id for item in train_records}
    tune_groups = {item.group_id for item in tune_records}
    train_pairs = {(item.task, item.seed) for item in train_records}
    tune_pairs = {(item.task, item.seed) for item in tune_records}
    invalid_values = sum(
        not math.isfinite(float(value))
        for item in all_records
        for value in item.features.values()
    )
    bindings_valid = all(
        item.confidence_calibration_release_id == confidence.get("release_id")
        and item.environment_evidence_release_id == environment.get("release_id")
        and item.paper_memory_v5_release_id == fusion.get("paper_memory_v5_release_id")
        for item in all_records
    )
    return PreFusionQualificationReport(
        source_commit=source_commit,
        standard_acceptance_id=str(acceptance.get("acceptance_id", "")),
        standard_closeout_id=str(closeout.get("closeout_id", "")),
        confidence_release_id=str(confidence.get("release_id", "")),
        environment_release_id=str(environment.get("release_id", "")),
        fusion_feature_release_id=str(fusion.get("release_id", "")),
        feature_direction_policy_id=feature_direction_policy.policy_id,
        l2_provenance_audit_id=str(l2.get("audit_id", "")),
        bootstrap_policy_id=str(bootstrap.get("policy_id", "")),
        train_rows=len(train_records),
        tune_rows=len(tune_records),
        train_units=len(train_groups),
        tune_units=len(tune_groups),
        train_tune_group_overlap=len(train_groups.intersection(tune_groups)),
        train_tune_task_seed_overlap=len(train_pairs.intersection(tune_pairs)),
        duplicate_feature_ids=len(ids) - len(set(ids)),
        nan_or_inf_values=invalid_values,
        missing_labels_or_features=sum(
            item.label not in {0, 1}
            or tuple(item.features) != FINAL_FEATURE_ORDER
            for item in all_records
        ),
        holdout_or_final_rows=sum(
            item.role not in {"dev_train", "dev_tune"} for item in all_records
        ),
        both_labels_present_train={item.label for item in train_records} == {0, 1},
        both_labels_present_tune={item.label for item in tune_records} == {0, 1},
        all_component_release_bindings_valid=bindings_valid,
        legacy_baseline_reproducible=all(
            math.isfinite(item.legacy_probability) for item in all_records
        ),
        equal_weight_baseline_reproducible=all(
            math.isfinite(item.equal_weight_probability) for item in all_records
        ),
        runtime_segment_is_predictive_feature=False,
        eligible=True,
    ).with_id()


def load_directed_jsonl(path: str | Path) -> list[DirectedFusionFeatureRecord]:
    return [DirectedFusionFeatureRecord(**item) for item in _read_jsonl(path)]


def write_json_immutable(path: str | Path, value: Mapping[str, Any]) -> None:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
