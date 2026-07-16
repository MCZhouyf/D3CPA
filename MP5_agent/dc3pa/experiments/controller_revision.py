"""Bind Controller bug fixes, fallback policy, and evidence invalidation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
REQUIRED_NATURAL_FIXES = frozenset(
    {
        "reuse_placed_crafting_table",
        "propagate_underground_state",
        "stabilize_navigation_target_coordinates",
        "stop_navigation_after_target_acquired",
    }
)
FORMAL_FALLBACK_FORBIDDEN_SCOPES = frozenset(
    {
        "formal_acquisition",
        "dev_train",
        "dev_tune",
        "dev_holdout",
        "fusion_fitting",
        "final_evaluation",
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
class ControllerRevisionManifest:
    revision_name: str
    parent_commit: str
    source_commit: str
    natural_fix_ids: tuple[str, ...]
    natural_fix_test_ids: tuple[str, ...]
    fallback_policy_id: str
    fallback_approval_sha256: str
    fallback_default_enabled: bool
    fallback_allowed_scopes: tuple[str, ...]
    fallback_forbidden_scopes: tuple[str, ...]
    prompts_changed: bool
    controller_success_logic_changed: bool
    evaluator_success_logic_changed: bool
    task_specific_planner_rules_added: bool
    formal_acquisition_started: bool
    schema_version: int = SCHEMA_VERSION
    revision_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported Controller revision schema")
        required = (
            self.revision_name,
            self.parent_commit,
            self.source_commit,
            self.fallback_policy_id,
            self.fallback_approval_sha256,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Controller revision identity is incomplete")
        missing = REQUIRED_NATURAL_FIXES - set(self.natural_fix_ids)
        if missing:
            raise ValueError(f"Missing natural execution fixes: {sorted(missing)}")
        if len(self.natural_fix_test_ids) < len(REQUIRED_NATURAL_FIXES):
            raise ValueError("Every natural fix needs explicit regression evidence")
        if self.fallback_default_enabled:
            raise ValueError("Fallback must remain disabled by default")
        if set(self.fallback_allowed_scopes) != {"diagnostic_dry_run"}:
            raise ValueError("Fallback scope must be diagnostic_dry_run only")
        missing_forbidden = (
            FORMAL_FALLBACK_FORBIDDEN_SCOPES
            - set(self.fallback_forbidden_scopes)
        )
        if missing_forbidden:
            raise ValueError(
                f"Fallback forbidden scopes incomplete: {sorted(missing_forbidden)}"
            )
        if self.prompts_changed:
            raise ValueError("This revision may not change formal prompts")
        if self.controller_success_logic_changed:
            raise ValueError("This revision may not change Controller success logic")
        if self.evaluator_success_logic_changed:
            raise ValueError("This revision may not change Evaluator success logic")
        if self.task_specific_planner_rules_added:
            raise ValueError("Task-specific Planner corrections are forbidden")
        if self.formal_acquisition_started:
            raise ValueError("Revision must finish before formal acquisition")
        expected = self.compute_revision_id()
        if self.revision_id and self.revision_id != expected:
            raise ValueError("Controller revision hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("revision_id", None)
        payload["natural_fix_ids"] = sorted(self.natural_fix_ids)
        payload["natural_fix_test_ids"] = sorted(
            self.natural_fix_test_ids
        )
        payload["fallback_allowed_scopes"] = sorted(
            self.fallback_allowed_scopes
        )
        payload["fallback_forbidden_scopes"] = sorted(
            self.fallback_forbidden_scopes
        )
        return payload

    def compute_revision_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "ControllerRevisionManifest":
        return replace(self, revision_id=self.compute_revision_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.revision_id else self.with_id()
        payload = item.payload_without_id()
        payload["revision_id"] = item.revision_id
        return payload


@dataclass(frozen=True)
class InvalidatedEvidence:
    artifact_label: str
    artifact_id: str
    artifact_sha256: str
    bound_source_commit: str
    invalidation_reason: str

    def __post_init__(self) -> None:
        if not self.artifact_label or not self.bound_source_commit:
            raise ValueError("Invalidated evidence identity is incomplete")
        if not self.invalidation_reason.strip():
            raise ValueError("Invalidation reason is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceInvalidationManifest:
    manifest_name: str
    previous_source_commit: str
    replacement_source_commit: str
    controller_revision_id: str
    artifacts: tuple[InvalidatedEvidence, ...]
    required_regeneration_labels: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    manifest_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported evidence invalidation schema")
        if self.previous_source_commit == self.replacement_source_commit:
            raise ValueError("Replacement commit must differ from old commit")
        if not self.artifacts:
            raise ValueError("At least one previous artifact must be invalidated")
        required = {
            "github_actions",
            "full_pytest",
            "minedojo_marker",
            "controller_identity",
            "task_semantic_smoke",
            "final_taskset_release",
            "schema_v2_design",
            "semantic_migration",
            "approval_binding",
            "blueprint_validation",
            "model_epoch",
            "six_entry_readiness_campaign",
            "acquisition_readiness",
            "preacquisition_gate",
        }
        missing = required - set(self.required_regeneration_labels)
        if missing:
            raise ValueError(
                f"Regeneration list is incomplete: {sorted(missing)}"
            )
        expected = self.compute_manifest_id()
        if self.manifest_id and self.manifest_id != expected:
            raise ValueError("Invalidation manifest hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("manifest_id", None)
        payload["artifacts"] = [
            item.to_dict()
            for item in sorted(
                self.artifacts,
                key=lambda item: (
                    item.artifact_label,
                    item.artifact_id,
                ),
            )
        ]
        payload["required_regeneration_labels"] = sorted(
            self.required_regeneration_labels
        )
        return payload

    def compute_manifest_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "EvidenceInvalidationManifest":
        return replace(self, manifest_id=self.compute_manifest_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.manifest_id else self.with_id()
        payload = item.payload_without_id()
        payload["manifest_id"] = item.manifest_id
        return payload


def load_controller_revision(path: str | Path) -> ControllerRevisionManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    for name in (
        "natural_fix_ids",
        "natural_fix_test_ids",
        "fallback_allowed_scopes",
        "fallback_forbidden_scopes",
    ):
        payload[name] = tuple(payload.get(name, ()))
    return ControllerRevisionManifest(**payload)
