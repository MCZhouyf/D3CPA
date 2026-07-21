"""Outcome-blind conversion of locked holdout observations to Fusion inputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .round5124_holdout import (
    FINAL_FEATURE_ORDER,
    HoldoutDecisionRecord,
    sha256_file,
)


SCHEMA_VERSION = 1


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _load_json(path: str | Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def load_holdout_decisions(path: str | Path) -> tuple[HoldoutDecisionRecord, ...]:
    records = []
    tuple_fields = {
        "returned_model_identities",
        "knowledge_missing_prerequisites",
        "environment_topk_exemplar_ids",
        "environment_topk_similarities",
    }
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        for name in tuple_fields:
            payload[name] = tuple(payload[name])
        records.append(HoldoutDecisionRecord(**payload))
    if not records:
        raise ValueError("Locked holdout decision dataset is empty")
    return tuple(records)


@dataclass(frozen=True)
class HoldoutFusionFeatureRecord:
    feature_record_id: str
    source_decision_record_id: str
    source_decision_record_hash: str
    group_id: str
    task: str
    seed: str
    difficulty: str
    run_id: str
    decision_index: int
    hard_feasible: bool
    features: Mapping[str, float]
    label: int
    legacy_probability: float
    equal_weight_probability: float
    confidence_release_id: str
    environment_release_id: str
    candidate_artifact_id: str
    final_runtime_release_id: str
    schema_version: int = SCHEMA_VERSION
    feature_hash: str = ""

    def __post_init__(self) -> None:
        if tuple(self.features) != FINAL_FEATURE_ORDER:
            raise ValueError("Holdout Fusion feature order changed")
        if self.label not in {0, 1} or self.decision_index < 0:
            raise ValueError("Holdout Fusion label/index is invalid")
        for value in (*self.features.values(), self.legacy_probability, self.equal_weight_probability):
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError("Holdout Fusion value is outside [0,1]")
        if not self.hard_feasible and (
            self.legacy_probability != 0.0 or self.equal_weight_probability != 0.0
        ):
            raise ValueError("Hard-infeasible holdout baselines must be zero")
        expected = self.compute_feature_hash()
        if self.feature_hash and self.feature_hash != expected:
            raise ValueError("Holdout Fusion feature hash mismatch")

    def payload_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("feature_hash", None)
        payload["features"] = {
            name: float(self.features[name]) for name in FINAL_FEATURE_ORDER
        }
        return payload

    def compute_feature_hash(self) -> str:
        return _sha(self.payload_without_hash())

    def with_hash(self) -> "HoldoutFusionFeatureRecord":
        return replace(self, feature_hash=self.compute_feature_hash())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.feature_hash else self.with_hash()
        return {**item.payload_without_hash(), "feature_hash": item.feature_hash}


def load_holdout_features(path: str | Path) -> tuple[HoldoutFusionFeatureRecord, ...]:
    records = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            payload["features"] = {
                name: float(payload["features"][name])
                for name in FINAL_FEATURE_ORDER
            }
            records.append(HoldoutFusionFeatureRecord(**payload))
    if not records:
        raise ValueError("Locked holdout Fusion dataset is empty")
    return tuple(records)


def _environment_state(record: HoldoutDecisionRecord, candidate: Mapping[str, Any]) -> str:
    maximum = max(record.environment_topk_similarities, default=0.0)
    if (
        not record.environment_topk_exemplar_ids
        or maximum < float(candidate["minimum_similarity"])
        or record.environment_coverage < float(candidate["minimum_coverage"])
    ):
        return "unknown"
    if record.environment_compatibility >= float(candidate["match_compatibility_threshold"]):
        return "matched"
    if record.environment_compatibility <= float(candidate["mismatch_compatibility_threshold"]):
        return "mismatch"
    return "unknown"


def export_holdout_features(
    *,
    decisions_path: str | Path,
    confidence_release_path: str | Path,
    environment_release_path: str | Path,
    candidate_path: str | Path,
    runtime_release_path: str | Path,
    output_path: str | Path,
) -> Mapping[str, Any]:
    confidence = _load_json(confidence_release_path)
    environment = _load_json(environment_release_path)
    candidate_artifact = _load_json(candidate_path)
    runtime = _load_json(runtime_release_path)
    if sha256_file(candidate_path) != runtime["candidate_artifact_sha256"]:
        raise ValueError("Candidate changed after holdout runtime freeze")
    if candidate_artifact["artifact_id"] != runtime["candidate_artifact_id"]:
        raise ValueError("Candidate identity changed after holdout runtime freeze")
    confidence_map = {
        item["level"]: float(item["calibrated_probability"])
        for item in confidence["levels"]
    }
    selected = environment["selected_result"]
    environment_probabilities = {
        name: float(value) for name, value in selected["state_probabilities"].items()
    }
    records = []
    for decision in load_holdout_decisions(decisions_path):
        state = _environment_state(decision, selected["candidate"])
        features = {
            "knowledge_coverage": float(decision.knowledge_coverage),
            "knowledge_known": 0.0 if decision.knowledge_unknown else 1.0,
            "confidence_probability": confidence_map[decision.confidence_level],
            "environment_probability": environment_probabilities[state],
        }
        feasible = bool(decision.knowledge_hard_feasible)
        legacy = (
            0.4 * features["knowledge_coverage"]
            + 0.2 * features["confidence_probability"]
            + 0.4 * features["environment_probability"]
            if feasible
            else 0.0
        )
        equal = sum(features.values()) / 4.0 if feasible else 0.0
        records.append(
            HoldoutFusionFeatureRecord(
                feature_record_id=_sha(
                    {
                        "source": decision.record_id,
                        "confidence": confidence["release_id"],
                        "environment": environment["release_id"],
                        "candidate": candidate_artifact["artifact_id"],
                        "runtime": runtime["release_id"],
                    }
                ),
                source_decision_record_id=decision.record_id,
                source_decision_record_hash=decision.record_hash,
                group_id=decision.group_id,
                task=decision.task,
                seed=decision.seed,
                difficulty=decision.difficulty,
                run_id=decision.run_id,
                decision_index=decision.decision_index,
                hard_feasible=feasible,
                features=features,
                label=int(decision.decision_correct),
                legacy_probability=legacy,
                equal_weight_probability=equal,
                confidence_release_id=str(confidence["release_id"]),
                environment_release_id=str(environment["release_id"]),
                candidate_artifact_id=str(candidate_artifact["artifact_id"]),
                final_runtime_release_id=str(runtime["release_id"]),
            ).with_hash()
        )
    if len({item.feature_record_id for item in records}) != len(records):
        raise ValueError("Duplicate locked holdout Fusion feature IDs")
    output = Path(output_path)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(
            json.dumps(item.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
            for item in sorted(records, key=lambda value: value.feature_record_id)
        ),
        encoding="utf-8",
    )
    summary = {
        "schema_version": SCHEMA_VERSION,
        "record_count": len(records),
        "positive_count": sum(item.label for item in records),
        "negative_count": sum(not item.label for item in records),
        "task_count": len({item.task for item in records}),
        "group_count": len({item.group_id for item in records}),
        "dataset_sha256": sha256_file(output),
        "candidate_artifact_id": candidate_artifact["artifact_id"],
        "final_runtime_release_id": runtime["release_id"],
    }
    summary["summary_id"] = _sha(summary)
    return summary
