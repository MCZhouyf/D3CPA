"""Author-approved amendment for the formal planning-focused bootstrap condition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
EXPECTED_AUTHOR = "ZYF"
EXPECTED_MODEL = "gpt-5.1"
STABLE_IDENTITY_POLICY = "record_and_require_epoch_stability"
RECORD_ONLY_IDENTITY_POLICY = "record_only_no_stability_requirement"
MODEL_IDENTITY_APPROVAL_SHA256 = (
    "26ec20eb43aab76a8a9ba61a5072f11d24f1a2981a698acd68edf3b56583f6d0"
)
EXPECTED_PREVIOUS_GATE_ID = (
    "27f2bc9cd18a33c21b68fbd6a85cfdf8e7560005c63319381c1debcaa9f34a4d"
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
class FormalBootstrapAmendment:
    amendment_name: str
    approval_record_id: str
    approved_by: str
    approval_effective_date: str
    source_commit: str
    previous_preacquisition_gate_id: str
    previous_phase: str
    formal_acquisition_started_before_amendment: bool
    model_requested_alias: str
    returned_model_identity_policy: str
    returned_identity_must_be_recorded: bool
    returned_identity_must_be_stable_within_epoch: bool
    requested_returned_equality_required: bool
    formal_log_bootstrap_policy_id: str
    benchmark_condition_name: str
    benchmark_claim: str
    applies_to_all_formal_methods: bool
    applies_to_all_formal_scopes: bool
    applies_to_memory_acquisition: bool
    applies_to_development_collection: bool
    applies_to_final_evaluation: bool
    old_preacquisition_gate_superseded: bool
    old_readiness_evidence_reusable: bool
    old_natural_results_reclassified_as_diagnostic: bool
    prompts_changed: bool
    controller_success_logic_changed: bool
    evaluator_success_logic_changed: bool
    task_catalog_changed: bool
    final_seeds_changed: bool
    holdout_opened: bool
    author_statement: tuple[str, ...]
    model_identity_approval_sha256: str = ""
    schema_version: int = SCHEMA_VERSION
    amendment_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported formal-bootstrap amendment schema")
        required = (
            self.amendment_name,
            self.approval_record_id,
            self.approved_by,
            self.approval_effective_date,
            self.source_commit,
            self.previous_preacquisition_gate_id,
            self.formal_log_bootstrap_policy_id,
            self.benchmark_condition_name,
            self.benchmark_claim,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Formal-bootstrap amendment identity is incomplete")
        if self.approved_by != EXPECTED_AUTHOR:
            raise ValueError("Formal-bootstrap amendment must be approved by ZYF")
        if self.previous_preacquisition_gate_id != EXPECTED_PREVIOUS_GATE_ID:
            raise ValueError("Unexpected previous Pre-Acquisition gate ID")
        if self.previous_phase != "dry_run_completed":
            raise ValueError("Amendment must supersede dry_run_completed evidence")
        if self.formal_acquisition_started_before_amendment:
            raise ValueError("Formal bootstrap cannot be introduced after acquisition")
        if self.model_requested_alias != EXPECTED_MODEL:
            raise ValueError("Requested model alias must remain gpt-5.1")
        if self.returned_model_identity_policy not in {
            STABLE_IDENTITY_POLICY,
            RECORD_ONLY_IDENTITY_POLICY,
        }:
            raise ValueError("Unexpected returned-model identity policy")
        if not self.returned_identity_must_be_recorded:
            raise ValueError("Returned model identity must be recorded")
        if self.returned_model_identity_policy == STABLE_IDENTITY_POLICY:
            if not self.returned_identity_must_be_stable_within_epoch:
                raise ValueError("Stable identity policy requires epoch stability")
        elif self.returned_identity_must_be_stable_within_epoch:
            raise ValueError("Record-only identity policy must waive epoch stability")
        elif self.model_identity_approval_sha256 != (
            MODEL_IDENTITY_APPROVAL_SHA256
        ):
            raise ValueError("Record-only identity approval SHA256 mismatch")
        if self.requested_returned_equality_required:
            raise ValueError("Requested/returned equality is no longer required")
        if not all(
            (
                self.applies_to_all_formal_methods,
                self.applies_to_all_formal_scopes,
                self.applies_to_memory_acquisition,
                self.applies_to_development_collection,
                self.applies_to_final_evaluation,
                self.old_preacquisition_gate_superseded,
                self.old_natural_results_reclassified_as_diagnostic,
            )
        ):
            raise ValueError("Formal-bootstrap scope or supersession is incomplete")
        if self.old_readiness_evidence_reusable:
            raise ValueError("Old readiness evidence cannot authorize the new condition")
        if any(
            (
                self.prompts_changed,
                self.controller_success_logic_changed,
                self.evaluator_success_logic_changed,
                self.task_catalog_changed,
                self.final_seeds_changed,
                self.holdout_opened,
            )
        ):
            raise ValueError("Formal-bootstrap amendment changes protected content")
        if not self.author_statement:
            raise ValueError("Author statement is required")
        expected = self.compute_amendment_id()
        if self.amendment_id and self.amendment_id != expected:
            raise ValueError("Formal-bootstrap amendment hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("amendment_id", None)
        payload["author_statement"] = list(self.author_statement)
        return payload

    def compute_amendment_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalBootstrapAmendment":
        return replace(self, amendment_id=self.compute_amendment_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.amendment_id else self.with_id()
        payload = item.payload_without_id()
        payload["amendment_id"] = item.amendment_id
        return payload


def load_formal_bootstrap_amendment(
    path: str | Path,
) -> FormalBootstrapAmendment:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Formal bootstrap amendment must be a JSON object")
    values = dict(payload)
    values["author_statement"] = tuple(values.get("author_statement", ()))
    amendment = FormalBootstrapAmendment(**values)
    if not amendment.amendment_id:
        raise ValueError("Formal bootstrap amendment must be frozen")
    return amendment
