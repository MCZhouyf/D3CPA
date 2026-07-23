"""Round 5.13E0 provenance audits over immutable Paper Memory V5 assets."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from dc3pa.memory.snapshot import (
    MemorySnapshotManifest,
    assert_snapshot_unchanged,
    sha256_file,
)


SCHEMA_VERSION = 1
MINECLIP_CASES = {"M1", "M2", "M3"}
SCENE_CASES = {"S1", "S2", "S3"}
V2_STATUSES = {
    "ELIGIBLE_FOR_PREPARATION",
    "BLOCKED_MINECLIP_POLICY_MISMATCH",
    "BLOCKED_SCENE_RELEASE_UNVERIFIABLE",
    "BLOCKED_DEPENDENT_CONTRACT_MISMATCH",
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def canonical_policy_id(payload: Mapping[str, Any]) -> str:
    value = dict(payload)
    value.pop("policy_id", None)
    return canonical_sha256(value)


def _file_sha(path: str | Path) -> str:
    return sha256_file(Path(path))


def _file_md5(path: str | Path) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _Hashed:
    _id_field: str

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop(self._id_field, None)
        return payload

    def compute_id(self) -> str:
        return canonical_sha256(self.payload_without_id())

    def with_id(self):
        return replace(self, **{self._id_field: self.compute_id()})

    def to_dict(self) -> dict[str, Any]:
        item = self if getattr(self, self._id_field) else self.with_id()
        return {**item.payload_without_id(), self._id_field: getattr(item, self._id_field)}


def _mineclip_semantic_payload(
    policy: Mapping[str, Any], checkpoint: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "repository": policy.get("repository"),
        "repository_commit": policy.get("repository_commit"),
        "architecture": policy.get("architecture"),
        "variant": policy.get("variant"),
        "pool_type": policy.get("pool_type"),
        "mlp_adapter_spec": policy.get("mlp_adapter_spec"),
        "resolution": policy.get("resolution"),
        "frame_count": policy.get("frame_count"),
        "frame_strategy": policy.get("frame_strategy"),
        "output_dim": policy.get("output_dim"),
        "l2_normalize_embeddings": policy.get("l2_normalize_embeddings"),
        "checkpoint_md5": checkpoint.get("checkpoint_md5"),
        "checkpoint_sha256": checkpoint.get("checkpoint_sha256"),
        "checkpoint_manifest_id": checkpoint.get("manifest_id"),
        "checkpoint_loaded_strictly": checkpoint.get("checkpoint_loaded_strictly"),
        "inference_probe_passed": checkpoint.get("inference_probe_passed"),
        "deterministic_repeat_probe_passed": checkpoint.get(
            "deterministic_repeat_probe_passed"
        ),
        "image_embedding_dim": checkpoint.get("image_embedding_dim"),
        "text_embedding_dim": checkpoint.get("text_embedding_dim"),
    }


@dataclass(frozen=True)
class MineCLIPIdentityForensicAudit(_Hashed):
    source_commit: str
    referenced_policy_id: str
    actual_policy_id: str
    referenced_payload_resolved: bool
    actual_payload_verified: bool
    canonical_payload_equal: bool | None
    case: str
    classification: str
    referenced_source_label: str | None
    actual_source_label: str
    actual_policy_file_sha256: str
    actual_policy_canonical_sha256: str
    checkpoint_file_sha256: str
    checkpoint_file_md5: str
    checkpoint_manifest_file_sha256: str
    checkpoint_manifest_id: str
    repository_commit: str
    variant: str
    frame_strategy: str
    output_dimension: int
    normalized_embeddings: bool
    inference_probe_passed: bool
    deterministic_probe_passed: bool
    automatic_rebind_permitted: bool
    searched_exact_id_match_count: int
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.case not in MINECLIP_CASES:
            raise ValueError("Unknown MineCLIP forensic case")
        if self.actual_policy_canonical_sha256 != self.actual_policy_id:
            raise ValueError("Actual MineCLIP policy ID is not canonical")
        if self.case == "M1" and not (
            self.referenced_payload_resolved
            and self.actual_payload_verified
            and self.canonical_payload_equal
            and self.automatic_rebind_permitted
        ):
            raise ValueError("M1 requires two verified equivalent payloads")
        if self.case == "M2" and self.canonical_payload_equal is not False:
            raise ValueError("M2 requires distinct semantic payloads")
        if self.case == "M3" and self.referenced_payload_resolved:
            raise ValueError("M3 requires an unresolved referenced identity")
        if self.case != "M1" and self.automatic_rebind_permitted:
            raise ValueError("Only M1 may permit automatic rebinding")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("MineCLIP forensic audit hash mismatch")


def audit_mineclip_identity(
    *,
    source_commit: str,
    referenced_policy_id: str,
    actual_policy_path: str | Path,
    checkpoint_manifest_path: str | Path,
    checkpoint_path: str | Path,
    referenced_policy_path: str | Path | None = None,
    searched_exact_id_match_count: int = 0,
    referenced_source_label: str | None = None,
    actual_source_label: str = "paper-memory-v5/mineclip-policy",
) -> MineCLIPIdentityForensicAudit:
    actual_path = Path(actual_policy_path)
    checkpoint_manifest_path = Path(checkpoint_manifest_path)
    checkpoint_path = Path(checkpoint_path)
    actual = json.loads(actual_path.read_text(encoding="utf-8"))
    checkpoint = json.loads(checkpoint_manifest_path.read_text(encoding="utf-8"))
    actual_id = str(actual.get("policy_id", ""))
    canonical_id = canonical_policy_id(actual)
    checkpoint_sha = _file_sha(checkpoint_path)
    checkpoint_md5 = _file_md5(checkpoint_path)
    actual_verified = all(
        (
            actual_id == canonical_id,
            checkpoint.get("policy_id") == actual_id,
            checkpoint.get("checkpoint_sha256") == checkpoint_sha,
            checkpoint.get("checkpoint_md5") == checkpoint_md5,
            checkpoint.get("checkpoint_loaded_strictly") is True,
            checkpoint.get("inference_probe_passed") is True,
            checkpoint.get("deterministic_repeat_probe_passed") is True,
        )
    )
    referenced: Mapping[str, Any] | None = None
    if referenced_policy_path is not None:
        referenced = json.loads(Path(referenced_policy_path).read_text(encoding="utf-8"))
        if str(referenced.get("policy_id", "")) != referenced_policy_id:
            raise ValueError("Referenced policy payload does not bind the requested ID")

    if referenced is None:
        case = "M3"
        classification = "unverifiable_identity"
        equal = None
    else:
        equal = _mineclip_semantic_payload(referenced, checkpoint) == _mineclip_semantic_payload(
            actual, checkpoint
        )
        if equal:
            case = "M1"
            classification = "reference_binding_error"
        else:
            case = "M2"
            classification = "scientific_policy_mismatch"

    return MineCLIPIdentityForensicAudit(
        source_commit=source_commit,
        referenced_policy_id=referenced_policy_id,
        actual_policy_id=actual_id,
        referenced_payload_resolved=referenced is not None,
        actual_payload_verified=actual_verified,
        canonical_payload_equal=equal,
        case=case,
        classification=classification,
        referenced_source_label=referenced_source_label,
        actual_source_label=actual_source_label,
        actual_policy_file_sha256=_file_sha(actual_path),
        actual_policy_canonical_sha256=canonical_id,
        checkpoint_file_sha256=checkpoint_sha,
        checkpoint_file_md5=checkpoint_md5,
        checkpoint_manifest_file_sha256=_file_sha(checkpoint_manifest_path),
        checkpoint_manifest_id=str(checkpoint.get("manifest_id", "")),
        repository_commit=str(actual.get("repository_commit", "")),
        variant=str(actual.get("variant", "")),
        frame_strategy=str(actual.get("frame_strategy", "")),
        output_dimension=int(actual.get("output_dim", 0)),
        normalized_embeddings=bool(actual.get("l2_normalize_embeddings")),
        inference_probe_passed=bool(checkpoint.get("inference_probe_passed")),
        deterministic_probe_passed=bool(
            checkpoint.get("deterministic_repeat_probe_passed")
        ),
        automatic_rebind_permitted=case == "M1" and actual_verified,
        searched_exact_id_match_count=int(searched_exact_id_match_count),
    ).with_id()


SCENE_REQUIRED_FIELDS = {
    "scene_id",
    "dedup_key",
    "source_episode_id",
    "source_episode_record_sha256",
    "source_task",
    "owner_task",
    "subgoal",
    "action",
    "action_signature",
    "pre_action_image_id",
    "pre_action_image_sha256",
    "source_pre_action_array_sha256",
    "embedding_row_index",
    "image_embedding_sha256",
    "text_embedding_sha256",
    "image_embedding_dimension",
    "text_embedding_dimension",
    "image_embedding_finite",
    "text_embedding_finite",
    "image_embedding_normalized",
    "text_embedding_normalized",
    "database_row_sha256",
    "database_table",
    "candidate_id",
}


@dataclass(frozen=True)
class SceneExemplarEvidenceReleaseV5(_Hashed):
    source_commit: str
    paper_memory_v5_release_id: str
    mineclip_policy_id: str
    mineclip_checkpoint_manifest_id: str
    snapshot_manifest_sha256: str
    snapshot_root_sha256: str
    database_sha256: str
    asset_manifest_sha256: str
    acquisition_manifest_sha256: str
    acquisition_root_sha256: str
    successful_episode_count: int
    scene_exemplar_count: int
    scene_source_episode_count: int
    dependency_edge_count: int
    scene_evidence: tuple[Mapping[str, Any], ...]
    release_kind: str = "evidence_manifest_over_existing_snapshot"
    memory_rebuilt: bool = False
    snapshot_modified: bool = False
    supersedes_missing_reference_only: bool = True
    new_encoding_count: int = 0
    new_deduplication_count: int = 0
    owner_reassignment_count: int = 0
    row_mutation_count: int = 0
    write_count: int = 0
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        if self.release_kind != "evidence_manifest_over_existing_snapshot":
            raise ValueError("Scene release must be an evidence-only manifest")
        if any(
            (
                self.memory_rebuilt,
                self.snapshot_modified,
                self.new_encoding_count,
                self.new_deduplication_count,
                self.owner_reassignment_count,
                self.row_mutation_count,
                self.write_count,
            )
        ):
            raise ValueError("Scene evidence release mutated frozen memory")
        if not self.supersedes_missing_reference_only:
            raise ValueError("Scene evidence release scope is too broad")
        if (self.successful_episode_count, self.scene_exemplar_count, self.dependency_edge_count) != (
            40,
            144,
            27,
        ):
            raise ValueError("Aggregate V5 identity differs from the frozen release")
        if len(self.scene_evidence) != 144:
            raise ValueError("Aggregate counts alone cannot create a scene release")
        ids = []
        for item in self.scene_evidence:
            if not SCENE_REQUIRED_FIELDS <= set(item):
                raise ValueError("Scene evidence is missing mandatory lineage")
            ids.append(str(item["scene_id"]))
            if item["image_embedding_dimension"] != 512 or item["text_embedding_dimension"] != 512:
                raise ValueError("Scene embedding dimension mismatch")
            if not all(
                item[key]
                for key in (
                    "image_embedding_finite",
                    "text_embedding_finite",
                    "image_embedding_normalized",
                    "text_embedding_normalized",
                )
            ):
                raise ValueError("Scene embedding proof is incomplete")
            if item["database_table"] != "scene_exemplars":
                raise ValueError("Scene row identity references an unexpected table")
        if len(set(ids)) != 144:
            raise ValueError("Scene IDs are not unique")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("Scene evidence release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["scene_evidence"] = [dict(item) for item in self.scene_evidence]
        return payload


@dataclass(frozen=True)
class SceneExemplarReleaseForensicAudit(_Hashed):
    source_commit: str
    missing_historical_release_id: str
    exact_historical_release_match_count: int
    case: str
    scene_release_reconstruction_eligible: bool
    evidence_release_id: str | None
    paper_memory_v5_release_id: str
    mineclip_policy_id: str
    scene_count: int
    unique_scene_count: int
    complete_lineage_count: int
    successful_episode_count: int
    scene_source_episode_count: int
    dependency_edge_count: int
    image_asset_count: int
    normalized_image_embedding_count: int
    normalized_text_embedding_count: int
    snapshot_root_sha256_before: str
    snapshot_root_sha256_after: str
    database_sha256_before: str
    database_sha256_after: str
    asset_manifest_sha256_before: str
    asset_manifest_sha256_after: str
    write_count: int
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.case not in SCENE_CASES:
            raise ValueError("Unknown Scene Exemplar forensic case")
        if self.scene_release_reconstruction_eligible != (self.case in {"S1", "S2"}):
            raise ValueError("Scene case and eligibility disagree")
        if self.case == "S2" and not self.evidence_release_id:
            raise ValueError("S2 requires a new evidence release")
        if self.scene_release_reconstruction_eligible and self.errors:
            raise ValueError("Eligible scene forensic audit contains errors")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Scene forensic audit hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["errors"] = list(self.errors)
        return payload


def _row_identity(row: sqlite3.Row) -> str:
    value = {
        key: (
            hashlib.sha256(row[key]).hexdigest()
            if isinstance(row[key], bytes)
            else row[key]
        )
        for key in row.keys()
    }
    if value.get("image_path"):
        value["image_path"] = f"snapshot:images/{Path(str(value['image_path'])).name}"
    return canonical_sha256(value)


def build_scene_exemplar_evidence_release(
    *,
    source_commit: str,
    missing_historical_release_id: str,
    exact_historical_release_match_count: int,
    snapshot_manifest_path: str | Path,
    acquisition_manifest_path: str | Path,
    lineage_input_path: str | Path,
    lineage_audit_path: str | Path,
    paper_memory_release_path: str | Path,
    mineclip_checkpoint_manifest_path: str | Path,
) -> tuple[SceneExemplarReleaseForensicAudit, SceneExemplarEvidenceReleaseV5 | None]:
    snapshot_path = Path(snapshot_manifest_path).resolve()
    acquisition_path = Path(acquisition_manifest_path).resolve()
    lineage_path = Path(lineage_input_path).resolve()
    lineage_audit_path = Path(lineage_audit_path).resolve()
    paper_path = Path(paper_memory_release_path).resolve()
    checkpoint_path = Path(mineclip_checkpoint_manifest_path).resolve()
    manifest = MemorySnapshotManifest.from_json(snapshot_path)
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    lineage_payload = json.loads(lineage_path.read_text(encoding="utf-8"))
    lineage_audit = json.loads(lineage_audit_path.read_text(encoding="utf-8"))
    paper = json.loads(paper_path.read_text(encoding="utf-8"))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    assert_snapshot_unchanged(manifest)
    snapshot_before = manifest.snapshot_root_sha256
    database_before = _file_sha(manifest.database_path)
    asset_manifest_before = canonical_sha256(manifest.asset_files)
    lineage = {
        str(item["retained_scene_id"]): item
        for item in lineage_payload.get("candidate_lineage", ())
    }
    if len(lineage) != len(lineage_payload.get("candidate_lineage", ())):
        errors.append("duplicate retained Scene ID in lineage input")

    uri = f"file:{Path(manifest.database_path).resolve()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    records: list[dict[str, Any]] = []
    try:
        episodes = {
            str(row["episode_id"])
            for row in connection.execute(
                "SELECT episode_id FROM episodes WHERE success=1 ORDER BY episode_id"
            )
        }
        edge_count = int(connection.execute("SELECT COUNT(*) FROM dependency_edges").fetchone()[0])
        rows = connection.execute("SELECT * FROM scene_exemplars ORDER BY exemplar_id").fetchall()
        for index, row in enumerate(rows):
            scene_id = str(row["exemplar_id"])
            item = lineage.get(scene_id)
            if item is None:
                errors.append(f"{scene_id}: missing deterministic lineage")
                continue
            metadata = json.loads(row["metadata_json"])
            image = np.frombuffer(row["image_vector"], dtype="<f4")
            text = np.frombuffer(row["text_vector"], dtype="<f4")
            image_path = Path(str(row["image_path"]))
            image_label = f"images/{image_path.name}"
            image_sha = _file_sha(image_path) if image_path.is_file() else ""
            source_image_label = (
                f"images/{row['episode_id']}/{row['step_id']}_a000.npy"
            )
            episode_label = f"episodes/{row['episode_id']}.json"
            evidence = {
                "scene_id": scene_id,
                "dedup_key": str(item.get("deterministic_dedup_key", "")),
                "source_episode_id": str(row["episode_id"]),
                "source_episode_record_sha256": str(
                    acquisition.get("files", {}).get(episode_label, "")
                ),
                "source_task": str(item.get("source_task", "")),
                "owner_task": str(item.get("retained_scene_owner_task", "")),
                "subgoal": str(metadata.get("local_subgoal", "")),
                "action": metadata.get("action"),
                "action_signature": str(metadata.get("action_key", "")),
                "pre_action_image_id": str(row["step_id"]),
                "pre_action_image_sha256": image_sha,
                "source_pre_action_array_sha256": str(
                    acquisition.get("files", {}).get(source_image_label, "")
                ),
                "embedding_row_index": index,
                "image_embedding_sha256": hashlib.sha256(row["image_vector"]).hexdigest(),
                "text_embedding_sha256": hashlib.sha256(row["text_vector"]).hexdigest(),
                "image_embedding_dimension": int(row["image_dim"]),
                "text_embedding_dimension": int(row["text_dim"]),
                "image_embedding_finite": bool(np.isfinite(image).all()),
                "text_embedding_finite": bool(np.isfinite(text).all()),
                "image_embedding_normalized": bool(
                    np.isclose(np.linalg.norm(image), 1.0, atol=1e-5)
                ),
                "text_embedding_normalized": bool(
                    np.isclose(np.linalg.norm(text), 1.0, atol=1e-5)
                ),
                "database_row_sha256": _row_identity(row),
                "database_table": "scene_exemplars",
                "candidate_id": str(item.get("candidate_id", "")),
            }
            if row["episode_id"] != item.get("source_episode_id"):
                errors.append(f"{scene_id}: source episode mismatch")
            if row["task_name"] != item.get("retained_scene_owner_task"):
                errors.append(f"{scene_id}: owner task mismatch")
            if metadata.get("source_episode_id") != row["episode_id"]:
                errors.append(f"{scene_id}: metadata episode mismatch")
            if manifest.asset_files.get(image_label) != image_sha:
                errors.append(f"{scene_id}: snapshot image hash mismatch")
            if not SCENE_REQUIRED_FIELDS <= set(evidence) or any(
                evidence[key] in (None, "") for key in SCENE_REQUIRED_FIELDS - {
                    "embedding_row_index"
                }
            ):
                errors.append(f"{scene_id}: incomplete lineage evidence")
            records.append(evidence)
    finally:
        connection.close()

    if len(episodes) != 40:
        errors.append("successful episode count is not 40")
    if len(rows) != 144 or len({row["exemplar_id"] for row in rows}) != 144:
        errors.append("Scene Exemplar identity is not exactly 144 unique rows")
    if edge_count != 27:
        errors.append("dependency edge count is not 27")
    if set(episodes) != {
        label.removeprefix("episodes/").removesuffix(".json")
        for label in acquisition.get("files", {})
        if label.startswith("episodes/") and label.endswith(".json")
    }:
        errors.append("successful episode set does not match acquisition manifest")
    if lineage_audit.get("eligible") is not True or lineage_audit.get("snapshot_modified"):
        errors.append("prior scene-lineage audit is not immutable and eligible")

    assert_snapshot_unchanged(manifest)
    snapshot_after = manifest.snapshot_root_sha256
    database_after = _file_sha(manifest.database_path)
    asset_manifest_after = canonical_sha256(manifest.asset_files)
    if (snapshot_before, database_before, asset_manifest_before) != (
        snapshot_after,
        database_after,
        asset_manifest_after,
    ):
        errors.append("snapshot, database, or asset identity changed during audit")

    release: SceneExemplarEvidenceReleaseV5 | None = None
    if exact_historical_release_match_count > 0:
        case = "S1"
    elif errors:
        case = "S3"
    else:
        case = "S2"
        release = SceneExemplarEvidenceReleaseV5(
            source_commit=source_commit,
            paper_memory_v5_release_id=str(paper["release_id"]),
            mineclip_policy_id=str(paper["mineclip_policy_id"]),
            mineclip_checkpoint_manifest_id=str(checkpoint["manifest_id"]),
            snapshot_manifest_sha256=_file_sha(snapshot_path),
            snapshot_root_sha256=snapshot_before,
            database_sha256=database_before,
            asset_manifest_sha256=asset_manifest_before,
            acquisition_manifest_sha256=_file_sha(acquisition_path),
            acquisition_root_sha256=str(paper["acquisition_root_sha256"]),
            successful_episode_count=len(episodes),
            scene_exemplar_count=len(rows),
            scene_source_episode_count=len({row["episode_id"] for row in rows}),
            dependency_edge_count=edge_count,
            scene_evidence=tuple(records),
        ).with_id()

    audit = SceneExemplarReleaseForensicAudit(
        source_commit=source_commit,
        missing_historical_release_id=missing_historical_release_id,
        exact_historical_release_match_count=exact_historical_release_match_count,
        case=case,
        scene_release_reconstruction_eligible=case in {"S1", "S2"},
        evidence_release_id=release.release_id if release else None,
        paper_memory_v5_release_id=str(paper["release_id"]),
        mineclip_policy_id=str(paper["mineclip_policy_id"]),
        scene_count=len(rows),
        unique_scene_count=len({row["exemplar_id"] for row in rows}),
        complete_lineage_count=len(records),
        successful_episode_count=len(episodes),
        scene_source_episode_count=len({row["episode_id"] for row in rows}),
        dependency_edge_count=edge_count,
        image_asset_count=sum(bool(item["pre_action_image_sha256"]) for item in records),
        normalized_image_embedding_count=sum(
            bool(item["image_embedding_normalized"]) for item in records
        ),
        normalized_text_embedding_count=sum(
            bool(item["text_embedding_normalized"]) for item in records
        ),
        snapshot_root_sha256_before=snapshot_before,
        snapshot_root_sha256_after=snapshot_after,
        database_sha256_before=database_before,
        database_sha256_after=database_after,
        asset_manifest_sha256_before=asset_manifest_before,
        asset_manifest_sha256_after=asset_manifest_after,
        write_count=0,
        errors=tuple(errors),
    ).with_id()
    return audit, release


@dataclass(frozen=True)
class Round513EPreSmokeIntegrityAuditV2(_Hashed):
    source_commit: str
    blocked_v1_audit_id: str
    blocked_v1_audit_sha256_before: str
    blocked_v1_audit_sha256_after: str
    mineclip_forensic_audit_id: str
    mineclip_case: str
    scene_forensic_audit_id: str
    scene_case: str
    scene_evidence_release_id: str | None
    contract_supersession_release_id: str | None
    binding_equivalence_audit_id: str | None
    snapshot_guard_passed: bool
    status: str
    eligible_for_preparation: bool
    smoke_pool_generated: bool = False
    smoke_assignments_generated: bool = False
    gamma_input_generated: bool = False
    minedojo_started: bool = False
    formal_development_started: bool = False
    holdout_final_accessed: bool = False
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.status not in V2_STATUSES:
            raise ValueError("Unknown V2 PreSmoke status")
        required_for_eligibility = all(
            (
                self.mineclip_case == "M1",
                self.scene_case in {"S1", "S2"},
                self.scene_evidence_release_id,
                self.contract_supersession_release_id,
                self.binding_equivalence_audit_id,
                self.snapshot_guard_passed,
            )
        )
        if self.eligible_for_preparation != bool(required_for_eligibility):
            raise ValueError("V2 eligibility does not satisfy all provenance gates")
        if self.eligible_for_preparation != (self.status == "ELIGIBLE_FOR_PREPARATION"):
            raise ValueError("V2 status and eligibility disagree")
        if any(
            (
                self.smoke_pool_generated,
                self.smoke_assignments_generated,
                self.gamma_input_generated,
                self.minedojo_started,
                self.formal_development_started,
                self.holdout_final_accessed,
            )
        ):
            raise ValueError("Blocked V2 audit crossed an experiment boundary")
        if self.blocked_v1_audit_sha256_before != self.blocked_v1_audit_sha256_after:
            raise ValueError("Blocked V1 audit was mutated")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("V2 PreSmoke audit hash mismatch")


def build_blocked_v2_audit(
    *,
    source_commit: str,
    blocked_v1_audit_id: str,
    blocked_v1_audit_sha256_before: str,
    blocked_v1_audit_sha256_after: str,
    mineclip_audit: MineCLIPIdentityForensicAudit,
    scene_audit: SceneExemplarReleaseForensicAudit,
    scene_release: SceneExemplarEvidenceReleaseV5 | None,
    snapshot_guard_passed: bool,
) -> Round513EPreSmokeIntegrityAuditV2:
    if scene_release is not None and scene_audit.evidence_release_id != scene_release.release_id:
        raise ValueError("Scene forensic audit and evidence release do not match")
    if mineclip_audit.case != "M1":
        status = "BLOCKED_MINECLIP_POLICY_MISMATCH"
    elif scene_audit.case == "S3":
        status = "BLOCKED_SCENE_RELEASE_UNVERIFIABLE"
    else:
        status = "BLOCKED_DEPENDENT_CONTRACT_MISMATCH"
    return Round513EPreSmokeIntegrityAuditV2(
        source_commit=source_commit,
        blocked_v1_audit_id=blocked_v1_audit_id,
        blocked_v1_audit_sha256_before=blocked_v1_audit_sha256_before,
        blocked_v1_audit_sha256_after=blocked_v1_audit_sha256_after,
        mineclip_forensic_audit_id=mineclip_audit.audit_id,
        mineclip_case=mineclip_audit.case,
        scene_forensic_audit_id=scene_audit.audit_id,
        scene_case=scene_audit.case,
        scene_evidence_release_id=scene_release.release_id if scene_release else None,
        contract_supersession_release_id=None,
        binding_equivalence_audit_id=None,
        snapshot_guard_passed=snapshot_guard_passed,
        status=status,
        eligible_for_preparation=False,
    ).with_id()
