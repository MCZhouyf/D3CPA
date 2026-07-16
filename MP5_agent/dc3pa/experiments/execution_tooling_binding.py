"""Authorize a source-commit update limited to Round 5.10 execution tooling.

The parent formal-bootstrap authorization remains the scientific authorization.
This binding permits a new source commit only when prompts, Controller,
Evaluator, taskset, policy, amendment, Blueprint, and schedule identities are
unchanged. Runtime behavior changes require a new scientific authorization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping


SCHEMA_VERSION = 1
PARENT_SOURCE_COMMIT = "540e83f9d75358e1eacb218bfc75fc4ae41f3b9c"
PARENT_AUTHORIZATION_ID = (
    "21acefe77baa226742088b61f5d792cd7d490f83df67c7ea3ab76d9b08ead03f"
)
ALLOWED_CHANGE_CLASSES = frozenset(
    {
        "execution_orchestration",
        "attempt_ledger",
        "provenance_binding",
        "acquisition_audit",
        "offline_memory_build_binding",
        "readonly_snapshot_audit",
        "tests_and_documentation",
    }
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ExecutionToolingBinding:
    binding_name: str
    approved_by: str
    approval_record_id: str
    source_extension_audit_sha256: str
    parent_source_commit: str
    new_source_commit: str
    parent_formal_authorization_id: str
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    blueprint_id: str
    acquisition_schedule_id: str
    taskset_release_id: str
    prompt_hash_bundle_id_before: str
    prompt_hash_bundle_id_after: str
    controller_identity_sha256_before: str
    controller_identity_sha256_after: str
    evaluator_identity_sha256_before: str
    evaluator_identity_sha256_after: str
    task_catalog_sha256_before: str
    task_catalog_sha256_after: str
    allowed_change_classes: tuple[str, ...]
    prompts_changed: bool
    controller_behavior_changed: bool
    evaluator_behavior_changed: bool
    task_catalog_changed: bool
    seeds_or_schedule_changed: bool
    bootstrap_policy_changed: bool
    formal_acquisition_started_before_binding: bool
    schema_version: int = SCHEMA_VERSION
    binding_id: str = ""

    def __post_init__(self) -> None:
        if self.approved_by != "ZYF":
            raise ValueError("Execution tooling binding must be approved by ZYF")
        if self.parent_source_commit != PARENT_SOURCE_COMMIT:
            raise ValueError("Unexpected parent source commit")
        if self.parent_formal_authorization_id != PARENT_AUTHORIZATION_ID:
            raise ValueError("Unexpected parent formal authorization")
        if not self.new_source_commit or self.new_source_commit == self.parent_source_commit:
            raise ValueError("New source commit is invalid")
        if set(self.allowed_change_classes) != ALLOWED_CHANGE_CLASSES:
            raise ValueError("Execution tooling change-class set is incomplete")
        identity_pairs = (
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
                self.task_catalog_sha256_before,
                self.task_catalog_sha256_after,
                "task catalog",
            ),
        )
        for before, after, label in identity_pairs:
            if not before or before != after:
                raise ValueError(f"{label} changed across tooling update")
        if any(
            (
                self.prompts_changed,
                self.controller_behavior_changed,
                self.evaluator_behavior_changed,
                self.task_catalog_changed,
                self.seeds_or_schedule_changed,
                self.bootstrap_policy_changed,
                self.formal_acquisition_started_before_binding,
            )
        ):
            raise ValueError("Tooling binding includes a protected behavior change")
        required = (
            self.binding_name,
            self.approval_record_id,
            self.source_extension_audit_sha256,
            self.bootstrap_policy_id,
            self.bootstrap_amendment_id,
            self.blueprint_id,
            self.acquisition_schedule_id,
            self.taskset_release_id,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Execution tooling binding identity is incomplete")
        expected = self.compute_binding_id()
        if self.binding_id and self.binding_id != expected:
            raise ValueError("Execution tooling binding hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("binding_id", None)
        payload["allowed_change_classes"] = sorted(
            self.allowed_change_classes
        )
        return payload

    def compute_binding_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "ExecutionToolingBinding":
        return replace(self, binding_id=self.compute_binding_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.binding_id else self.with_id()
        payload = item.payload_without_id()
        payload["binding_id"] = item.binding_id
        return payload
