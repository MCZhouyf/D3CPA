"""Superseding authorization gate for formal log-bootstrap acquisition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence

from .formal_log_bootstrap import FormalBootstrapRunReceipt
from .formal_bootstrap_amendment import (
    MODEL_IDENTITY_APPROVAL_SHA256,
    RECORD_ONLY_IDENTITY_POLICY,
)


SCHEMA_VERSION = 1
OLD_GATE_ID = (
    "27f2bc9cd18a33c21b68fbd6a85cfdf8e7560005c63319381c1debcaa9f34a4d"
)
AMENDMENT_BASELINE_COMMIT = "db8778ddcaf4655ee86cf50c9d0a9919a832d7d3"
ZYF_APPROVAL_SHA256 = (
    "02aa04d0bdf45d5e7dad1afb3f6ff295a687a91707c693e9d5dd9e1f040fffab"
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
class FormalBootstrapReadinessEvidence:
    readiness_campaign_id: str
    source_commit: str
    blueprint_id: str
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    run_receipt_ids: tuple[str, ...]
    expected_run_count: int
    pipeline_pass_count: int
    task_completed_count: int
    intervention_trigger_count: int
    total_injected_logs: int
    returned_model_identities: tuple[str, ...]
    returned_identity_stable_within_epoch: bool
    requested_returned_equality_required: bool
    model_epoch_id: str
    task_seed_match_count: int
    provider_call_contract_passed: bool
    no_formal_memory_writes: bool
    no_acquisition_writes: bool
    eligible: bool
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    evidence_id: str = ""

    def __post_init__(self) -> None:
        if self.expected_run_count <= 0:
            raise ValueError("Readiness campaign must contain runs")
        if len(self.run_receipt_ids) != self.expected_run_count:
            raise ValueError("Readiness receipt count mismatch")
        if self.requested_returned_equality_required:
            raise ValueError("Requested/returned identity equality is not required")
        if not self.returned_model_identities:
            raise ValueError("Returned model identity must be recorded")
        if self.eligible and self.errors:
            raise ValueError("Eligible readiness evidence cannot contain errors")
        expected = self.compute_evidence_id()
        if self.evidence_id and self.evidence_id != expected:
            raise ValueError("Formal bootstrap readiness hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("evidence_id", None)
        payload["run_receipt_ids"] = list(self.run_receipt_ids)
        payload["returned_model_identities"] = list(
            self.returned_model_identities
        )
        payload["errors"] = list(self.errors)
        return payload

    def compute_evidence_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalBootstrapReadinessEvidence":
        return replace(self, evidence_id=self.compute_evidence_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.evidence_id else self.with_id()
        payload = item.payload_without_id()
        payload["evidence_id"] = item.evidence_id
        return payload


@dataclass(frozen=True)
class FormalBootstrapAuthorization:
    authorization_name: str
    source_commit: str
    previous_preacquisition_gate_id: str
    previous_gate_superseded: bool
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    blueprint_id: str
    blueprint_validation_report_id: str
    taskset_release_id: str
    semantic_migration_report_id: str
    approval_binding_id: str
    readiness_evidence_id: str
    model_epoch_id: str
    acquisition_schedule_id: str
    acquisition_episode_count: int
    all_methods_share_policy: bool
    all_formal_phases_share_policy: bool
    memory_records_bootstrap_metadata: bool
    development_records_bootstrap_metadata: bool
    final_results_report_natural_and_assisted_separately: bool
    formal_acquisition_permitted: bool
    reasons: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    authorization_id: str = ""

    def __post_init__(self) -> None:
        if self.previous_preacquisition_gate_id != OLD_GATE_ID:
            raise ValueError("Unexpected superseded Pre-Acquisition gate")
        if not self.previous_gate_superseded:
            raise ValueError("Old Pre-Acquisition gate must be superseded")
        if self.acquisition_episode_count != 100:
            raise ValueError("Reference acquisition requires 100 episodes")
        if self.formal_acquisition_permitted and self.reasons:
            raise ValueError("Permitted authorization cannot contain reasons")
        expected = self.compute_authorization_id()
        if self.authorization_id and self.authorization_id != expected:
            raise ValueError("Formal bootstrap authorization hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("authorization_id", None)
        payload["reasons"] = list(self.reasons)
        return payload

    def compute_authorization_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalBootstrapAuthorization":
        return replace(self, authorization_id=self.compute_authorization_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.authorization_id else self.with_id()
        payload = item.payload_without_id()
        payload["authorization_id"] = item.authorization_id
        return payload


def audit_formal_bootstrap_authorization(
    *,
    source_commit: str,
    policy: Mapping[str, Any],
    amendment: Mapping[str, Any],
    blueprint_validation: Mapping[str, Any],
    approval_binding: Mapping[str, Any],
    taskset_release: Mapping[str, Any],
    migration_report: Mapping[str, Any],
    readiness: FormalBootstrapReadinessEvidence,
    acquisition_schedule: Mapping[str, Any],
) -> FormalBootstrapAuthorization:
    reasons: list[str] = []
    policy_id = str(policy.get("policy_id", ""))
    amendment_id = str(amendment.get("amendment_id", ""))
    blueprint_id = str(blueprint_validation.get("blueprint_id", ""))

    if not policy_id or not amendment_id or not blueprint_id:
        reasons.append("policy/amendment/Blueprint identity is incomplete")
    if amendment.get("formal_log_bootstrap_policy_id") != policy_id:
        reasons.append("amendment/bootstrap policy mismatch")
    if amendment.get("returned_model_identity_policy") == (
        RECORD_ONLY_IDENTITY_POLICY
    ) and approval_binding.get("model_identity_approval_sha256") != (
        MODEL_IDENTITY_APPROVAL_SHA256
    ):
        reasons.append("record-only identity approval mismatch")
    if amendment.get("source_commit") != AMENDMENT_BASELINE_COMMIT:
        reasons.append("amendment baseline commit mismatch")
    if not amendment.get("old_preacquisition_gate_superseded", False):
        reasons.append("old Pre-Acquisition gate was not superseded")
    if not blueprint_validation.get("eligible", False):
        reasons.append("Blueprint validation is ineligible")
    if approval_binding.get("blueprint_id") != blueprint_id:
        reasons.append("approval/Blueprint mismatch")
    if approval_binding.get("formal_log_bootstrap_policy_id") != policy_id:
        reasons.append("approval/bootstrap policy mismatch")
    if approval_binding.get("formal_bootstrap_amendment_id") != amendment_id:
        reasons.append("approval/bootstrap amendment mismatch")
    if approval_binding.get("source_commit") != source_commit:
        reasons.append("approval source commit mismatch")
    if approval_binding.get("zyf_approval_sha256") != ZYF_APPROVAL_SHA256:
        reasons.append("approval record SHA256 mismatch")
    if not taskset_release.get("eligible", False):
        reasons.append("final taskset release is ineligible")
    if not migration_report.get("eligible", False):
        reasons.append("semantic migration is ineligible")
    if not readiness.eligible:
        reasons.append("formal bootstrap readiness is ineligible")
    if readiness.source_commit != source_commit:
        reasons.append("readiness source commit mismatch")
    if readiness.blueprint_id != blueprint_id:
        reasons.append("readiness Blueprint mismatch")
    if readiness.bootstrap_policy_id != policy_id:
        reasons.append("readiness bootstrap policy mismatch")
    if readiness.bootstrap_amendment_id != amendment_id:
        reasons.append("readiness bootstrap amendment mismatch")
    if readiness.pipeline_pass_count != readiness.expected_run_count:
        reasons.append("readiness pipeline did not pass every run")
    if readiness.task_seed_match_count != readiness.expected_run_count:
        reasons.append("readiness task-seed binding is incomplete")
    if not readiness.provider_call_contract_passed:
        reasons.append("provider call contract failed")
    if not readiness.no_formal_memory_writes:
        reasons.append("readiness wrote formal memory")
    if not readiness.no_acquisition_writes:
        reasons.append("readiness wrote acquisition data")

    schedule_id = str(acquisition_schedule.get("schedule_id", ""))
    episode_count = int(acquisition_schedule.get("episode_count", 0) or 0)
    if episode_count != 100:
        reasons.append("formal acquisition schedule is not 100 episodes")
    if acquisition_schedule.get("bootstrap_policy_id") != policy_id:
        reasons.append("schedule/bootstrap policy mismatch")
    if acquisition_schedule.get("bootstrap_amendment_id") != amendment_id:
        reasons.append("schedule/bootstrap amendment mismatch")
    if acquisition_schedule.get("source_commit") != source_commit:
        reasons.append("schedule source commit mismatch")
    if acquisition_schedule.get("blueprint_id") != blueprint_id:
        reasons.append("schedule/Blueprint mismatch")

    uniform_methods = bool(
        acquisition_schedule.get("all_methods_share_policy", False)
    )
    uniform_phases = bool(policy.get("enabled_for_all_formal_scopes", False))
    memory_metadata = bool(
        acquisition_schedule.get("memory_records_bootstrap_metadata", False)
    )
    development_metadata = bool(
        approval_binding.get("development_records_bootstrap_metadata", False)
    )
    separate_reporting = bool(
        approval_binding.get(
            "final_results_report_natural_and_assisted_separately",
            False,
        )
    )
    if not uniform_methods:
        reasons.append("policy is not uniform across methods")
    if not uniform_phases:
        reasons.append("policy is not uniform across formal phases")
    if not memory_metadata:
        reasons.append("memory records do not bind bootstrap metadata")
    if not development_metadata:
        reasons.append("development records do not bind bootstrap metadata")
    if not separate_reporting:
        reasons.append("final result reporting does not separate completion classes")

    return FormalBootstrapAuthorization(
        authorization_name="dc3pa-formal-log-bootstrap-authorization-v1",
        source_commit=source_commit,
        previous_preacquisition_gate_id=OLD_GATE_ID,
        previous_gate_superseded=True,
        bootstrap_policy_id=policy_id,
        bootstrap_amendment_id=amendment_id,
        blueprint_id=blueprint_id,
        blueprint_validation_report_id=str(
            blueprint_validation.get("report_id", "")
        ),
        taskset_release_id=str(taskset_release.get("release_id", "")),
        semantic_migration_report_id=str(
            migration_report.get("report_id", "")
        ),
        approval_binding_id=str(approval_binding.get("binding_id", "")),
        readiness_evidence_id=readiness.evidence_id,
        model_epoch_id=readiness.model_epoch_id,
        acquisition_schedule_id=schedule_id,
        acquisition_episode_count=episode_count,
        all_methods_share_policy=uniform_methods,
        all_formal_phases_share_policy=uniform_phases,
        memory_records_bootstrap_metadata=memory_metadata,
        development_records_bootstrap_metadata=development_metadata,
        final_results_report_natural_and_assisted_separately=separate_reporting,
        formal_acquisition_permitted=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
    ).with_id()


def audit_formal_bootstrap_readiness(
    receipts: Sequence[Mapping[str, Any]],
    *,
    readiness_campaign_id: str,
    source_commit: str,
    blueprint_id: str,
    bootstrap_policy_id: str,
    bootstrap_amendment_id: str,
    model_epoch_id: str,
    expected_run_count: int = 6,
) -> FormalBootstrapReadinessEvidence:
    errors: list[str] = []
    receipt_ids: list[str] = []
    returned: set[str] = set()
    pipeline = completed = triggers = injected = task_seed_matches = 0
    provider_contract = True
    no_memory = True
    no_acquisition = True

    if len(receipts) != expected_run_count:
        errors.append(
            f"expected {expected_run_count} receipts, found {len(receipts)}"
        )

    seen_pairs: set[tuple[str, str]] = set()
    data_binding_ids: set[str] = set()
    for index, item in enumerate(receipts):
        label = f"receipt[{index}]"
        try:
            values = dict(item)
            values["returned_model_identities"] = tuple(
                values.get("returned_model_identities", ())
            )
            values["event_ids"] = tuple(values.get("event_ids", ()))
            FormalBootstrapRunReceipt(**values)
        except (TypeError, ValueError) as exc:
            errors.append(f"{label}: invalid immutable receipt: {exc}")
        receipt_id = str(item.get("receipt_id", ""))
        if not receipt_id:
            errors.append(f"{label}: receipt ID missing")
        receipt_ids.append(receipt_id)
        if item.get("scope") != "bootstrap_readiness_dry_run":
            errors.append(f"{label}: incorrect readiness scope")
        if item.get("readiness_campaign_id") != readiness_campaign_id:
            errors.append(f"{label}: readiness campaign mismatch")
        if item.get("source_commit") != source_commit:
            errors.append(f"{label}: source commit mismatch")
        if item.get("blueprint_id") != blueprint_id:
            errors.append(f"{label}: Blueprint mismatch")
        if item.get("policy_id") != bootstrap_policy_id:
            errors.append(f"{label}: policy mismatch")
        if item.get("bootstrap_amendment_id") != bootstrap_amendment_id:
            errors.append(f"{label}: amendment mismatch")
        binding_id = str(item.get("bootstrap_data_binding_id", ""))
        if not binding_id:
            errors.append(f"{label}: bootstrap data binding missing")
        else:
            data_binding_ids.add(binding_id)
        if bool(item.get("pipeline_pass", False)):
            pipeline += 1
        else:
            errors.append(f"{label}: pipeline did not pass")
        if bool(item.get("task_completed", False)):
            completed += 1
        triggers += int(item.get("intervention_trigger_count", 0) or 0)
        injected += int(item.get("total_injected_logs", 0) or 0)
        identities = item.get("returned_model_identities", ())
        if not isinstance(identities, Sequence) or isinstance(identities, str):
            errors.append(f"{label}: returned identities are malformed")
        else:
            returned.update(str(value) for value in identities if str(value))
        pair = (str(item.get("task", "")), str(item.get("seed", "")))
        if all(pair) and pair not in seen_pairs:
            seen_pairs.add(pair)
            task_seed_matches += 1
        else:
            errors.append(f"{label}: missing or duplicate task-seed")
        if not bool(item.get("provider_call_contract_passed", False)):
            provider_contract = False
            errors.append(f"{label}: provider call contract failed")
        if int(item.get("planner_calls", 0) or 0) != 1:
            errors.append(f"{label}: readiness requires one Planner call")
        if int(item.get("reflection_calls", 0) or 0) not in {0, 1}:
            errors.append(f"{label}: readiness permits at most one Reflection call")
        if int(item.get("evaluation_chain_calls", 0) or 0) != 0:
            errors.append(f"{label}: Evaluation Chain must be disabled")
        if int(item.get("controller_execution_count", 0) or 0) != 1:
            errors.append(f"{label}: readiness requires one Controller execution")
        if int(item.get("formal_memory_write_count", 0) or 0) != 0:
            no_memory = False
            errors.append(f"{label}: formal memory was written")
        if int(item.get("acquisition_write_count", 0) or 0) != 0:
            no_acquisition = False
            errors.append(f"{label}: acquisition data was written")

    if not returned:
        errors.append("no returned model identity was recorded")
    epoch_stable = len(returned) == 1
    if len(data_binding_ids) != 1:
        errors.append(
            f"readiness receipts mix bootstrap data bindings: {sorted(data_binding_ids)}"
        )

    return FormalBootstrapReadinessEvidence(
        readiness_campaign_id=readiness_campaign_id,
        source_commit=source_commit,
        blueprint_id=blueprint_id,
        bootstrap_policy_id=bootstrap_policy_id,
        bootstrap_amendment_id=bootstrap_amendment_id,
        run_receipt_ids=tuple(receipt_ids),
        expected_run_count=expected_run_count,
        pipeline_pass_count=pipeline,
        task_completed_count=completed,
        intervention_trigger_count=triggers,
        total_injected_logs=injected,
        returned_model_identities=tuple(sorted(returned)),
        returned_identity_stable_within_epoch=epoch_stable,
        requested_returned_equality_required=False,
        model_epoch_id=model_epoch_id,
        task_seed_match_count=task_seed_matches,
        provider_call_contract_passed=provider_contract,
        no_formal_memory_writes=no_memory,
        no_acquisition_writes=no_acquisition,
        eligible=not errors,
        errors=tuple(dict.fromkeys(errors)),
    ).with_id()
