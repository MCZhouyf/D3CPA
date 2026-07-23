"""Prospective authoritative re-baseline over immutable Paper Memory V5.

This module does not repair historical identities.  It proves the actual
snapshot closure, records invalid historical bindings, and builds DRAFT
candidate objects that remain unusable until an exact author approval exists.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from dc3pa.experiments.mineclip_memory_v5 import MineCLIPV5RebuildContract
from dc3pa.experiments.round513e_provenance import (
    canonical_policy_id,
    canonical_sha256,
)
from dc3pa.memory.snapshot import (
    MemorySnapshotManifest,
    assert_snapshot_unchanged,
    sha256_file,
)


SCHEMA_VERSION = 1
FULL_ID = re.compile(r"[0-9a-f]{64}")
HISTORICAL_REFERENCE = re.compile(r"[0-9a-f]{8,64}")
ACTUAL_PROVENANCE_STATUSES = {
    "ACTUAL_PROVENANCE_CLOSED",
    "ACTUAL_PROVENANCE_INCOMPLETE",
    "ACTUAL_ARTIFACT_CONFLICT",
}
REBASELINE_DECLARATIONS = (
    "The invalid historical MineCLIP reference is not claimed equivalent.",
    "The invalid historical Scene release is not reused.",
    "The new release binds only already existing immutable V5 bytes.",
    "No Memory database, image, embedding, rule, owner or row is changed.",
    "No engineering smoke or formal scientific result exists under the invalid prospective contracts.",
    "The new release is prospective only.",
    "V4.1.2 dependent contracts will be regenerated with new IDs.",
    "Retrieval algorithm, top-k, compatibility, tie-break and unknown semantics remain unchanged.",
    "Historical contracts/audits remain preserved and ineligible.",
    "Holdout/final/Round 6 remain closed.",
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _file_md5(path: str | Path) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nul_delimited_file_map_sha(files: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for relative, file_hash in sorted(files.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _load_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _full_id(value: Any) -> bool:
    return isinstance(value, str) and FULL_ID.fullmatch(value) is not None


def exact_full_id_equal(left: str, right: str) -> bool:
    """Return equality only for two complete SHA-256 identities."""

    return _full_id(left) and _full_id(right) and left == right


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


def _row_identity(row: sqlite3.Row) -> str:
    value = {
        key: hashlib.sha256(row[key]).hexdigest()
        if isinstance(row[key], bytes)
        else row[key]
        for key in row.keys()
    }
    if value.get("image_path"):
        value["image_path"] = f"snapshot:images/{Path(str(value['image_path'])).name}"
    return canonical_sha256(value)


def _forbidden_source_labels(value: Any, *, key: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            errors.extend(_forbidden_source_labels(child, key=str(child_key)))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            errors.extend(_forbidden_source_labels(child, key=key))
    elif isinstance(value, str) and key.lower() in {
        "split",
        "dataset_split",
        "experiment_split",
        "namespace",
        "source_namespace",
    }:
        normalized = value.strip().lower()
        if "holdout" in normalized or normalized in {"final", "round6", "round 6"}:
            errors.append(f"prohibited source label {key}={value}")
    return errors


@dataclass(frozen=True)
class ActualPaperMemoryV5ProvenanceClosureAudit(_Hashed):
    source_commit: str
    status: str
    embedding_evidence_path: str
    actual_snapshot_manifest_id: str
    actual_snapshot_manifest_file_sha256: str
    actual_acquisition_manifest_id: str
    actual_acquisition_manifest_file_sha256: str
    actual_acquisition_root_sha256: str
    accepted_source_manifest_id: str
    accepted_source_manifest_file_sha256: str
    accepted_source_root_sha256: str
    accepted_source_file_map_sha256: str
    accepted_source_file_count: int
    snapshot_root_sha256: str
    database_sha256: str
    asset_manifest_sha256: str
    builder_source_commit: str
    builder_contract_id: str
    builder_contract_file_sha256: str
    build_stats_file_sha256: str
    mineclip_policy_id: str
    mineclip_policy_file_sha256: str
    mineclip_checkpoint_manifest_id: str
    mineclip_checkpoint_manifest_file_sha256: str
    mineclip_checkpoint_sha256: str
    mineclip_checkpoint_md5: str
    mineclip_probe_id: str
    mineclip_probe_file_sha256: str
    readonly_snapshot_smoke_id: str
    readonly_snapshot_smoke_file_sha256: str
    accepted_episode_count: int
    accepted_episode_identity_root: str
    source_receipt_hash_root: str
    scene_source_episode_count: int
    scene_source_episode_identity_root: str
    no_scene_episode_count: int
    no_scene_reason: str
    dependency_edge_count: int
    scene_exemplar_count: int
    unique_scene_count: int
    scene_lineage_root: str
    embedding_row_hash_root: str
    duplicate_scene_id_count: int
    orphan_scene_count: int
    missing_image_count: int
    missing_embedding_count: int
    source_episode_outside_acquisition_count: int
    task_seed_run_identity_count: int
    holdout_final_source_count: int
    snapshot_guard_passed: bool
    sqlite_integrity_passed: bool
    database_sha256_after: str
    snapshot_root_sha256_after: str
    asset_manifest_sha256_after: str
    write_count: int
    memory_rebuilt: bool
    reencoding_count: int
    row_mutation_count: int
    scene_lineage: tuple[Mapping[str, Any], ...]
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.status not in ACTUAL_PROVENANCE_STATUSES:
            raise ValueError("Unknown actual-provenance status")
        if self.embedding_evidence_path not in {"P1", "P2", "P3"}:
            raise ValueError("Unknown MineCLIP-to-embedding evidence path")
        if self.status == "ACTUAL_PROVENANCE_CLOSED":
            if self.errors:
                raise ValueError("Closed provenance contains errors")
            if self.embedding_evidence_path not in {"P1", "P2"}:
                raise ValueError("Closed provenance lacks embedding evidence")
            if (
                self.accepted_episode_count,
                self.scene_source_episode_count,
                self.dependency_edge_count,
                self.scene_exemplar_count,
                self.unique_scene_count,
            ) != (40, 36, 27, 144, 144):
                raise ValueError("Closed provenance has unexpected aggregate identity")
            if any(
                (
                    self.duplicate_scene_id_count,
                    self.orphan_scene_count,
                    self.missing_image_count,
                    self.missing_embedding_count,
                    self.source_episode_outside_acquisition_count,
                    self.holdout_final_source_count,
                    self.write_count,
                    self.memory_rebuilt,
                    self.reencoding_count,
                    self.row_mutation_count,
                )
            ):
                raise ValueError("Closed provenance violates immutable closure")
            if not all((self.snapshot_guard_passed, self.sqlite_integrity_passed)):
                raise ValueError("Closed provenance lacks read-only integrity proof")
            if len(self.scene_lineage) != 144:
                raise ValueError("Closed provenance requires all Scene rows")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Actual-provenance audit hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["scene_lineage"] = [dict(item) for item in self.scene_lineage]
        payload["errors"] = list(self.errors)
        return payload


def audit_actual_paper_memory_v5(
    *,
    source_commit: str,
    snapshot_manifest_path: str | Path,
    actual_acquisition_manifest_path: str | Path,
    accepted_source_manifest_path: str | Path,
    acquisition_root: str | Path,
    lineage_input_path: str | Path,
    lineage_audit_path: str | Path,
    mineclip_policy_path: str | Path,
    checkpoint_manifest_path: str | Path,
    checkpoint_path: str | Path,
    mineclip_probe_path: str | Path,
    rebuild_contract_path: str | Path,
    build_stats_path: str | Path,
    readonly_snapshot_smoke_path: str | Path,
) -> ActualPaperMemoryV5ProvenanceClosureAudit:
    """Audit actual V5 bytes without encoding, deduplicating, or writing."""

    snapshot_path = Path(snapshot_manifest_path).resolve()
    actual_acquisition_path = Path(actual_acquisition_manifest_path).resolve()
    source_manifest_path = Path(accepted_source_manifest_path).resolve()
    acquisition_root = Path(acquisition_root).resolve()
    policy_path = Path(mineclip_policy_path).resolve()
    checkpoint_manifest_path = Path(checkpoint_manifest_path).resolve()
    checkpoint_path = Path(checkpoint_path).resolve()
    probe_path = Path(mineclip_probe_path).resolve()
    contract_path = Path(rebuild_contract_path).resolve()
    stats_path = Path(build_stats_path).resolve()
    readonly_smoke_path = Path(readonly_snapshot_smoke_path).resolve()

    errors: list[str] = []
    snapshot_payload = _load_object(snapshot_path)
    actual_acquisition = _load_object(actual_acquisition_path)
    source_manifest = _load_object(source_manifest_path)
    lineage_payload = _load_object(lineage_input_path)
    lineage_audit = _load_object(lineage_audit_path)
    policy = _load_object(policy_path)
    checkpoint_manifest = _load_object(checkpoint_manifest_path)
    probe = _load_object(probe_path)
    contract_payload = _load_object(contract_path)
    stats = _load_object(stats_path)
    readonly_smoke = _load_object(readonly_smoke_path)
    contract = MineCLIPV5RebuildContract(**contract_payload)
    manifest = MemorySnapshotManifest.from_json(snapshot_path)

    assert_snapshot_unchanged(manifest)
    snapshot_before = manifest.snapshot_root_sha256
    database_before = sha256_file(Path(manifest.database_path))
    asset_before = canonical_sha256(manifest.asset_files)

    actual_files = dict(actual_acquisition.get("files", {}))
    source_files = dict(source_manifest.get("files", {}))
    if actual_files != source_files:
        errors.append("actual and accepted-source acquisition file maps differ")
    if len(actual_files) != 184 or actual_acquisition.get("file_count") != 184:
        errors.append("actual acquisition manifest does not contain 184 files")
    if _nul_delimited_file_map_sha(actual_files) != actual_acquisition.get("root_sha256"):
        errors.append("actual acquisition root digest is invalid")
    source_file_map_sha = canonical_sha256(source_files)
    if source_file_map_sha != source_manifest.get("root_sha256"):
        errors.append("accepted-source acquisition root digest is invalid")
    if contract.acquisition_manifest_sha256 != sha256_file(source_manifest_path):
        errors.append("builder contract does not bind accepted-source manifest")
    if contract.acquisition_root_sha256 != source_manifest.get("root_sha256"):
        errors.append("builder contract does not bind accepted-source root")
    source_file_mismatches = 0
    for relative, expected in source_files.items():
        path = acquisition_root / relative
        if not path.is_file() or sha256_file(path) != expected:
            source_file_mismatches += 1
    if source_file_mismatches:
        errors.append(f"{source_file_mismatches} accepted source files are missing or changed")

    snapshot_sha = sha256_file(snapshot_path)
    actual_acquisition_sha = sha256_file(actual_acquisition_path)
    if snapshot_payload.get("acquisition_manifest_sha256") != actual_acquisition_sha:
        errors.append("snapshot does not bind the actual acquisition manifest")
    if snapshot_payload.get("database_sha256") != database_before:
        errors.append("snapshot database hash mismatch")
    if snapshot_payload.get("snapshot_root_sha256") != snapshot_before:
        errors.append("snapshot root mismatch")
    if snapshot_payload.get("source_commit") != contract.source_commit:
        errors.append("snapshot and builder source commits differ")
    if snapshot_payload.get("table_counts") != {
        "dependency_edges": 27,
        "episodes": 40,
        "metadata": 1,
        "scene_exemplars": 144,
    }:
        errors.append("snapshot manifest table counts differ from 40/27/144")
    readonly_checks = {
        "snapshot_manifest_sha256": snapshot_sha,
        "snapshot_root_sha256_before": snapshot_before,
        "snapshot_root_sha256_after": snapshot_before,
        "successful_episode_count": 40,
        "dependency_edge_count": 27,
        "scene_exemplar_count": 144,
        "readonly_open_passed": True,
        "database_query_only": True,
        "mutation_attempt_blocked": True,
        "eligible": True,
    }
    for key, expected in readonly_checks.items():
        if readonly_smoke.get(key) != expected:
            errors.append(f"read-only snapshot smoke mismatch: {key}")

    metadata = snapshot_payload.get("metadata", {})
    expected_metadata = {
        "mineclip_v5_rebuild_contract_id": contract.contract_id,
        "mineclip_policy_id": policy.get("policy_id"),
        "mineclip_checkpoint_manifest_id": checkpoint_manifest.get("manifest_id"),
        "mineclip_checkpoint_sha256": checkpoint_manifest.get("checkpoint_sha256"),
        "mineclip_repository_commit": policy.get("repository_commit"),
        "mineclip_variant": policy.get("variant"),
        "scene_frame_strategy": policy.get("frame_strategy"),
        "acquisition_root_sha256": source_manifest.get("root_sha256"),
        "image_encoder_identity": "dc3pa.memory.mineclip_scene_encoder:MineCLIPImageEncoder",
        "text_encoder_identity": "dc3pa.memory.mineclip_scene_encoder:MineCLIPTextEncoder",
        "build_from_successful_records_only": True,
        "dependency_extraction_offline_only": True,
        "no_new_minedojo_episodes": True,
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            errors.append(f"snapshot metadata mismatch: {key}")

    policy_id = str(policy.get("policy_id", ""))
    if canonical_policy_id(policy) != policy_id:
        errors.append("actual MineCLIP policy ID is not canonical")
    checkpoint_sha = sha256_file(checkpoint_path)
    checkpoint_md5 = _file_md5(checkpoint_path)
    checkpoint_checks = {
        "policy_id": policy_id,
        "checkpoint_sha256": checkpoint_sha,
        "checkpoint_md5": checkpoint_md5,
    }
    for key, expected in checkpoint_checks.items():
        if checkpoint_manifest.get(key) != expected:
            errors.append(f"checkpoint manifest mismatch: {key}")
    if not all(
        checkpoint_manifest.get(key) is True
        for key in (
            "checkpoint_loaded_strictly",
            "inference_probe_passed",
            "deterministic_repeat_probe_passed",
        )
    ):
        errors.append("frozen checkpoint manifest lacks strict deterministic probe")
    if not all(
        probe.get(key) is True
        for key in (
            "checkpoint_loaded_strictly",
            "inference_probe_passed",
            "deterministic_repeat_probe_passed",
        )
    ):
        errors.append("actual checkpoint revalidation probe failed")
    if probe.get("policy_id") != policy_id or probe.get("checkpoint_sha256") != checkpoint_sha:
        errors.append("actual checkpoint revalidation probe identity mismatch")

    receipt_records: dict[str, dict[str, Any]] = {}
    receipt_hashes: dict[str, str] = {}
    task_seed_run_count = 0
    holdout_final_count = 0
    for relative in sorted(source_files):
        if not relative.startswith("episodes/") or not relative.endswith(".json"):
            continue
        payload = _load_object(acquisition_root / relative)
        record = payload.get("record")
        if not isinstance(record, dict):
            errors.append(f"{relative}: missing record")
            continue
        episode_id = str(record.get("episode_id", ""))
        binding = record.get("metadata", {}).get("formal_acquisition_binding", {})
        identity_ok = all(
            (
                episode_id,
                record.get("task_name"),
                record.get("seed"),
                binding.get("run_id") == episode_id,
                str(binding.get("task", "")) == str(record.get("task_name", "")),
                str(binding.get("seed", "")) == str(record.get("seed", "")),
            )
        )
        if identity_ok:
            task_seed_run_count += 1
        else:
            errors.append(f"{relative}: incomplete task/seed/run identity")
        forbidden = _forbidden_source_labels(record)
        holdout_final_count += len(forbidden)
        errors.extend(f"{relative}: {item}" for item in forbidden)
        receipt_records[episode_id] = record
        receipt_hashes[episode_id] = str(source_files[relative])
    if len(receipt_records) != 40:
        errors.append("accepted source episode count is not 40")

    lineage_by_scene = {
        str(item.get("retained_scene_id")): item
        for item in lineage_payload.get("candidate_lineage", ())
    }
    if len(lineage_by_scene) != len(lineage_payload.get("candidate_lineage", ())):
        errors.append("duplicate retained Scene ID in lineage input")

    uri = f"file:{Path(manifest.database_path).resolve()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    scene_evidence: list[dict[str, Any]] = []
    orphan_count = missing_image_count = missing_embedding_count = 0
    try:
        integrity_ok = connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        episodes = connection.execute(
            "SELECT episode_id, task_name, success FROM episodes ORDER BY episode_id"
        ).fetchall()
        episode_ids = {str(row["episode_id"]) for row in episodes if row["success"] == 1}
        edge_count = int(connection.execute("SELECT COUNT(*) FROM dependency_edges").fetchone()[0])
        rows = connection.execute("SELECT * FROM scene_exemplars ORDER BY exemplar_id").fetchall()
        for index, row in enumerate(rows):
            scene_id = str(row["exemplar_id"])
            lineage = lineage_by_scene.get(scene_id)
            if lineage is None or str(row["episode_id"]) not in receipt_records:
                orphan_count += 1
                continue
            row_metadata = json.loads(row["metadata_json"])
            image_vector = np.frombuffer(row["image_vector"], dtype="<f4")
            text_vector = np.frombuffer(row["text_vector"], dtype="<f4")
            embedding_valid = all(
                (
                    image_vector.size == 512,
                    text_vector.size == 512,
                    np.isfinite(image_vector).all(),
                    np.isfinite(text_vector).all(),
                    np.isclose(np.linalg.norm(image_vector), 1.0, atol=1e-5),
                    np.isclose(np.linalg.norm(text_vector), 1.0, atol=1e-5),
                )
            )
            if not embedding_valid:
                missing_embedding_count += 1
            image_path = Path(str(row["image_path"]))
            image_label = f"images/{image_path.name}"
            image_sha = sha256_file(image_path) if image_path.is_file() else ""
            if not image_sha or manifest.asset_files.get(image_label) != image_sha:
                missing_image_count += 1
            action_index = int(row_metadata.get("action_index", -1))
            source_image_label = (
                f"images/{row['episode_id']}/{row['step_id']}_a{action_index:03d}.npy"
            )
            receipt = receipt_records[str(row["episode_id"])]
            matching_candidates = [
                item
                for item in receipt.get("scene_candidates", ())
                if str(item.get("step_id")) == str(row["step_id"])
                and str(item.get("metadata", {}).get("action_key"))
                == str(row_metadata.get("action_key"))
            ]
            evidence = {
                "scene_id": scene_id,
                "canonical_dedup_key": str(lineage.get("deterministic_dedup_key", "")),
                "canonical_owner": str(lineage.get("retained_scene_owner_task", "")),
                "source_episode_id": str(row["episode_id"]),
                "source_episode_receipt_sha256": receipt_hashes.get(str(row["episode_id"]), ""),
                "source_task": str(lineage.get("source_task", "")),
                "source_image_id": str(row["step_id"]),
                "source_image_array_sha256": str(actual_files.get(source_image_label, "")),
                "retained_image_sha256": image_sha,
                "stored_embedding_table": "scene_exemplars",
                "stored_embedding_row_index": index,
                "stored_image_embedding_sha256": hashlib.sha256(row["image_vector"]).hexdigest(),
                "stored_text_embedding_sha256": hashlib.sha256(row["text_vector"]).hexdigest(),
                "action": row_metadata.get("action"),
                "subgoal": str(row_metadata.get("local_subgoal", "")),
                "action_signature": str(row_metadata.get("action_key", "")),
                "mineclip_policy_id": policy_id,
                "database_row_identity": _row_identity(row),
                "database_table": "scene_exemplars",
                "candidate_id": str(lineage.get("candidate_id", "")),
            }
            required = [value for key, value in evidence.items() if key != "stored_embedding_row_index"]
            if not all(value not in (None, "") for value in required):
                errors.append(f"{scene_id}: incomplete Scene lineage")
            if len(matching_candidates) != 1:
                errors.append(f"{scene_id}: source receipt candidate is not unique")
            else:
                candidate = matching_candidates[0]
                candidate_metadata = candidate.get("metadata", {})
                source_path = str(candidate.get("image_path", ""))
                if source_path != source_image_label:
                    errors.append(f"{scene_id}: source image path mismatch")
                if candidate_metadata.get("image_sha256") != actual_files.get(source_image_label):
                    errors.append(f"{scene_id}: source image hash mismatch")
                if candidate.get("action") != row_metadata.get("action"):
                    errors.append(f"{scene_id}: source action mismatch")
                if str(candidate.get("local_subgoal", "")) != evidence["subgoal"]:
                    errors.append(f"{scene_id}: source subgoal mismatch")
                if str(candidate_metadata.get("action_key", "")) != evidence["action_signature"]:
                    errors.append(f"{scene_id}: source action signature mismatch")
            if str(row["task_name"]) != evidence["canonical_owner"]:
                errors.append(f"{scene_id}: canonical owner mismatch")
            if str(lineage.get("source_episode_id")) != evidence["source_episode_id"]:
                errors.append(f"{scene_id}: source episode mismatch")
            scene_evidence.append(evidence)
    finally:
        connection.close()

    if len(episode_ids) != 40 or episode_ids != set(receipt_records):
        errors.append("database episode set differs from accepted acquisition")
    source_scene_episodes = {item["source_episode_id"] for item in scene_evidence}
    outside_count = len(source_scene_episodes - set(receipt_records))
    if outside_count:
        errors.append("Scene source episode exists outside acquisition")
    if edge_count != 27:
        errors.append("dependency edge count is not 27")
    unique_scene_count = len({item["scene_id"] for item in scene_evidence})
    duplicate_count = len(scene_evidence) - unique_scene_count
    if len({item["canonical_dedup_key"] for item in scene_evidence}) != 144:
        errors.append("canonical Scene dedup keys are not unique")
    if len(rows) != 144 or unique_scene_count != 144:
        errors.append("Scene identity is not exactly 144 unique rows")

    no_scene_episodes = set(receipt_records) - source_scene_episodes
    expected_no_scene = set()
    for item in lineage_audit.get("results", ()):
        if item.get("reason") == "no_valid_scene_candidate":
            expected_no_scene.update(str(value) for value in item.get("successful_episode_ids", ()))
    if no_scene_episodes != expected_no_scene or any(
        receipt_records[value].get("scene_candidates") for value in no_scene_episodes
    ):
        errors.append("36/40 Scene-source explanation does not match frozen retention metadata")
    if lineage_audit.get("eligible") is not True or lineage_audit.get("snapshot_modified"):
        errors.append("frozen Scene-lineage audit is not eligible and immutable")

    stats_expected = {
        "acquisition_episodes": 40,
        "retained_dependency_edges": 27,
        "stored_scene_exemplars": 144,
        "structured_action_key_coverage": 1.0,
    }
    for key, expected in stats_expected.items():
        if stats.get(key) != expected:
            errors.append(f"build stats mismatch: {key}")

    assert_snapshot_unchanged(manifest)
    database_after = sha256_file(Path(manifest.database_path))
    asset_after = canonical_sha256(manifest.asset_files)
    snapshot_after = manifest.snapshot_root_sha256
    if (database_before, asset_before, snapshot_before) != (
        database_after,
        asset_after,
        snapshot_after,
    ):
        errors.append("immutable snapshot changed during provenance audit")

    scene_lineage_root = canonical_sha256(scene_evidence)
    embedding_root = canonical_sha256(
        [
            {
                "scene_id": item["scene_id"],
                "image": item["stored_image_embedding_sha256"],
                "text": item["stored_text_embedding_sha256"],
            }
            for item in scene_evidence
        ]
    )
    status = "ACTUAL_PROVENANCE_CLOSED" if not errors else "ACTUAL_ARTIFACT_CONFLICT"
    return ActualPaperMemoryV5ProvenanceClosureAudit(
        source_commit=source_commit,
        status=status,
        embedding_evidence_path="P1",
        actual_snapshot_manifest_id=snapshot_sha,
        actual_snapshot_manifest_file_sha256=snapshot_sha,
        actual_acquisition_manifest_id=actual_acquisition_sha,
        actual_acquisition_manifest_file_sha256=actual_acquisition_sha,
        actual_acquisition_root_sha256=str(actual_acquisition.get("root_sha256", "")),
        accepted_source_manifest_id=sha256_file(source_manifest_path),
        accepted_source_manifest_file_sha256=sha256_file(source_manifest_path),
        accepted_source_root_sha256=str(source_manifest.get("root_sha256", "")),
        accepted_source_file_map_sha256=source_file_map_sha,
        accepted_source_file_count=len(source_files),
        snapshot_root_sha256=snapshot_before,
        database_sha256=database_before,
        asset_manifest_sha256=asset_before,
        builder_source_commit=str(snapshot_payload.get("source_commit", "")),
        builder_contract_id=contract.contract_id,
        builder_contract_file_sha256=sha256_file(contract_path),
        build_stats_file_sha256=sha256_file(stats_path),
        mineclip_policy_id=policy_id,
        mineclip_policy_file_sha256=sha256_file(policy_path),
        mineclip_checkpoint_manifest_id=str(checkpoint_manifest.get("manifest_id", "")),
        mineclip_checkpoint_manifest_file_sha256=sha256_file(checkpoint_manifest_path),
        mineclip_checkpoint_sha256=checkpoint_sha,
        mineclip_checkpoint_md5=checkpoint_md5,
        mineclip_probe_id=str(probe.get("probe_id", probe.get("manifest_id", ""))),
        mineclip_probe_file_sha256=sha256_file(probe_path),
        readonly_snapshot_smoke_id=str(readonly_smoke.get("smoke_id", "")),
        readonly_snapshot_smoke_file_sha256=sha256_file(readonly_smoke_path),
        accepted_episode_count=len(receipt_records),
        accepted_episode_identity_root=canonical_sha256(sorted(receipt_records)),
        source_receipt_hash_root=canonical_sha256(receipt_hashes),
        scene_source_episode_count=len(source_scene_episodes),
        scene_source_episode_identity_root=canonical_sha256(sorted(source_scene_episodes)),
        no_scene_episode_count=len(no_scene_episodes),
        no_scene_reason="frozen_no_valid_scene_candidate",
        dependency_edge_count=edge_count,
        scene_exemplar_count=len(rows),
        unique_scene_count=unique_scene_count,
        scene_lineage_root=scene_lineage_root,
        embedding_row_hash_root=embedding_root,
        duplicate_scene_id_count=duplicate_count,
        orphan_scene_count=orphan_count,
        missing_image_count=missing_image_count,
        missing_embedding_count=missing_embedding_count,
        source_episode_outside_acquisition_count=outside_count,
        task_seed_run_identity_count=task_seed_run_count,
        holdout_final_source_count=holdout_final_count,
        snapshot_guard_passed=(snapshot_before == snapshot_after),
        sqlite_integrity_passed=integrity_ok,
        database_sha256_after=database_after,
        snapshot_root_sha256_after=snapshot_after,
        asset_manifest_sha256_after=asset_after,
        write_count=0,
        memory_rebuilt=False,
        reencoding_count=0,
        row_mutation_count=0,
        scene_lineage=tuple(scene_evidence),
        errors=tuple(dict.fromkeys(errors)),
    ).with_id()


@dataclass(frozen=True)
class RetirementEntry:
    object_id: str
    object_kind: str
    reason: str
    identity_complete: bool = True
    historical_object_preserved: bool = True
    prospective_use_forbidden: bool = True
    equivalence_to_actual_artifact_claimed: bool = False
    scientific_results_produced_under_object: int = 0

    def __post_init__(self) -> None:
        if HISTORICAL_REFERENCE.fullmatch(self.object_id) is None:
            raise ValueError("Retirement requires a hexadecimal historical reference")
        if self.identity_complete != _full_id(self.object_id):
            raise ValueError("Retirement identity-completeness declaration is incorrect")
        if not all((self.historical_object_preserved, self.prospective_use_forbidden)):
            raise ValueError("Retirement safeguards are incomplete")
        if self.equivalence_to_actual_artifact_claimed:
            raise ValueError("Retirement cannot claim historical equivalence")
        if self.scientific_results_produced_under_object != 0:
            raise ValueError("Retired prospective object has scientific results")


@dataclass(frozen=True)
class InvalidBindingRetirementRegistry(_Hashed):
    source_commit: str
    entries: tuple[RetirementEntry, ...]
    historical_objects_deleted: bool = False
    schema_version: int = SCHEMA_VERSION
    registry_id: str = ""

    _id_field = "registry_id"

    def __post_init__(self) -> None:
        ids = [entry.object_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Retirement registry contains duplicate IDs")
        if self.historical_objects_deleted:
            raise ValueError("Historical objects cannot be deleted")
        if self.registry_id and self.registry_id != self.compute_id():
            raise ValueError("Retirement registry hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["entries"] = [asdict(entry) for entry in self.entries]
        return payload

    def rejects(self, object_id: str) -> bool:
        if not _full_id(object_id):
            return True
        return object_id in {entry.object_id for entry in self.entries}


@dataclass(frozen=True)
class ProspectiveRebaselineImpactAudit(_Hashed):
    source_commit: str
    invalid_binding_retirement_registry_id: str
    readiness_decision_id: str
    readiness_decision_file_sha256: str
    blocked_v1_audit_id: str
    blocked_v1_audit_file_sha256: str
    blocked_v2_audit_id: str
    blocked_v2_audit_file_sha256: str
    engineering_smoke_audit_id: str
    engineering_smoke_audit_file_sha256: str
    engineering_smoke_rows_under_invalid_contracts: int
    formal_v4_1_development_rows: int
    chrm_cdt_fitted_artifact_count: int
    holdout_final_row_count: int
    prospective_rebaseline_justified: bool
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        counts = (
            self.engineering_smoke_rows_under_invalid_contracts,
            self.formal_v4_1_development_rows,
            self.chrm_cdt_fitted_artifact_count,
            self.holdout_final_row_count,
        )
        if self.prospective_rebaseline_justified != all(value == 0 for value in counts):
            raise ValueError("Prospective impact conclusion does not match result counts")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Prospective impact audit hash mismatch")


@dataclass(frozen=True)
class ActualArtifactCandidateRelease(_Hashed):
    release_name: str
    source_commit: str
    provenance_closure_audit_id: str
    mineclip_policy_id: str
    mineclip_checkpoint_manifest_id: str
    mineclip_checkpoint_sha256: str
    snapshot_manifest_id: str
    acquisition_manifest_id: str
    snapshot_root_sha256: str
    database_sha256: str
    asset_manifest_sha256: str
    accepted_episode_count: int
    scene_source_episode_count: int
    dependency_edge_count: int
    scene_exemplar_count: int
    scene_lineage_root: str
    builder_contract_id: str
    builder_source_commit: str
    read_only_no_write_verified: bool
    release_scope: str = "prospective_authoritative_rebaseline_candidate"
    authorization_status: str = "pending"
    usable: bool = False
    memory_rebuilt: bool = False
    database_bytes_changed: bool = False
    image_bytes_changed: bool = False
    embedding_bytes_changed: bool = False
    historical_equivalence_claimed: bool = False
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        if self.release_scope != "prospective_authoritative_rebaseline_candidate":
            raise ValueError("Candidate release scope changed")
        if self.authorization_status != "pending" or self.usable:
            raise ValueError("Pre-approval candidate cannot be usable")
        if any(
            (
                self.memory_rebuilt,
                self.database_bytes_changed,
                self.image_bytes_changed,
                self.embedding_bytes_changed,
                self.historical_equivalence_claimed,
            )
        ):
            raise ValueError("Candidate release changes or equates frozen assets")
        if not self.read_only_no_write_verified:
            raise ValueError("Candidate release lacks no-write evidence")
        if (
            self.accepted_episode_count,
            self.scene_source_episode_count,
            self.dependency_edge_count,
            self.scene_exemplar_count,
        ) != (40, 36, 27, 144):
            raise ValueError("Candidate release aggregate identity changed")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("Candidate release hash mismatch")


def build_candidate_release(
    *,
    release_name: str,
    closure: ActualPaperMemoryV5ProvenanceClosureAudit,
) -> ActualArtifactCandidateRelease:
    if closure.status != "ACTUAL_PROVENANCE_CLOSED":
        raise ValueError("Actual provenance is not closed")
    return ActualArtifactCandidateRelease(
        release_name=release_name,
        source_commit=closure.source_commit,
        provenance_closure_audit_id=closure.audit_id,
        mineclip_policy_id=closure.mineclip_policy_id,
        mineclip_checkpoint_manifest_id=closure.mineclip_checkpoint_manifest_id,
        mineclip_checkpoint_sha256=closure.mineclip_checkpoint_sha256,
        snapshot_manifest_id=closure.actual_snapshot_manifest_id,
        acquisition_manifest_id=closure.actual_acquisition_manifest_id,
        snapshot_root_sha256=closure.snapshot_root_sha256,
        database_sha256=closure.database_sha256,
        asset_manifest_sha256=closure.asset_manifest_sha256,
        accepted_episode_count=closure.accepted_episode_count,
        scene_source_episode_count=closure.scene_source_episode_count,
        dependency_edge_count=closure.dependency_edge_count,
        scene_exemplar_count=closure.scene_exemplar_count,
        scene_lineage_root=closure.scene_lineage_root,
        builder_contract_id=closure.builder_contract_id,
        builder_source_commit=closure.builder_source_commit,
        read_only_no_write_verified=closure.write_count == 0,
    ).with_id()


@dataclass(frozen=True)
class ProspectiveMemoryRebaselineAuthorizationInput(_Hashed):
    source_commit: str
    provenance_closure_audit_id: str
    provenance_closure_audit_file_sha256: str
    retirement_registry_id: str
    retirement_registry_file_sha256: str
    impact_audit_id: str
    impact_audit_file_sha256: str
    paper_memory_candidate_release_id: str
    paper_memory_candidate_release_file_sha256: str
    scene_candidate_release_id: str
    scene_candidate_release_file_sha256: str
    actual_mineclip_policy_id: str
    actual_snapshot_manifest_id: str
    actual_acquisition_manifest_id: str
    declarations: tuple[str, ...]
    approved_by: str | None = None
    rebaseline_authorization_status: str = "pending"
    contract_regeneration_permitted: bool = False
    schema_version: int = SCHEMA_VERSION
    authorization_input_id: str = ""

    _id_field = "authorization_input_id"

    def __post_init__(self) -> None:
        if self.declarations != REBASELINE_DECLARATIONS:
            raise ValueError("Re-baseline authorization declarations changed")
        if self.approved_by is not None:
            raise ValueError("Author approval cannot be fabricated in an input")
        if self.rebaseline_authorization_status != "pending":
            raise ValueError("Pre-approval authorization status must be pending")
        if self.contract_regeneration_permitted:
            raise ValueError("Contract regeneration requires external approval")
        if self.authorization_input_id and self.authorization_input_id != self.compute_id():
            raise ValueError("Authorization input hash mismatch")


def build_authorization_input(
    *,
    source_commit: str,
    closure: ActualPaperMemoryV5ProvenanceClosureAudit,
    closure_file_sha256: str,
    retirement: InvalidBindingRetirementRegistry,
    retirement_file_sha256: str,
    impact: ProspectiveRebaselineImpactAudit,
    impact_file_sha256: str,
    paper_candidate: ActualArtifactCandidateRelease,
    paper_candidate_file_sha256: str,
    scene_candidate: ActualArtifactCandidateRelease,
    scene_candidate_file_sha256: str,
) -> ProspectiveMemoryRebaselineAuthorizationInput:
    if closure.status != "ACTUAL_PROVENANCE_CLOSED" or not impact.prospective_rebaseline_justified:
        raise ValueError("Re-baseline authorization input is not eligible")
    return ProspectiveMemoryRebaselineAuthorizationInput(
        source_commit=source_commit,
        provenance_closure_audit_id=closure.audit_id,
        provenance_closure_audit_file_sha256=closure_file_sha256,
        retirement_registry_id=retirement.registry_id,
        retirement_registry_file_sha256=retirement_file_sha256,
        impact_audit_id=impact.audit_id,
        impact_audit_file_sha256=impact_file_sha256,
        paper_memory_candidate_release_id=paper_candidate.release_id,
        paper_memory_candidate_release_file_sha256=paper_candidate_file_sha256,
        scene_candidate_release_id=scene_candidate.release_id,
        scene_candidate_release_file_sha256=scene_candidate_file_sha256,
        actual_mineclip_policy_id=closure.mineclip_policy_id,
        actual_snapshot_manifest_id=closure.actual_snapshot_manifest_id,
        actual_acquisition_manifest_id=closure.actual_acquisition_manifest_id,
        declarations=REBASELINE_DECLARATIONS,
    ).with_id()


def retired_reference_is_eligible(
    object_id: str, registry: InvalidBindingRetirementRegistry
) -> bool:
    return not registry.rejects(object_id)


def transitive_dependency_ids(
    *,
    nodes: Mapping[str, Iterable[str]],
    invalid_roots: Iterable[str],
) -> tuple[str, ...]:
    """Return full-ID nodes that directly or transitively bind invalid roots."""

    roots = set(invalid_roots)
    if any(HISTORICAL_REFERENCE.fullmatch(value) is None for value in roots):
        raise ValueError("Dependency roots must be hexadecimal historical references")
    dependent: set[str] = set()
    changed = True
    while changed:
        changed = False
        for object_id, references in nodes.items():
            if not _full_id(object_id):
                raise ValueError("Dependency node must use a full ID")
            if object_id not in dependent and set(references) & (roots | dependent):
                dependent.add(object_id)
                changed = True
    return tuple(sorted(dependent))
