"""Blocked Round 5.13D readiness contracts before engineering-smoke approval."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any


BLOCK_REASON = "engineering_smoke_authorization_missing"


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


class _Hashed:
    _id_field: str

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop(self._id_field, None)
        return payload

    def compute_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self):
        return replace(self, **{self._id_field: self.compute_id()})

    def to_dict(self) -> dict[str, Any]:
        item = self if getattr(self, self._id_field) else self.with_id()
        return {**item.payload_without_id(), self._id_field: getattr(item, self._id_field)}


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeAudit(_Hashed):
    source_commit: str
    smoke_design_id: str
    authorization_id: str
    status: str = "not_run"
    block_reason: str = BLOCK_REASON
    executed: bool = False
    unit_count: int = 0
    resolved_units: int = 0
    duplicate_ids: int = 0
    memory_writes: int = 0
    acquisition_writes: int = 0
    holdout_final_accesses: int = 0
    formal_fitting_eligible_rows: int = 0
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.executed or self.unit_count or self.resolved_units:
            raise ValueError("Unapproved engineering smoke cannot contain units")
        if self.status != "not_run" or self.block_reason != BLOCK_REASON:
            raise ValueError("Unexpected pre-approval smoke status")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Smoke audit hash mismatch")


@dataclass(frozen=True)
class CHRMLiteBehaviorEquivalenceAudit(_Hashed):
    source_commit: str
    synthetic_test_count: int
    synthetic_passed: bool
    full_environment_import_test_count: int
    full_environment_import_passed: bool
    engineering_receipt_comparison_completed: bool = False
    status: str = "partial_blocked_pending_smoke"
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if not self.synthetic_passed or self.synthetic_test_count < 1:
            raise ValueError("Synthetic behavior equivalence has not passed")
        if self.engineering_receipt_comparison_completed:
            raise ValueError("Engineering receipt equivalence requires approved smoke")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Behavior equivalence audit hash mismatch")


@dataclass(frozen=True)
class CHRMLiteInstrumentationReleaseV4_1(_Hashed):
    source_commit: str
    record_schema_id: str
    behavior_equivalence_audit_id: str
    smoke_audit_id: str
    runtime_mode: str = "chrmlite_estimation_collection_v41"
    status: str = "blocked_pending_engineering_smoke"
    released_for_formal_collection: bool = False
    formal_campaign_started: bool = False
    schema_version: int = 1
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        if self.released_for_formal_collection or self.formal_campaign_started:
            raise ValueError("Blocked instrumentation opened formal collection")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("Instrumentation release hash mismatch")


@dataclass(frozen=True)
class CHRMLiteDataReadinessReport(_Hashed):
    source_commit: str
    instrumentation_release_id: str
    smoke_audit_id: str
    required_field_coverage: float = 0.0
    confidence_coverage: float = 0.0
    knowledge_coverage: float = 0.0
    environment_coverage: float = 0.0
    label_coverage: float = 0.0
    status: str = "BLOCKED"
    reason: str = BLOCK_REASON
    schema_version: int = 1
    report_id: str = ""

    _id_field = "report_id"

    def __post_init__(self) -> None:
        if self.status != "BLOCKED" or self.reason != BLOCK_REASON:
            raise ValueError("Unapproved smoke cannot be data-ready")
        if any(
            value != 0.0
            for value in (
                self.required_field_coverage,
                self.confidence_coverage,
                self.knowledge_coverage,
                self.environment_coverage,
                self.label_coverage,
            )
        ):
            raise ValueError("Unrun smoke coverage must not be fabricated")
        if self.report_id and self.report_id != self.compute_id():
            raise ValueError("Data readiness report hash mismatch")


@dataclass(frozen=True)
class Round513CDReadinessDecision(_Hashed):
    source_commit: str
    instrumentation_release_id: str
    data_readiness_report_id: str
    state: str = "BLOCKED"
    exact_reason: str = BLOCK_REASON
    formal_collection_authorized: bool = False
    cdt_parameters_estimated: bool = False
    holdout_or_final_accessed: bool = False
    schema_version: int = 1
    decision_id: str = ""

    _id_field = "decision_id"

    def __post_init__(self) -> None:
        if self.state != "BLOCKED" or self.exact_reason != BLOCK_REASON:
            raise ValueError("Pre-smoke readiness must remain blocked")
        if self.formal_collection_authorized or self.cdt_parameters_estimated:
            raise ValueError("Readiness decision opened a forbidden phase")
        if self.holdout_or_final_accessed:
            raise ValueError("Readiness decision records Holdout/final contamination")
        if self.decision_id and self.decision_id != self.compute_id():
            raise ValueError("Readiness decision hash mismatch")


def build_blocked_readiness(
    *,
    source_commit: str,
    smoke_design_id: str,
    authorization_id: str,
    record_schema_id: str,
    synthetic_test_count: int,
    full_environment_import_test_count: int,
    full_environment_import_passed: bool,
) -> tuple[Any, ...]:
    smoke = CHRMLiteEngineeringSmokeAudit(
        source_commit, smoke_design_id, authorization_id
    ).with_id()
    behavior = CHRMLiteBehaviorEquivalenceAudit(
        source_commit=source_commit,
        synthetic_test_count=synthetic_test_count,
        synthetic_passed=True,
        full_environment_import_test_count=full_environment_import_test_count,
        full_environment_import_passed=full_environment_import_passed,
    ).with_id()
    release = CHRMLiteInstrumentationReleaseV4_1(
        source_commit, record_schema_id, behavior.audit_id, smoke.audit_id
    ).with_id()
    report = CHRMLiteDataReadinessReport(
        source_commit, release.release_id, smoke.audit_id
    ).with_id()
    decision = Round513CDReadinessDecision(
        source_commit, release.release_id, report.report_id
    ).with_id()
    return release, smoke, behavior, report, decision
