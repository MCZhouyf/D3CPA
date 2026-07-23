"""Contracts for retiring Round 5.12.6 before holdout assignment generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping


SCHEMA_VERSION = 1
SUPERSESSION_STATUS = "superseded_before_assignment_generation"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


class _HashedContract:
    _id_field: str

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop(self._id_field, None)
        return payload

    def compute_id(self) -> str:
        return _sha(self.payload_without_id())

    def to_dict(self) -> dict[str, Any]:
        identifier = getattr(self, self._id_field)
        item = self if identifier else replace(self, **{self._id_field: self.compute_id()})
        payload = item.payload_without_id()
        payload[self._id_field] = getattr(item, self._id_field)
        return payload


@dataclass(frozen=True)
class Round5126SupersessionDecision(_HashedContract):
    source_sha: str
    pending_authorization_input_id: str
    invalidation_receipt_id: str
    status: str = SUPERSESSION_STATUS
    scientific_holdout_consumed: bool = False
    holdout_outcomes_observed: bool = False
    old_authorization_reusable: bool = False
    old_salt_namespace_reusable: bool = False
    old_preauthorization_objects_preserved: bool = True
    old_authorization_approved: bool = False
    old_assignments_generated: bool = False
    old_ledger_created: bool = False
    old_bundle_read: bool = False
    old_bundle_decrypted: bool = False
    old_minedojo_holdout_started: bool = False
    final_evaluation_open: bool = False
    round6_open: bool = False
    schema_version: int = SCHEMA_VERSION
    decision_id: str = ""

    _id_field = "decision_id"

    def __post_init__(self) -> None:
        if not all(
            (self.source_sha, self.pending_authorization_input_id, self.invalidation_receipt_id)
        ):
            raise ValueError("Supersession identity is incomplete")
        if self.status != SUPERSESSION_STATUS:
            raise ValueError("Old holdout was not superseded before assignment generation")
        forbidden_true = (
            self.scientific_holdout_consumed,
            self.holdout_outcomes_observed,
            self.old_authorization_reusable,
            self.old_salt_namespace_reusable,
            self.old_authorization_approved,
            self.old_assignments_generated,
            self.old_ledger_created,
            self.old_bundle_read,
            self.old_bundle_decrypted,
            self.old_minedojo_holdout_started,
            self.final_evaluation_open,
            self.round6_open,
        )
        if any(forbidden_true) or not self.old_preauthorization_objects_preserved:
            raise ValueError("Supersession would consume, reopen, or discard frozen state")
        if self.decision_id and self.decision_id != self.compute_id():
            raise ValueError("Supersession decision hash mismatch")

    def with_id(self) -> "Round5126SupersessionDecision":
        return replace(self, decision_id=self.compute_id())


@dataclass(frozen=True)
class RetiredAuthorizationRegistry(_HashedContract):
    source_sha: str
    pending_authorization_input_id: str
    pending_authorization_input_sha256: str
    salt_commitment_sha256: str
    namespace_id: str
    preflight_binding_id: str
    preflight_binding_sha256: str
    runtime_release_id: str
    runtime_release_sha256: str
    exclusion_registry_id: str
    exclusion_registry_sha256: str
    invalidation_receipt_id: str
    supersession_decision_id: str
    authorization_status: str = "retired_invalidated"
    authorization_reusable: bool = False
    salt_namespace_reusable: bool = False
    old_files_preserved: bool = True
    schema_version: int = SCHEMA_VERSION
    registry_id: str = ""

    _id_field = "registry_id"

    def __post_init__(self) -> None:
        identities = (
            self.source_sha,
            self.pending_authorization_input_id,
            self.pending_authorization_input_sha256,
            self.salt_commitment_sha256,
            self.namespace_id,
            self.preflight_binding_id,
            self.preflight_binding_sha256,
            self.runtime_release_id,
            self.runtime_release_sha256,
            self.exclusion_registry_id,
            self.exclusion_registry_sha256,
            self.invalidation_receipt_id,
            self.supersession_decision_id,
        )
        if not all(identities):
            raise ValueError("Retired authorization registry is incomplete")
        if self.authorization_status != "retired_invalidated":
            raise ValueError("Retired authorization has an invalid status")
        if self.authorization_reusable or self.salt_namespace_reusable:
            raise ValueError("Retired authorization material cannot be reused")
        if not self.old_files_preserved:
            raise ValueError("Retirement must preserve all old files")
        if self.registry_id and self.registry_id != self.compute_id():
            raise ValueError("Retired authorization registry hash mismatch")

    def with_id(self) -> "RetiredAuthorizationRegistry":
        return replace(self, registry_id=self.compute_id())


@dataclass(frozen=True)
class OldMonotonicLogisticBaselineRelease(_HashedContract):
    release_name: str
    retired_from_source_sha: str
    model_source_commit: str
    feature_schema_id: str
    feature_schema_sha256: str
    feature_order: tuple[str, ...]
    coefficients: Mapping[str, float]
    intercept: float
    selected_l2: float
    selected_checkpoint: int
    confidence_release_id: str
    confidence_release_sha256: str
    environment_release_id: str
    environment_release_sha256: str
    paper_memory_v5_release_id: str
    paper_memory_v5_root_sha256: str
    development_train_sha256: str
    development_tune_sha256: str
    fusion_train_sha256: str
    fusion_tune_sha256: str
    activation_policy_id: str
    activation_policy_sha256: str
    comparison_only: bool = True
    fitting_reopened: bool = False
    holdout_used: bool = False
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        identities = (
            self.release_name,
            self.retired_from_source_sha,
            self.model_source_commit,
            self.feature_schema_id,
            self.feature_schema_sha256,
            self.confidence_release_id,
            self.confidence_release_sha256,
            self.environment_release_id,
            self.environment_release_sha256,
            self.paper_memory_v5_release_id,
            self.paper_memory_v5_root_sha256,
            self.development_train_sha256,
            self.development_tune_sha256,
            self.fusion_train_sha256,
            self.fusion_tune_sha256,
            self.activation_policy_id,
            self.activation_policy_sha256,
        )
        if not all(identities):
            raise ValueError("Old Logistic baseline release is incomplete")
        if not self.feature_order or set(self.feature_order) != set(self.coefficients):
            raise ValueError("Old Logistic coefficient schema mismatch")
        if self.selected_l2 < 0 or self.selected_checkpoint <= 0:
            raise ValueError("Old Logistic checkpoint is invalid")
        if not self.comparison_only or self.fitting_reopened or self.holdout_used:
            raise ValueError("Old Logistic may only be retained as a frozen baseline")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("Old Logistic baseline release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["feature_order"] = list(self.feature_order)
        payload["coefficients"] = dict(sorted(self.coefficients.items()))
        return payload

    def with_id(self) -> "OldMonotonicLogisticBaselineRelease":
        return replace(self, release_id=self.compute_id())
