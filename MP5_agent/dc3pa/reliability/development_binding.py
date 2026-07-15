"""Strict binding between protocol assignments and actual FusionExample files."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .development_protocol import DevelopmentProtocolManifest
from .final_test_exclusion import FinalTestExclusionManifest
from .fusion_dataset import FusionExample, dataset_sha256
from .fusion_features import FEATURE_SCHEMA_VERSION


COLLECTION_SCHEMA_VERSION = 1
COLLECTION_STATUSES = frozenset(
    {"included", "no_usable_steps", "technical_failure"}
)
ROLE_TO_SPLIT = {
    "dev_train": "train",
    "dev_tune": "validation",
    "dev_holdout": "test",
}


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def activation_policy_id(protocol: DevelopmentProtocolManifest) -> str:
    """Return the semantic policy ID across protocol schema versions."""

    current = str(getattr(protocol, "activation_policy_id", "") or "").strip()
    legacy = str(
        getattr(protocol, "activation_policy_sha256", "") or ""
    ).strip()
    if current and legacy and current != legacy:
        raise ValueError("Conflicting activation policy IDs in protocol")
    value = current or legacy
    if not value:
        raise ValueError("Protocol activation policy ID is missing")
    return value


def environment_parameter_sha256(parameters: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(dict(sorted(parameters.items())))
    ).hexdigest()


@dataclass(frozen=True)
class CollectionOutcome:
    group_id: str
    role: str
    task: str
    seed: str
    status: str
    usable_example_count: int
    exclusion_reason: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in COLLECTION_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(COLLECTION_STATUSES)}"
            )
        if self.usable_example_count < 0:
            raise ValueError("usable_example_count must be nonnegative")
        if self.status == "included" and self.usable_example_count <= 0:
            raise ValueError("included groups need at least one usable example")
        if self.status != "included" and self.usable_example_count != 0:
            raise ValueError("excluded groups cannot claim usable examples")
        if self.status != "included" and not self.exclusion_reason.strip():
            raise ValueError("excluded groups need an explicit reason")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class DevelopmentCollectionManifest:
    manifest_name: str
    protocol_id: str
    final_test_exclusion_id: str
    role: str
    outcomes: tuple[CollectionOutcome, ...]
    source_commit: str
    schema_version: int = COLLECTION_SCHEMA_VERSION
    manifest_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECTION_SCHEMA_VERSION:
            raise ValueError("Unsupported collection schema")
        if self.role not in ROLE_TO_SPLIT:
            raise ValueError(f"Unknown development role {self.role!r}")
        required = (
            self.manifest_name,
            self.protocol_id,
            self.final_test_exclusion_id,
            self.source_commit,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Collection manifest identifiers are required")
        ids = [item.group_id for item in self.outcomes]
        if len(ids) != len(set(ids)):
            raise ValueError("Collection outcome group IDs must be unique")
        if any(item.role != self.role for item in self.outcomes):
            raise ValueError("Collection outcome role mismatch")
        expected = self.compute_manifest_id()
        if self.manifest_id and self.manifest_id != expected:
            raise ValueError("Collection manifest hash mismatch")

    def outcome_map(self) -> dict[str, CollectionOutcome]:
        return {item.group_id: item for item in self.outcomes}

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("manifest_id", None)
        payload["outcomes"] = [
            item.to_dict()
            for item in sorted(self.outcomes, key=lambda item: item.group_id)
        ]
        return payload

    def compute_manifest_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "DevelopmentCollectionManifest":
        return replace(self, manifest_id=self.compute_manifest_id())

    def to_dict(self) -> dict[str, Any]:
        manifest = self if self.manifest_id else self.with_id()
        payload = manifest.payload_without_id()
        payload["manifest_id"] = manifest.manifest_id
        return payload


@dataclass(frozen=True)
class DatasetBindingExpectation:
    role: str
    protocol_id: str
    final_test_exclusion_id: str
    memory_snapshot_sha256: str
    confidence_artifact_id: str
    knowledge_impl: str
    model_confidence_impl: str
    environment_impl: str
    environment_scope: str
    environment_parameter_sha256: str
    source_commit: str
    feature_schema_version: str = FEATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.role not in ROLE_TO_SPLIT:
            raise ValueError(f"Unknown role {self.role!r}")
        values = asdict(self)
        if any(not str(value).strip() for value in values.values()):
            raise ValueError("Dataset binding fields cannot be empty")


@dataclass(frozen=True)
class DatasetBindingReport:
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    summary: Mapping[str, Any]

    def require_eligible(self) -> None:
        if not self.eligible:
            raise ValueError(
                "Development dataset binding failed: " + "; ".join(self.errors)
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "summary": dict(self.summary),
        }


def _example_provenance(example: FusionExample) -> Mapping[str, Any]:
    direct = getattr(example, "provenance", None)
    if isinstance(direct, Mapping) and direct:
        return direct
    metadata = example.metadata if isinstance(example.metadata, Mapping) else {}
    nested = metadata.get("provenance", {})
    return nested if isinstance(nested, Mapping) else {}


def validate_dataset_binding(
    examples: Sequence[FusionExample],
    *,
    protocol: DevelopmentProtocolManifest,
    final_exclusion: FinalTestExclusionManifest,
    collection: DevelopmentCollectionManifest,
    expectation: DatasetBindingExpectation,
) -> DatasetBindingReport:
    errors: list[str] = []
    warnings: list[str] = []

    protocol_id = protocol.protocol_id or protocol.compute_protocol_id()
    exclusion_id = (
        final_exclusion.manifest_id or final_exclusion.compute_manifest_id()
    )
    if expectation.protocol_id != protocol_id:
        errors.append("Expectation protocol ID does not match loaded protocol")
    if expectation.final_test_exclusion_id != exclusion_id:
        errors.append("Expectation final-test exclusion ID mismatch")
    if collection.protocol_id != protocol_id:
        errors.append("Collection manifest protocol ID mismatch")
    if collection.final_test_exclusion_id != exclusion_id:
        errors.append("Collection manifest exclusion ID mismatch")
    if collection.role != expectation.role:
        errors.append("Collection manifest role mismatch")

    assignment_map = protocol.assignment_map()
    expected_groups = protocol.groups_for(expectation.role)
    outcomes = collection.outcome_map()
    if set(outcomes) != set(expected_groups):
        errors.append(
            "Collection outcomes do not account for every preregistered group"
        )

    expected_split = ROLE_TO_SPLIT[expectation.role]
    actual_counts: dict[str, int] = {}
    stable_keys: set[tuple[str, int, str]] = set()
    technical_failures = 0

    expected_provenance = {
        "development_protocol_id": expectation.protocol_id,
        "final_test_exclusion_id": expectation.final_test_exclusion_id,
        "memory_snapshot_sha256": expectation.memory_snapshot_sha256,
        "confidence_artifact_id": expectation.confidence_artifact_id,
        "feature_schema_version": expectation.feature_schema_version,
        "knowledge_impl": expectation.knowledge_impl,
        "model_confidence_impl": expectation.model_confidence_impl,
        "environment_impl": expectation.environment_impl,
        "environment_scope": expectation.environment_scope,
        "environment_parameter_sha256": expectation.environment_parameter_sha256,
        "source_commit": expectation.source_commit,
    }

    for example in examples:
        if example.split != expected_split:
            errors.append(
                f"{example.stable_key}: split {example.split!r} != "
                f"{expected_split!r}"
            )
        assignment = assignment_map.get(example.group_id)
        if assignment is None:
            errors.append(f"Unexpected group {example.group_id!r}")
            continue
        if assignment.role != expectation.role:
            errors.append(
                f"Group {example.group_id!r} belongs to {assignment.role}, "
                f"not {expectation.role}"
            )
        if example.task != assignment.task or str(example.seed) != str(
            assignment.seed
        ):
            errors.append(
                f"Group {example.group_id!r} task/seed do not match protocol"
            )
        try:
            final_exclusion.validate_development_item(
                task=example.task,
                seed=str(example.seed),
                goal_status=str(assignment.goal_status),
            )
        except ValueError as exc:
            errors.append(str(exc))

        if example.stable_key in stable_keys:
            errors.append(f"Duplicate stable key {example.stable_key!r}")
        stable_keys.add(example.stable_key)
        actual_counts[example.group_id] = actual_counts.get(example.group_id, 0) + 1

        if example.memory_snapshot_sha256 != expectation.memory_snapshot_sha256:
            errors.append(f"{example.stable_key}: memory snapshot mismatch")
        if example.confidence_artifact_id != expectation.confidence_artifact_id:
            errors.append(f"{example.stable_key}: confidence artifact mismatch")

        provenance = _example_provenance(example)
        if not provenance:
            errors.append(f"{example.stable_key}: provenance is missing")
        else:
            for key, expected in expected_provenance.items():
                actual = str(provenance.get(key, ""))
                if actual != str(expected):
                    errors.append(
                        f"{example.stable_key}: provenance {key} mismatch "
                        f"({actual!r} != {expected!r})"
                    )
        if bool(example.metadata.get("technical_failure", False)):
            technical_failures += 1
            errors.append(
                f"{example.stable_key}: technical failure cannot be a "
                "labelled fusion example"
            )

    for group_id in expected_groups:
        outcome = outcomes.get(group_id)
        if outcome is None:
            continue
        assignment = assignment_map[group_id]
        if outcome.task != assignment.task or str(outcome.seed) != str(
            assignment.seed
        ):
            errors.append(f"Collection outcome {group_id!r} task/seed mismatch")
        count = actual_counts.get(group_id, 0)
        if outcome.status == "included" and count != outcome.usable_example_count:
            errors.append(
                f"Included group {group_id!r} expected "
                f"{outcome.usable_example_count} examples, found {count}"
            )
        if outcome.status != "included" and count:
            errors.append(
                f"Excluded group {group_id!r} unexpectedly has {count} examples"
            )

    missing_groups = sorted(group for group in expected_groups if group not in outcomes)
    if missing_groups:
        errors.append(f"Missing collection outcomes: {missing_groups}")

    return DatasetBindingReport(
        eligible=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        summary={
            "role": expectation.role,
            "dataset_sha256": dataset_sha256(examples),
            "example_count": len(examples),
            "positive_count": sum(item.label for item in examples),
            "negative_count": len(examples) - sum(item.label for item in examples),
            "preregistered_group_count": len(expected_groups),
            "included_group_count": len(actual_counts),
            "technical_failure_count": technical_failures,
            "collection_status_counts": {
                status: sum(
                    1 for item in outcomes.values() if item.status == status
                )
                for status in sorted(COLLECTION_STATUSES)
            },
        },
    )


def save_collection_manifest(
    path: str | Path,
    manifest: DevelopmentCollectionManifest,
) -> str:
    manifest = manifest.with_id()
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest.manifest_id


def load_collection_manifest(
    path: str | Path,
) -> DevelopmentCollectionManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["outcomes"] = tuple(
        CollectionOutcome(**item) for item in payload["outcomes"]
    )
    return DevelopmentCollectionManifest(**payload)
