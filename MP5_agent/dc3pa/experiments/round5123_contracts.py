"""Immutable contracts for the Round 5.12.3 mixed-runtime closeout."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
EXPECTED_UNITS = 60
EXPECTED_TRAIN_UNITS = 45
EXPECTED_TUNE_UNITS = 15
EXPECTED_SUCCESS = 36
EXPECTED_SCIENTIFIC_FAILURE = 24
EXPECTED_TRAIN_RECORDS = 528
EXPECTED_TUNE_RECORDS = 153
EXPECTED_RECORDS = 681

FORBIDDEN_FUSION_FEATURES = frozenset(
    {
        "runtime_segment",
        "runtime_segment_id",
        "controller_identity",
        "controller_version",
        "source_commit",
        "execution_budget",
        "max_explore_steps",
        "episode_timeout_seconds",
        "task",
        "difficulty",
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


def _required(value: str, label: str) -> None:
    if not str(value).strip():
        raise ValueError(f"{label} is required")


@dataclass(frozen=True)
class AcceptedUnitBinding:
    unit_id: str
    role: str
    task: str
    seed: str
    run_id: str
    status: str
    frozen_order_index: int
    legacy_sequence_index: int
    decision_record_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.unit_id, "unit_id"),
            (self.task, "task"),
            (self.seed, "seed"),
            (self.run_id, "run_id"),
        ):
            _required(value, label)
        if self.role not in {"dev_train", "dev_tune"}:
            raise ValueError("accepted unit role must be dev_train or dev_tune")
        if self.status not in {
            "completed_success",
            "completed_scientific_failure",
        }:
            raise ValueError("accepted unit must have a scientific outcome")
        if self.frozen_order_index < 0 or self.legacy_sequence_index < 0:
            raise ValueError("accepted unit order indices must be nonnegative")
        if not self.decision_record_ids:
            raise ValueError("accepted unit has no decision records")
        if len(set(self.decision_record_ids)) != len(self.decision_record_ids):
            raise ValueError("accepted unit has duplicate decision record IDs")

    @property
    def task_completed(self) -> bool:
        return self.status == "completed_success"


@dataclass(frozen=True)
class RuntimeSegment:
    source_commit: str
    controller_identity_sha256: str
    controller_component_sha256: Mapping[str, str]
    evaluator_identity_sha256: str
    prompt_hash_bundle_id: str
    paper_memory_v5_release_id: str
    paper_memory_snapshot_root_sha256: str
    active_taskset_release_id: str
    formal_log_bootstrap_policy_id: str
    execution_budget_profile_id: str
    execution_budget_profile: Mapping[str, Any]
    accepted_units: tuple[AcceptedUnitBinding, ...]
    runtime_segment_is_predictive_feature: bool = False
    schema_version: int = SCHEMA_VERSION
    segment_id: str = ""

    def __post_init__(self) -> None:
        for value, label in (
            (self.source_commit, "source_commit"),
            (self.controller_identity_sha256, "controller identity"),
            (self.evaluator_identity_sha256, "evaluator identity"),
            (self.prompt_hash_bundle_id, "prompt hash bundle"),
            (self.paper_memory_v5_release_id, "Paper Memory V5 release"),
            (self.paper_memory_snapshot_root_sha256, "Paper Memory V5 root"),
            (self.active_taskset_release_id, "active taskset release"),
            (self.formal_log_bootstrap_policy_id, "Log Bootstrap policy"),
            (self.execution_budget_profile_id, "execution budget profile"),
        ):
            _required(value, label)
        if not self.controller_component_sha256:
            raise ValueError("Controller component hashes are required")
        if not self.execution_budget_profile:
            raise ValueError("complete execution budget profile is required")
        if str(self.execution_budget_profile.get("snapshot_id", "")) != (
            self.execution_budget_profile_id
        ):
            raise ValueError("execution budget profile ID mismatch")
        if self.runtime_segment_is_predictive_feature:
            raise ValueError("runtime segment may only be audit metadata")
        if not self.accepted_units:
            raise ValueError("runtime segment is empty")
        unit_ids = [item.unit_id for item in self.accepted_units]
        record_ids = [
            record_id
            for item in self.accepted_units
            for record_id in item.decision_record_ids
        ]
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("runtime segment has duplicate unit IDs")
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("runtime segment has duplicate decision record IDs")
        expected = self.compute_segment_id()
        if self.segment_id and self.segment_id != expected:
            raise ValueError("runtime segment hash mismatch")

    @property
    def ordered_units(self) -> tuple[AcceptedUnitBinding, ...]:
        return tuple(sorted(self.accepted_units, key=lambda item: item.frozen_order_index))

    @property
    def record_ids(self) -> tuple[str, ...]:
        return tuple(
            record_id
            for item in self.accepted_units
            for record_id in item.decision_record_ids
        )

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("segment_id", None)
        payload["controller_component_sha256"] = dict(
            sorted(self.controller_component_sha256.items())
        )
        payload["execution_budget_profile"] = dict(self.execution_budget_profile)
        payload["accepted_units"] = [asdict(item) for item in self.ordered_units]
        payload["first_accepted_unit"] = self.ordered_units[0].unit_id
        payload["last_accepted_unit"] = self.ordered_units[-1].unit_id
        payload["train_unit_count"] = sum(
            item.role == "dev_train" for item in self.accepted_units
        )
        payload["tune_unit_count"] = sum(
            item.role == "dev_tune" for item in self.accepted_units
        )
        payload["train_decision_record_count"] = sum(
            len(item.decision_record_ids)
            for item in self.accepted_units
            if item.role == "dev_train"
        )
        payload["tune_decision_record_count"] = sum(
            len(item.decision_record_ids)
            for item in self.accepted_units
            if item.role == "dev_tune"
        )
        payload["task_success_count"] = sum(
            item.task_completed for item in self.accepted_units
        )
        payload["scientific_failure_count"] = sum(
            not item.task_completed for item in self.accepted_units
        )
        return payload

    def compute_segment_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "RuntimeSegment":
        return replace(self, segment_id=self.compute_segment_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.segment_id else self.with_id()
        payload = item.payload_without_id()
        payload["segment_id"] = item.segment_id
        return payload


@dataclass(frozen=True)
class ResumedReplacementLineage:
    assignment_id: str
    task: str
    seed: str
    group_id: str
    role: str
    old_failed_attempt_ids: tuple[str, ...]
    old_failed_attempt_sha256: tuple[str, ...]
    replacement_attempt_id: str
    replacement_attempt_sha256: str
    replacement_reason: str
    authorization_id: str
    old_decision_row_count: int
    old_rows_in_accepted_data: int
    replacement_decision_row_count: int
    accepted_final_attempt_count: int
    final_status: str
    schema_version: int = SCHEMA_VERSION
    lineage_id: str = ""

    def __post_init__(self) -> None:
        if self.role not in {"dev_train", "dev_tune"}:
            raise ValueError("replacement lineage role is invalid")
        if not self.old_failed_attempt_ids:
            raise ValueError("replacement lineage has no old failed attempt")
        if len(self.old_failed_attempt_ids) != len(self.old_failed_attempt_sha256):
            raise ValueError("old failed attempt IDs/hashes are mismatched")
        if self.old_decision_row_count <= 0:
            raise ValueError("old failed attempt has no decision rows")
        if self.old_rows_in_accepted_data != 0:
            raise ValueError("old failed decision rows contaminated accepted data")
        if self.replacement_decision_row_count <= 0:
            raise ValueError("replacement attempt has no decision rows")
        if self.accepted_final_attempt_count != 1:
            raise ValueError("assignment must have exactly one accepted final attempt")
        if self.final_status != "completed_success":
            raise ValueError("the resumed replacement must be successful")
        for value, label in (
            (self.assignment_id, "assignment_id"),
            (self.replacement_attempt_id, "replacement attempt"),
            (self.replacement_attempt_sha256, "replacement attempt hash"),
            (self.replacement_reason, "replacement reason"),
            (self.authorization_id, "replacement authorization"),
        ):
            _required(value, label)
        expected = self.compute_lineage_id()
        if self.lineage_id and self.lineage_id != expected:
            raise ValueError("replacement lineage hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("lineage_id", None)
        payload["old_failed_attempt_ids"] = list(self.old_failed_attempt_ids)
        payload["old_failed_attempt_sha256"] = list(
            self.old_failed_attempt_sha256
        )
        return payload

    def compute_lineage_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "ResumedReplacementLineage":
        return replace(self, lineage_id=self.compute_lineage_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.lineage_id else self.with_id()
        payload = item.payload_without_id()
        payload["lineage_id"] = item.lineage_id
        return payload


@dataclass(frozen=True)
class RuntimeSegmentManifest:
    round5122_result_sha: str
    assignment_manifest_id: str
    effective_campaign_status_sha256: str
    effective_train_jsonl_sha256: str
    effective_tune_jsonl_sha256: str
    paper_memory_v5_release_id: str
    active_taskset_release_id: str
    segments: tuple[RuntimeSegment, ...]
    replacement_lineage: ResumedReplacementLineage
    failed_attempt_decision_contamination: int
    duplicate_accepted_decision_ids: int
    formal_memory_writes: int
    acquisition_store_writes: int
    evaluation_chain_calls: int
    holdout_final_contamination: int
    mine_sand_records: int
    legacy_receipt_source_mismatch_count: int
    legacy_receipt_source_commits: tuple[str, ...]
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    manifest_id: str = ""

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("runtime segment manifest is empty")
        normalized = tuple(
            item if item.segment_id else item.with_id() for item in self.segments
        )
        unit_ids = [
            unit.unit_id for segment in normalized for unit in segment.accepted_units
        ]
        record_ids = [
            record_id for segment in normalized for record_id in segment.record_ids
        ]
        train_units = sum(
            unit.role == "dev_train"
            for segment in normalized
            for unit in segment.accepted_units
        )
        tune_units = len(unit_ids) - train_units
        train_records = sum(
            len(unit.decision_record_ids)
            for segment in normalized
            for unit in segment.accepted_units
            if unit.role == "dev_train"
        )
        tune_records = len(record_ids) - train_records
        successes = sum(
            unit.task_completed
            for segment in normalized
            for unit in segment.accepted_units
        )
        failures = len(unit_ids) - successes
        observed = {
            "units": len(unit_ids),
            "train_units": train_units,
            "tune_units": tune_units,
            "successes": successes,
            "scientific_failures": failures,
            "train_records": train_records,
            "tune_records": tune_records,
            "records": len(record_ids),
        }
        expected = {
            "units": EXPECTED_UNITS,
            "train_units": EXPECTED_TRAIN_UNITS,
            "tune_units": EXPECTED_TUNE_UNITS,
            "successes": EXPECTED_SUCCESS,
            "scientific_failures": EXPECTED_SCIENTIFIC_FAILURE,
            "train_records": EXPECTED_TRAIN_RECORDS,
            "tune_records": EXPECTED_TUNE_RECORDS,
            "records": EXPECTED_RECORDS,
        }
        if observed != expected:
            raise ValueError(
                f"Round 5.12.3 accounting mismatch: {observed} != {expected}"
            )
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("accepted unit belongs to more than one segment")
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("accepted record belongs to more than one segment")
        lineage_units = [
            unit
            for segment in normalized
            for unit in segment.accepted_units
            if unit.unit_id == self.replacement_lineage.assignment_id
        ]
        if len(lineage_units) != 1 or not lineage_units[0].task_completed:
            raise ValueError("replacement lineage does not resolve to one final success")
        protected = (
            self.failed_attempt_decision_contamination,
            self.duplicate_accepted_decision_ids,
            self.formal_memory_writes,
            self.acquisition_store_writes,
            self.evaluation_chain_calls,
            self.holdout_final_contamination,
            self.mine_sand_records,
        )
        if any(protected):
            raise ValueError("protected-data invariant failed")
        if not self.legacy_receipt_source_commits:
            raise ValueError("legacy receipt source audit is missing")
        if self.errors or not self.eligible:
            raise ValueError("cannot freeze an ineligible runtime segment manifest")
        expected_id = self.compute_manifest_id(normalized)
        if self.manifest_id and self.manifest_id != expected_id:
            raise ValueError("runtime segment manifest hash mismatch")

    def payload_without_id(
        self, segments: Sequence[RuntimeSegment] | None = None
    ) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("manifest_id", None)
        selected = segments or self.segments
        payload["segments"] = [
            item.to_dict()
            for item in sorted(
                selected,
                key=lambda value: min(
                    unit.frozen_order_index for unit in value.accepted_units
                ),
            )
        ]
        payload["replacement_lineage"] = self.replacement_lineage.to_dict()
        payload["legacy_receipt_source_commits"] = list(
            self.legacy_receipt_source_commits
        )
        payload["errors"] = list(self.errors)
        payload["warnings"] = list(self.warnings)
        payload["resolved_unit_count"] = EXPECTED_UNITS
        payload["accepted_decision_record_count"] = EXPECTED_RECORDS
        return payload

    def compute_manifest_id(
        self, segments: Sequence[RuntimeSegment] | None = None
    ) -> str:
        return _sha(self.payload_without_id(segments))

    def with_id(self) -> "RuntimeSegmentManifest":
        normalized = tuple(
            item if item.segment_id else item.with_id() for item in self.segments
        )
        item = replace(
            self,
            segments=normalized,
            replacement_lineage=(
                self.replacement_lineage
                if self.replacement_lineage.lineage_id
                else self.replacement_lineage.with_id()
            ),
        )
        return replace(item, manifest_id=item.compute_manifest_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.manifest_id else self.with_id()
        payload = item.payload_without_id()
        payload["manifest_id"] = item.manifest_id
        return payload


@dataclass(frozen=True)
class MixedRuntimeDevelopmentAmendment:
    amendment_name: str
    runtime_segment_manifest_id: str
    status: str
    controller_changes_accepted: bool
    budget_relaxations_accepted: bool
    all_final_units_and_records_accepted: bool
    no_outcome_selective_exclusions: bool
    no_unit_removed_by_outcome: bool
    runtime_segment_is_audit_metadata_only: bool
    descriptive_success_rate_is_not_homogeneous_benchmark: bool
    holdout_uses_one_frozen_final_runtime: bool
    no_runtime_change_after_candidate_freeze: bool
    approved_by: str = ""
    approved_at: str = ""
    approval_statement: str = ""
    schema_version: int = SCHEMA_VERSION
    amendment_id: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"DRAFT", "APPROVED"}:
            raise ValueError("amendment status must be DRAFT or APPROVED")
        required_statements = (
            self.controller_changes_accepted,
            self.budget_relaxations_accepted,
            self.all_final_units_and_records_accepted,
            self.no_outcome_selective_exclusions,
            self.no_unit_removed_by_outcome,
            self.runtime_segment_is_audit_metadata_only,
            self.descriptive_success_rate_is_not_homogeneous_benchmark,
            self.holdout_uses_one_frozen_final_runtime,
            self.no_runtime_change_after_candidate_freeze,
        )
        if not all(required_statements):
            raise ValueError("mixed-runtime amendment is missing a required statement")
        if self.status == "APPROVED":
            for value, label in (
                (self.approved_by, "approved_by"),
                (self.approved_at, "approved_at"),
                (self.approval_statement, "approval_statement"),
            ):
                _required(value, label)
        elif any((self.approved_by, self.approved_at, self.approval_statement)):
            raise ValueError("DRAFT amendment cannot contain approval evidence")
        expected = self.compute_amendment_id()
        if self.amendment_id and self.amendment_id != expected:
            raise ValueError("mixed-runtime amendment hash mismatch")

    @property
    def author_approved(self) -> bool:
        return self.status == "APPROVED"

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("amendment_id", None)
        return payload

    def compute_amendment_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "MixedRuntimeDevelopmentAmendment":
        return replace(self, amendment_id=self.compute_amendment_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.amendment_id else self.with_id()
        payload = item.payload_without_id()
        payload["amendment_id"] = item.amendment_id
        return payload


@dataclass(frozen=True)
class AmendedDevelopmentDatasetAcceptance:
    runtime_segment_manifest_id: str
    mixed_runtime_amendment_id: str
    author_approved: bool
    accepted_unit_count: int
    accepted_decision_record_count: int
    runtime_segment_is_predictive_feature: bool
    holdout_opened: bool
    fusion_fitted: bool
    final_evaluation_opened: bool
    eligible: bool
    schema_version: int = SCHEMA_VERSION
    acceptance_id: str = ""

    def __post_init__(self) -> None:
        if not self.author_approved:
            raise ValueError("author approval is required before dataset acceptance")
        if self.accepted_unit_count != EXPECTED_UNITS:
            raise ValueError("dataset acceptance must retain all 60 units")
        if self.accepted_decision_record_count != EXPECTED_RECORDS:
            raise ValueError("dataset acceptance must retain all 681 records")
        if self.runtime_segment_is_predictive_feature:
            raise ValueError("runtime segment cannot be a predictive feature")
        if self.holdout_opened or self.fusion_fitted or self.final_evaluation_opened:
            raise ValueError("dataset acceptance crossed a protected phase boundary")
        if not self.eligible:
            raise ValueError("cannot freeze an ineligible dataset acceptance")
        expected = self.compute_acceptance_id()
        if self.acceptance_id and self.acceptance_id != expected:
            raise ValueError("dataset acceptance hash mismatch")

    @classmethod
    def from_approved_amendment(
        cls,
        *,
        manifest: RuntimeSegmentManifest,
        amendment: MixedRuntimeDevelopmentAmendment,
    ) -> "AmendedDevelopmentDatasetAcceptance":
        if not amendment.author_approved:
            raise ValueError("author amendment remains DRAFT")
        if amendment.runtime_segment_manifest_id != manifest.manifest_id:
            raise ValueError("amendment and runtime manifest IDs differ")
        return cls(
            runtime_segment_manifest_id=manifest.manifest_id,
            mixed_runtime_amendment_id=amendment.amendment_id,
            author_approved=True,
            accepted_unit_count=EXPECTED_UNITS,
            accepted_decision_record_count=EXPECTED_RECORDS,
            runtime_segment_is_predictive_feature=False,
            holdout_opened=False,
            fusion_fitted=False,
            final_evaluation_opened=False,
            eligible=True,
        ).with_id()

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("acceptance_id", None)
        return payload

    def compute_acceptance_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "AmendedDevelopmentDatasetAcceptance":
        return replace(self, acceptance_id=self.compute_acceptance_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.acceptance_id else self.with_id()
        payload = item.payload_without_id()
        payload["acceptance_id"] = item.acceptance_id
        return payload


def assert_fusion_feature_names(feature_names: Sequence[str]) -> None:
    overlap = FORBIDDEN_FUSION_FEATURES.intersection(feature_names)
    if overlap:
        raise ValueError(
            f"runtime/task metadata cannot be Fusion features: {sorted(overlap)}"
        )
