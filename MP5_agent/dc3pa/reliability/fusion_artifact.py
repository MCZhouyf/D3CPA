"""Strict, hash-bound artifact for monotonic Logistic fusion."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional

from .fusion_features import FEATURE_SCHEMA_VERSION, FUSION_FEATURE_NAMES


FUSION_ARTIFACT_SCHEMA_VERSION = 1
FUSION_IMPLS = frozenset(
    {
        "legacy_memory_weighted",
        "monotonic_logistic_shadow",
        "monotonic_logistic_v2",
    }
)


def validate_fusion_impl(value: str) -> str:
    candidate = str(value or "").strip().lower()
    if candidate not in FUSION_IMPLS:
        raise ValueError(
            f"fusion_impl must be one of {sorted(FUSION_IMPLS)}, got {value!r}"
        )
    return candidate


def _canonical(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric, not bool")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


@dataclass(frozen=True)
class FusionArtifact:
    feature_schema_version: str
    knowledge_impl: str
    model_confidence_impl: str
    environment_impl: str
    environment_scope: str
    knowledge_unknown_prior: float
    environment_unknown_compatibility: float
    intercept: float
    coefficients: Mapping[str, float]
    dataset_sha256: str
    memory_snapshot_sha256: str
    confidence_artifact_id: str
    created_from_commit: str
    training_metrics: Mapping[str, Any] = field(default_factory=dict)
    validation_metrics: Mapping[str, Any] = field(default_factory=dict)
    trainer_config: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = FUSION_ARTIFACT_SCHEMA_VERSION
    artifact_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != FUSION_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("Unsupported fusion artifact schema")
        if self.feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise ValueError("Feature schema mismatch")
        if set(self.coefficients) != set(FUSION_FEATURE_NAMES):
            raise ValueError(
                f"coefficients must contain exactly {FUSION_FEATURE_NAMES}"
            )
        for name, value in self.coefficients.items():
            if _finite(value, name) < 0.0:
                raise ValueError(f"{name} coefficient must be nonnegative")
        _finite(self.intercept, "intercept")
        for name, value in (
            ("knowledge_unknown_prior", self.knowledge_unknown_prior),
            (
                "environment_unknown_compatibility",
                self.environment_unknown_compatibility,
            ),
        ):
            number = _finite(value, name)
            if not 0.0 <= number <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        for name, value in (
            ("dataset_sha256", self.dataset_sha256),
            ("memory_snapshot_sha256", self.memory_snapshot_sha256),
            ("confidence_artifact_id", self.confidence_artifact_id),
            ("created_from_commit", self.created_from_commit),
        ):
            if not str(value).strip():
                raise ValueError(f"{name} is required")
        expected = self.compute_artifact_id()
        if self.artifact_id and self.artifact_id != expected:
            raise ValueError("Fusion artifact hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("artifact_id", None)
        payload["coefficients"] = dict(sorted(self.coefficients.items()))
        payload["training_metrics"] = dict(self.training_metrics)
        payload["validation_metrics"] = dict(self.validation_metrics)
        payload["trainer_config"] = dict(self.trainer_config)
        return payload

    def compute_artifact_id(self) -> str:
        return hashlib.sha256(_canonical(self.payload_without_id())).hexdigest()

    def with_id(self) -> "FusionArtifact":
        return replace(self, artifact_id=self.compute_artifact_id())

    def to_dict(self) -> dict[str, Any]:
        artifact = self if self.artifact_id else self.with_id()
        payload = artifact.payload_without_id()
        payload["artifact_id"] = artifact.artifact_id
        return payload

    def validate_runtime(
        self,
        *,
        knowledge_impl: str,
        model_confidence_impl: str,
        environment_impl: str,
        environment_scope: str,
        memory_snapshot_sha256: str,
        confidence_artifact_id: str,
    ) -> None:
        expected = {
            "knowledge_impl": self.knowledge_impl,
            "model_confidence_impl": self.model_confidence_impl,
            "environment_impl": self.environment_impl,
            "environment_scope": self.environment_scope,
            "memory_snapshot_sha256": self.memory_snapshot_sha256,
            "confidence_artifact_id": self.confidence_artifact_id,
        }
        actual = {
            "knowledge_impl": knowledge_impl,
            "model_confidence_impl": model_confidence_impl,
            "environment_impl": environment_impl,
            "environment_scope": environment_scope,
            "memory_snapshot_sha256": memory_snapshot_sha256,
            "confidence_artifact_id": confidence_artifact_id,
        }
        mismatches = {
            key: {"expected": expected[key], "actual": actual[key]}
            for key in expected
            if str(expected[key]) != str(actual[key])
        }
        if mismatches:
            raise ValueError(f"Fusion artifact runtime mismatch: {mismatches}")


def save_fusion_artifact(path: Path, artifact: FusionArtifact) -> str:
    artifact = artifact.with_id()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return artifact.artifact_id


def load_fusion_artifact(path: Path) -> FusionArtifact:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return FusionArtifact(**payload)
