"""Frozen input release for V5-bound development collection."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping


SCHEMA_VERSION = 1
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _require_sha256(value: str, label: str) -> None:
    if not HEX64.fullmatch(value):
        raise ValueError(f"{label} must be a full 64-character SHA-256")


@dataclass(frozen=True)
class DevelopmentInputRelease:
    release_name: str
    source_commit: str
    active_taskset_release_id: str
    active_catalog_sha256: str
    mineclip_policy_id: str
    mineclip_checkpoint_manifest_id: str
    mineclip_v5_contract_id: str
    paper_memory_v5_release_id: str
    paper_memory_snapshot_root_sha256: str
    paper_memory_database_sha256: str
    readonly_smoke_id: str
    coverage_audit_id: str
    scene_lineage_audit_id: str
    formal_bootstrap_policy_id: str
    formal_bootstrap_amendment_id: str
    prompt_hash_bundle_id: str
    controller_identity_sha256: str
    evaluator_identity_sha256: str
    requested_model_name: str
    returned_identity_policy: str
    development_protocol_id: str
    development_tooling_binding_id: str
    analysis_policy_id: str
    final_exclusion_id: str
    memory_is_read_only: bool
    memory_writes_forbidden: bool
    acquisition_writes_forbidden: bool
    holdout_access_forbidden_in_round511: bool
    active_task_name: str
    superseded_task_name: str
    eligible: bool
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        if not HEX40.fullmatch(self.source_commit):
            raise ValueError("Development source commit must be a full Git SHA")
        for value, label in (
            (self.active_taskset_release_id, "active taskset release"),
            (self.active_catalog_sha256, "active catalog"),
            (self.mineclip_policy_id, "MineCLIP policy"),
            (self.mineclip_checkpoint_manifest_id, "MineCLIP checkpoint manifest"),
            (self.mineclip_v5_contract_id, "MineCLIP V5 contract"),
            (self.paper_memory_v5_release_id, "Paper Memory V5 release"),
            (self.paper_memory_snapshot_root_sha256, "Memory snapshot root"),
            (self.paper_memory_database_sha256, "Memory database"),
            (self.readonly_smoke_id, "read-only smoke"),
            (self.coverage_audit_id, "coverage audit"),
            (self.scene_lineage_audit_id, "Scene-lineage audit"),
            (self.formal_bootstrap_policy_id, "formal bootstrap policy"),
            (self.formal_bootstrap_amendment_id, "formal bootstrap amendment"),
            (self.prompt_hash_bundle_id, "prompt hash bundle"),
            (self.controller_identity_sha256, "Controller identity"),
            (self.evaluator_identity_sha256, "Evaluator identity"),
            (self.development_protocol_id, "development protocol"),
            (self.development_tooling_binding_id, "development tooling binding"),
            (self.analysis_policy_id, "analysis policy"),
            (self.final_exclusion_id, "final exclusion"),
        ):
            _require_sha256(value, label)
        if self.requested_model_name != "gpt-5.1":
            raise ValueError("Requested model name must remain gpt-5.1")
        if self.returned_identity_policy != "record_only_not_eligibility":
            raise ValueError("Unexpected returned-identity policy")
        if not all(
            (
                self.memory_is_read_only,
                self.memory_writes_forbidden,
                self.acquisition_writes_forbidden,
                self.holdout_access_forbidden_in_round511,
                self.eligible,
            )
        ):
            raise ValueError("Development input safeguards are incomplete")
        if self.active_task_name != "craft wooden pressure plate":
            raise ValueError("Active taskset is not pressure-plate canonical")
        if self.superseded_task_name != "mine sand":
            raise ValueError("Superseded task identity is incorrect")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("Development input release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        return payload

    def compute_release_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "DevelopmentInputRelease":
        return replace(self, release_id=self.compute_release_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.release_id else self.with_id()
        payload = item.payload_without_id()
        payload["release_id"] = item.release_id
        return payload


def build_development_input_release(
    *,
    release_name: str,
    source_commit: str,
    active_taskset: Mapping[str, Any],
    mineclip_policy: Mapping[str, Any],
    checkpoint_manifest: Mapping[str, Any],
    v5_contract: Mapping[str, Any],
    paper_memory: Mapping[str, Any],
    readonly_smoke: Mapping[str, Any],
    coverage_audit: Mapping[str, Any],
    scene_lineage_audit: Mapping[str, Any],
    bootstrap_policy: Mapping[str, Any],
    bootstrap_amendment: Mapping[str, Any],
    prompt_hash_bundle_id: str,
    controller_identity_sha256: str,
    evaluator_identity_sha256: str,
    development_protocol_id: str,
    development_tooling_binding_id: str,
    analysis_policy_id: str,
    final_exclusion_id: str,
) -> DevelopmentInputRelease:
    errors: list[str] = []
    if not active_taskset.get("eligible", False):
        errors.append("active taskset release is ineligible")
    if active_taskset.get("pressure_plate_task_name") != (
        "craft wooden pressure plate"
    ):
        errors.append("active taskset is not pressure-plate canonical")
    if not paper_memory.get("eligible", False) or not paper_memory.get(
        "paper_candidate", False
    ):
        errors.append("Paper Memory V5 is not an eligible paper candidate")
    if paper_memory.get("encoder_name") != "MineCLIP":
        errors.append("Paper Memory V5 is not MineCLIP")
    if paper_memory.get("encoder_variant") != "attn":
        errors.append("Paper Memory V5 is not the attn profile")
    if not readonly_smoke.get("eligible", False):
        errors.append("Memory read-only smoke is ineligible")
    if readonly_smoke.get("snapshot_root_sha256_before") != readonly_smoke.get(
        "snapshot_root_sha256_after"
    ):
        errors.append("Memory snapshot changed during read-only smoke")
    if not coverage_audit.get("eligible", False):
        errors.append("Memory coverage audit is ineligible")
    if not scene_lineage_audit.get("eligible", False):
        errors.append("Scene-lineage audit is ineligible")
    if scene_lineage_audit.get("snapshot_modified", True):
        errors.append("Scene-lineage audit modified the snapshot")
    if int(scene_lineage_audit.get("new_minedojo_episode_count", -1)) != 0:
        errors.append("Scene-lineage audit ran MineDojo")
    if v5_contract.get("active_taskset_release_id") != active_taskset.get(
        "release_id"
    ):
        errors.append("V5 contract/active taskset mismatch")
    if paper_memory.get("active_taskset_release_id") != active_taskset.get(
        "release_id"
    ):
        errors.append("Paper Memory/active taskset mismatch")
    if paper_memory.get("mineclip_policy_id") != mineclip_policy.get("policy_id"):
        errors.append("Paper Memory/MineCLIP policy mismatch")
    if paper_memory.get("mineclip_checkpoint_manifest_id") != (
        checkpoint_manifest.get("manifest_id")
    ):
        errors.append("Paper Memory/checkpoint manifest mismatch")
    if errors:
        raise ValueError("; ".join(errors))

    return DevelopmentInputRelease(
        release_name=release_name,
        source_commit=source_commit,
        active_taskset_release_id=str(active_taskset["release_id"]),
        active_catalog_sha256=str(active_taskset["catalog_sha256"]),
        mineclip_policy_id=str(mineclip_policy["policy_id"]),
        mineclip_checkpoint_manifest_id=str(
            checkpoint_manifest["manifest_id"]
        ),
        mineclip_v5_contract_id=str(v5_contract["contract_id"]),
        paper_memory_v5_release_id=str(paper_memory["release_id"]),
        paper_memory_snapshot_root_sha256=str(
            paper_memory["snapshot_root_sha256"]
        ),
        paper_memory_database_sha256=str(paper_memory["database_sha256"]),
        readonly_smoke_id=str(readonly_smoke["smoke_id"]),
        coverage_audit_id=str(coverage_audit["audit_id"]),
        scene_lineage_audit_id=str(scene_lineage_audit["audit_id"]),
        formal_bootstrap_policy_id=str(bootstrap_policy["policy_id"]),
        formal_bootstrap_amendment_id=str(
            bootstrap_amendment["amendment_id"]
        ),
        prompt_hash_bundle_id=prompt_hash_bundle_id,
        controller_identity_sha256=controller_identity_sha256,
        evaluator_identity_sha256=evaluator_identity_sha256,
        requested_model_name="gpt-5.1",
        returned_identity_policy="record_only_not_eligibility",
        development_protocol_id=development_protocol_id,
        development_tooling_binding_id=development_tooling_binding_id,
        analysis_policy_id=analysis_policy_id,
        final_exclusion_id=final_exclusion_id,
        memory_is_read_only=True,
        memory_writes_forbidden=True,
        acquisition_writes_forbidden=True,
        holdout_access_forbidden_in_round511=True,
        active_task_name="craft wooden pressure plate",
        superseded_task_name="mine sand",
        eligible=True,
    ).with_id()
