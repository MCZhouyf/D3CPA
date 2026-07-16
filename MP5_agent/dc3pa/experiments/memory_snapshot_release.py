"""Freeze and audit the final read-only memory snapshot for Round 5.10."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1


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
class MemoryBuildContract:
    contract_name: str
    source_commit: str
    formal_acquisition_campaign_id: str
    formal_acquisition_audit_id: str
    formal_authorization_id: str
    execution_tooling_binding_id: str
    acquisition_schedule_id: str
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    bootstrap_data_binding_id: str
    blueprint_id: str
    acquisition_root_sha256: str
    successful_acquisition_episode_count: int
    min_dependency_support: int
    image_encoder_identity: str
    text_encoder_identity: str
    encoder_config_sha256: str
    build_from_successful_records_only: bool = True
    dependency_extraction_offline_only: bool = True
    scene_deduplication_enabled: bool = True
    require_structured_action_key_coverage: bool = True
    minimum_structured_action_key_coverage: float = 0.95
    reset_output_required: bool = True
    schema_version: int = SCHEMA_VERSION
    contract_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported memory-build contract schema")
        required = (
            self.contract_name,
            self.source_commit,
            self.formal_acquisition_campaign_id,
            self.formal_acquisition_audit_id,
            self.formal_authorization_id,
            self.execution_tooling_binding_id,
            self.acquisition_schedule_id,
            self.bootstrap_policy_id,
            self.bootstrap_amendment_id,
            self.bootstrap_data_binding_id,
            self.blueprint_id,
            self.acquisition_root_sha256,
            self.image_encoder_identity,
            self.text_encoder_identity,
            self.encoder_config_sha256,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Memory-build contract identity is incomplete")
        prohibited_encoder_names = ("rgbhistogram", "hashingtext", "development")
        identities = (
            self.image_encoder_identity.lower(),
            self.text_encoder_identity.lower(),
        )
        if any(name in identity for name in prohibited_encoder_names for identity in identities):
            raise ValueError("Development fallback encoders cannot enter the paper snapshot")
        if self.successful_acquisition_episode_count < 0:
            raise ValueError("Successful episode count cannot be negative")
        if self.min_dependency_support <= 0:
            raise ValueError("Dependency support threshold must be positive")
        if not all(
            (
                self.build_from_successful_records_only,
                self.dependency_extraction_offline_only,
                self.scene_deduplication_enabled,
                self.require_structured_action_key_coverage,
                self.reset_output_required,
            )
        ):
            raise ValueError("Memory-build safeguards are incomplete")
        if not 0.0 <= self.minimum_structured_action_key_coverage <= 1.0:
            raise ValueError("Action-key coverage threshold is invalid")
        expected = self.compute_contract_id()
        if self.contract_id and self.contract_id != expected:
            raise ValueError("Memory-build contract hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("contract_id", None)
        return payload

    def compute_contract_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "MemoryBuildContract":
        return replace(self, contract_id=self.compute_contract_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.contract_id else self.with_id()
        payload = item.payload_without_id()
        payload["contract_id"] = item.contract_id
        return payload


@dataclass(frozen=True)
class ReadOnlySnapshotSmoke:
    snapshot_manifest_sha256: str
    snapshot_root_sha256_before: str
    snapshot_root_sha256_after: str
    readonly_open_passed: bool
    mutation_attempt_blocked: bool
    database_query_only: bool
    successful_episode_count: int
    dependency_edge_count: int
    scene_exemplar_count: int
    eligible: bool
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    smoke_id: str = ""

    def __post_init__(self) -> None:
        if self.eligible and self.errors:
            raise ValueError("Eligible read-only smoke cannot contain errors")
        expected = self.compute_smoke_id()
        if self.smoke_id and self.smoke_id != expected:
            raise ValueError("Read-only smoke hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("smoke_id", None)
        payload["errors"] = list(self.errors)
        return payload

    def compute_smoke_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "ReadOnlySnapshotSmoke":
        return replace(self, smoke_id=self.compute_smoke_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.smoke_id else self.with_id()
        payload = item.payload_without_id()
        payload["smoke_id"] = item.smoke_id
        return payload


@dataclass(frozen=True)
class FrozenMemoryRelease:
    release_name: str
    source_commit: str
    memory_build_contract_id: str
    formal_acquisition_audit_id: str
    formal_authorization_id: str
    execution_tooling_binding_id: str
    acquisition_schedule_id: str
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    bootstrap_data_binding_id: str
    blueprint_id: str
    acquisition_root_sha256: str
    acquisition_manifest_sha256: str
    snapshot_manifest_sha256: str
    snapshot_root_sha256: str
    database_sha256: str
    build_stats_sha256: str
    read_only_smoke_id: str
    successful_episode_count: int
    dependency_edge_count: int
    scene_exemplar_count: int
    structured_action_key_coverage: float
    min_dependency_support: int
    image_encoder_identity: str
    text_encoder_identity: str
    eligible: bool
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        if not self.eligible:
            raise ValueError("Cannot freeze an ineligible memory release")
        required = (
            self.release_name,
            self.source_commit,
            self.memory_build_contract_id,
            self.formal_acquisition_audit_id,
            self.formal_authorization_id,
            self.execution_tooling_binding_id,
            self.acquisition_schedule_id,
            self.bootstrap_policy_id,
            self.bootstrap_amendment_id,
            self.bootstrap_data_binding_id,
            self.blueprint_id,
            self.acquisition_root_sha256,
            self.acquisition_manifest_sha256,
            self.snapshot_manifest_sha256,
            self.snapshot_root_sha256,
            self.database_sha256,
            self.build_stats_sha256,
            self.read_only_smoke_id,
            self.image_encoder_identity,
            self.text_encoder_identity,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Frozen memory release identity is incomplete")
        for value in (
            self.successful_episode_count,
            self.dependency_edge_count,
            self.scene_exemplar_count,
            self.min_dependency_support,
        ):
            if isinstance(value, bool) or value < 0:
                raise ValueError("Frozen memory counts cannot be negative")
        if self.min_dependency_support <= 0:
            raise ValueError("Dependency support threshold must be positive")
        if not 0.0 <= self.structured_action_key_coverage <= 1.0:
            raise ValueError("Action-key coverage is invalid")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("Frozen memory release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        return payload

    def compute_release_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FrozenMemoryRelease":
        return replace(self, release_id=self.compute_release_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.release_id else self.with_id()
        payload = item.payload_without_id()
        payload["release_id"] = item.release_id
        return payload


def audit_snapshot_and_build_release(
    *,
    release_name: str,
    contract: MemoryBuildContract,
    acquisition_audit: Mapping[str, Any],
    snapshot_manifest_path: str | Path,
    build_stats_path: str | Path,
    read_only_smoke: ReadOnlySnapshotSmoke,
) -> FrozenMemoryRelease:
    errors: list[str] = []
    snapshot_path = Path(snapshot_manifest_path)
    stats_path = Path(build_stats_path)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    stats = json.loads(stats_path.read_text(encoding="utf-8"))

    if not acquisition_audit.get("eligible", False):
        errors.append("formal acquisition audit is ineligible")
    if acquisition_audit.get("audit_id") != contract.formal_acquisition_audit_id:
        errors.append("acquisition audit/contract mismatch")
    if acquisition_audit.get("source_commit") != contract.source_commit:
        errors.append("acquisition audit source commit mismatch")
    if acquisition_audit.get("acquisition_root_sha256") != (
        contract.acquisition_root_sha256
    ):
        errors.append("acquisition root hash mismatch")
    success_count = int(
        acquisition_audit.get("successful_episode_count", -1)
    )
    if success_count != contract.successful_acquisition_episode_count:
        errors.append("successful episode count/contract mismatch")
    if not read_only_smoke.eligible:
        errors.append("read-only snapshot smoke is ineligible")
    if read_only_smoke.snapshot_manifest_sha256 != sha256_file(snapshot_path):
        errors.append("read-only smoke/snapshot manifest mismatch")

    metadata = snapshot.get("metadata", {})
    if not isinstance(metadata, Mapping):
        errors.append("snapshot metadata is missing")
        metadata = {}
    expected_metadata = {
        "formal_acquisition_campaign_id": (
            contract.formal_acquisition_campaign_id
        ),
        "formal_acquisition_audit_id": contract.formal_acquisition_audit_id,
        "formal_authorization_id": contract.formal_authorization_id,
        "execution_tooling_binding_id": contract.execution_tooling_binding_id,
        "acquisition_schedule_id": contract.acquisition_schedule_id,
        "bootstrap_policy_id": contract.bootstrap_policy_id,
        "bootstrap_amendment_id": contract.bootstrap_amendment_id,
        "bootstrap_data_binding_id": contract.bootstrap_data_binding_id,
        "blueprint_id": contract.blueprint_id,
        "memory_build_contract_id": contract.contract_id,
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            errors.append(f"snapshot metadata {key} mismatch")

    table_counts = snapshot.get("table_counts", {})
    db_episode_count = int(table_counts.get("episodes", -1))
    if db_episode_count != success_count:
        errors.append(
            f"snapshot episode count {db_episode_count} != success count "
            f"{success_count}"
        )
    if int(stats.get("acquisition_episodes", -1)) != success_count:
        errors.append("build_stats acquisition_episodes mismatch")
    if int(stats.get("min_dependency_support", -1)) != (
        contract.min_dependency_support
    ):
        errors.append("dependency support threshold mismatch")
    coverage = float(stats.get("structured_action_key_coverage", 0.0))
    if contract.require_structured_action_key_coverage and (
        coverage < contract.minimum_structured_action_key_coverage
    ):
        errors.append(
            "structured action-key coverage is below the contract threshold"
        )
    dependency_count = int(
        stats.get(
            "retained_dependency_edges",
            table_counts.get("dependency_edges", 0),
        )
    )
    exemplar_count = int(
        stats.get(
            "stored_scene_exemplars",
            table_counts.get("scene_exemplars", 0),
        )
    )
    if read_only_smoke.successful_episode_count != success_count:
        errors.append("read-only smoke episode count mismatch")
    if read_only_smoke.dependency_edge_count != dependency_count:
        errors.append("read-only smoke dependency-edge count mismatch")
    if read_only_smoke.scene_exemplar_count != exemplar_count:
        errors.append("read-only smoke scene-exemplar count mismatch")

    if errors:
        raise ValueError("; ".join(errors))

    return FrozenMemoryRelease(
        release_name=release_name,
        source_commit=contract.source_commit,
        memory_build_contract_id=contract.contract_id,
        formal_acquisition_audit_id=contract.formal_acquisition_audit_id,
        formal_authorization_id=contract.formal_authorization_id,
        execution_tooling_binding_id=contract.execution_tooling_binding_id,
        acquisition_schedule_id=contract.acquisition_schedule_id,
        bootstrap_policy_id=contract.bootstrap_policy_id,
        bootstrap_amendment_id=contract.bootstrap_amendment_id,
        bootstrap_data_binding_id=contract.bootstrap_data_binding_id,
        blueprint_id=contract.blueprint_id,
        acquisition_root_sha256=contract.acquisition_root_sha256,
        acquisition_manifest_sha256=str(
            snapshot.get("acquisition_manifest_sha256", "")
        ),
        snapshot_manifest_sha256=sha256_file(snapshot_path),
        snapshot_root_sha256=str(snapshot.get("snapshot_root_sha256", "")),
        database_sha256=str(snapshot.get("database_sha256", "")),
        build_stats_sha256=sha256_file(stats_path),
        read_only_smoke_id=read_only_smoke.smoke_id,
        successful_episode_count=success_count,
        dependency_edge_count=dependency_count,
        scene_exemplar_count=exemplar_count,
        structured_action_key_coverage=coverage,
        min_dependency_support=contract.min_dependency_support,
        image_encoder_identity=contract.image_encoder_identity,
        text_encoder_identity=contract.text_encoder_identity,
        eligible=True,
    ).with_id()
