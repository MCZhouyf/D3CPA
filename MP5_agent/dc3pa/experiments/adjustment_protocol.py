"""Immutable registry for train/tune-only adjustments before holdout lock."""

from __future__ import annotations
import hashlib, json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping

SCHEMA_VERSION = 1
ALLOWED = frozenset({
    "environment_selection_within_preregistered_grid",
    "confidence_calibration",
    "fusion_regularization",
    "uniform_data_extension",
    "runtime_bugfix_no_outcome_selection",
})
PROTECTED = frozenset({
    "final_task_catalog", "covered_heldout_status", "final_seeds",
    "split_or_seed_salts", "activation_noninferiority_margins",
    "locked_holdout_data_or_labels", "final_test_data_or_labels",
})
EVIDENCE_ROLES = frozenset({"dev_train", "dev_tune"})


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class AdjustmentRecord:
    adjustment_name: str
    component: str
    blueprint_id_before: str
    source_commit_before: str
    evidence_roles: tuple[str, ...]
    evidence_artifact_sha256: tuple[str, ...]
    previous_value: Mapping[str, Any]
    proposed_value: Mapping[str, Any]
    rationale: str
    holdout_lock_exists: bool
    final_evaluation_started: bool
    within_preregistered_space: bool
    requires_new_blueprint_approval: bool
    author_approval_record_id: str = ""
    schema_version: int = SCHEMA_VERSION
    adjustment_id: str = ""

    def __post_init__(self):
        if self.component in PROTECTED:
            raise ValueError(f"Protected component: {self.component}")
        if self.component not in ALLOWED:
            raise ValueError(f"Unsupported adjustment: {self.component}")
        if self.holdout_lock_exists or self.final_evaluation_started:
            raise ValueError("Adjustment is too late")
        roles = set(self.evidence_roles)
        if not roles or not roles <= EVIDENCE_ROLES:
            raise ValueError("Only dev_train/dev_tune evidence is allowed")
        if not self.evidence_artifact_sha256:
            raise ValueError("Evidence hashes are required")
        if not self.rationale.strip():
            raise ValueError("Rationale is required")
        if self.component == "environment_selection_within_preregistered_grid" and (
            not self.within_preregistered_space
        ):
            raise ValueError("Environment choice is outside frozen grid")
        if self.requires_new_blueprint_approval and (
            not self.author_approval_record_id
        ):
            raise ValueError("New Blueprint approval is required")
        expected = self.compute_id()
        if self.adjustment_id and self.adjustment_id != expected:
            raise ValueError("Adjustment hash mismatch")

    def payload(self):
        value = asdict(self)
        value.pop("adjustment_id", None)
        value["evidence_roles"] = list(self.evidence_roles)
        value["evidence_artifact_sha256"] = list(self.evidence_artifact_sha256)
        value["previous_value"] = dict(self.previous_value)
        value["proposed_value"] = dict(self.proposed_value)
        return value

    def compute_id(self):
        return hashlib.sha256(canonical(self.payload())).hexdigest()

    def with_id(self):
        return replace(self, adjustment_id=self.compute_id())

    def to_dict(self):
        value = self.payload()
        value["adjustment_id"] = self.adjustment_id or self.compute_id()
        return value
