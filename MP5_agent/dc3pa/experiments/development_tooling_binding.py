"""Authorize Round 5.11 shadow collection and analysis tooling only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any


SCHEMA_VERSION = 1
PARENT_SOURCE_COMMIT = "30d455add0ef302d9ac967da083a82426a16187c"
ALLOWED_CHANGE_CLASSES = frozenset(
    {
        "scene_lineage_audit",
        "development_protocol_binding",
        "shadow_feature_instrumentation",
        "development_record_schema",
        "confidence_calibration",
        "environment_parameter_selection",
        "fusion_feature_export",
        "tests_and_documentation",
    }
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class DevelopmentToolingBinding:
    binding_name: str
    approved_by: str
    approval_record_id: str
    parent_source_commit: str
    new_source_commit: str
    paper_memory_v5_release_id: str
    active_taskset_release_id: str
    formal_bootstrap_policy_id: str
    prompt_hash_bundle_id_before: str
    prompt_hash_bundle_id_after: str
    controller_identity_sha256_before: str
    controller_identity_sha256_after: str
    evaluator_identity_sha256_before: str
    evaluator_identity_sha256_after: str
    active_catalog_sha256_before: str
    active_catalog_sha256_after: str
    paper_memory_snapshot_root_before: str
    paper_memory_snapshot_root_after: str
    allowed_change_classes: tuple[str, ...]
    prompts_changed: bool
    controller_behavior_changed: bool
    evaluator_behavior_changed: bool
    active_taskset_changed: bool
    paper_memory_changed: bool
    bootstrap_policy_changed: bool
    development_collection_started_before_binding: bool
    schema_version: int = SCHEMA_VERSION
    binding_id: str = ""

    def __post_init__(self) -> None:
        if self.approved_by != "ZYF":
            raise ValueError("Development tooling binding must be approved by ZYF")
        if self.parent_source_commit != PARENT_SOURCE_COMMIT:
            raise ValueError("Unexpected Round 5.11 parent commit")
        if not self.new_source_commit or self.new_source_commit == self.parent_source_commit:
            raise ValueError("Development tooling source commit is invalid")
        if set(self.allowed_change_classes) != ALLOWED_CHANGE_CLASSES:
            raise ValueError("Development tooling change-class set is incomplete")
        for before, after, label in (
            (
                self.prompt_hash_bundle_id_before,
                self.prompt_hash_bundle_id_after,
                "prompt hashes",
            ),
            (
                self.controller_identity_sha256_before,
                self.controller_identity_sha256_after,
                "Controller identity",
            ),
            (
                self.evaluator_identity_sha256_before,
                self.evaluator_identity_sha256_after,
                "Evaluator identity",
            ),
            (
                self.active_catalog_sha256_before,
                self.active_catalog_sha256_after,
                "active catalog",
            ),
            (
                self.paper_memory_snapshot_root_before,
                self.paper_memory_snapshot_root_after,
                "Paper Memory V5 snapshot",
            ),
        ):
            if not before or before != after:
                raise ValueError(f"{label} changed across tooling update")
        if any(
            (
                self.prompts_changed,
                self.controller_behavior_changed,
                self.evaluator_behavior_changed,
                self.active_taskset_changed,
                self.paper_memory_changed,
                self.bootstrap_policy_changed,
                self.development_collection_started_before_binding,
            )
        ):
            raise ValueError("Development tooling binding changes protected behavior")
        required = (
            self.binding_name,
            self.approval_record_id,
            self.paper_memory_v5_release_id,
            self.active_taskset_release_id,
            self.formal_bootstrap_policy_id,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Development tooling binding is incomplete")
        expected = self.compute_binding_id()
        if self.binding_id and self.binding_id != expected:
            raise ValueError("Development tooling binding hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("binding_id", None)
        payload["allowed_change_classes"] = sorted(self.allowed_change_classes)
        return payload

    def compute_binding_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "DevelopmentToolingBinding":
        return replace(self, binding_id=self.compute_binding_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.binding_id else self.with_id()
        payload = item.payload_without_id()
        payload["binding_id"] = item.binding_id
        return payload
