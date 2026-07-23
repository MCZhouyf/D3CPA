"""Round 5.13E2H runtime-source hardening contracts.

These contracts adapt already-frozen scientific objects for execution.  They
do not change the V4.1.2 method, select retry budgets, or authorize MineDojo.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


ADAPTER_VERSION = "ContractRuntimeAdapterV4_1_2_R1"
SCIENTIFIC_METHOD_VERSION = "V4.1.2"
RUNTIME_BINDING_REVISION = "R1"
CONTRACT_VERSIONS = {"4.1", "4.1.2", "4.1.2-R1"}
RECORD_DISPOSITIONS = {
    "accepted_scientific",
    "audit_only_ambiguous",
    "technical_quarantine",
    "incomplete_pending",
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _Hashed:
    _id_field: str

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop(self._id_field, None)
        return payload

    def compute_id(self) -> str:
        return canonical_sha256(self.payload_without_id())

    def with_id(self):
        return replace(self, **{self._id_field: self.compute_id()})

    def to_dict(self) -> dict[str, Any]:
        item = self if getattr(self, self._id_field) else self.with_id()
        return {
            **item.payload_without_id(),
            self._id_field: getattr(item, self._id_field),
        }


_V41_FIELDS = {
    "bilateral_retrieval_policy": {
        "compatible_rule", "full_library_max_shortcut_permitted", "gamma_policy",
        "incompatible_rule", "mineclip_policy_id", "minimum_count_per_side",
        "online_llm_calls", "paper_memory_v5_release_id", "policy_id",
        "scene_exemplar_release_id", "schema_version", "source_commit",
        "tie_break", "top_k_per_side", "undercovered_state",
    },
    "decision_record_schema": {
        "accepted_label_states", "deterministic_duplicate_safe_ids",
        "outcome_registry_id", "planner_schema_id", "post_join_atomic",
        "pre_record_persisted_before_action", "required_field_coverage",
        "required_sections", "retrieval_policy_id", "rule_registry_id",
        "schema_id", "schema_version", "source_commit",
    },
    "planner_schema": {
        "calls_per_decision", "confidence_required", "extra_confidence_call_permitted",
        "malformed_policy", "output_schema", "parser_policy", "prompt_template",
        "raw_probability_permitted", "same_schema_for_all_baselines", "schema_id",
        "schema_version", "source_commit",
    },
    "rule_registry": {
        "ambiguous_necessity_excluded", "dependency_schema_id",
        "hard_rules_enter_soft_coverage", "labels_available_to_classifier",
        "registry_id", "rules", "schema_version", "source_commit",
        "support_controls_eligibility_only",
    },
    "step_outcome_registry": {
        "controller_boolean_alone_sufficient", "controller_contract_id", "definitions",
        "evaluator_contract_id", "excluded_states", "execution_budget_profile_id",
        "registry_id", "schema_version", "scientific_states", "source_commit",
    },
    "support_policy": {
        "ambiguous_rule_policy", "dependency_support_threshold",
        "dependency_support_threshold_source", "formal_required_field_coverage",
        "insufficient_revision_rule", "parameter_provenance_policy_id", "policy_id",
        "schema_version", "silent_imputation_permitted", "source_commit",
        "sparse_confidence_rule", "sparse_environment_rule", "sparse_horizon_rule",
    },
}
_V412_FIELDS = {
    key: fields | {"contract_version"} for key, fields in _V41_FIELDS.items()
}
_V412_FIELDS["instrumentation_release"] = {
    "behavior_equivalence_audit_id", "contract_version",
    "formal_campaign_started", "record_schema_id", "release_id",
    "released_for_formal_collection", "runtime_mode", "schema_version",
    "smoke_audit_id", "source_commit", "status",
}
_ID_FIELDS = {
    "bilateral_retrieval_policy": "policy_id",
    "decision_record_schema": "schema_id",
    "instrumentation_release": "release_id",
    "planner_schema": "schema_id",
    "rule_registry": "registry_id",
    "step_outcome_registry": "registry_id",
    "support_policy": "policy_id",
}


@dataclass(frozen=True)
class ContractRuntimeAdapterV4_1_2_R1:
    contract_type: str
    contract_version: str
    raw_contract_payload: Mapping[str, Any]
    raw_contract_id: str
    raw_file_sha256: str
    authoring_source_commit: str
    normalized_runtime_view: Mapping[str, Any]
    adapter_version: str = ADAPTER_VERSION
    adapter_id: str = ""

    def __post_init__(self) -> None:
        if self.contract_version not in CONTRACT_VERSIONS:
            raise ValueError("Unsupported contract version")
        if self.adapter_version != ADAPTER_VERSION:
            raise ValueError("Unsupported runtime adapter version")
        if not all(
            (
                self.contract_type,
                self.raw_contract_id,
                self.raw_file_sha256,
                self.authoring_source_commit,
            )
        ):
            raise ValueError("Contract adapter provenance is incomplete")
        if self.adapter_id and self.adapter_id != self.compute_id():
            raise ValueError("Contract adapter hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("adapter_id", None)
        return payload

    def compute_id(self) -> str:
        return canonical_sha256(self.payload_without_id())

    def with_id(self) -> "ContractRuntimeAdapterV4_1_2_R1":
        return replace(self, adapter_id=self.compute_id())


def load_versioned_contract(
    path: str | Path,
    *,
    contract_type: str,
    expected_contract_id: str,
    expected_file_sha256: str,
) -> ContractRuntimeAdapterV4_1_2_R1:
    """Verify frozen bytes and canonical ID before creating a runtime view."""

    source = Path(path)
    actual_file_sha = file_sha256(source)
    if actual_file_sha != expected_file_sha256:
        raise ValueError("Contract file SHA-256 mismatch")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Contract payload must be an object")
    raw_version = payload.get("contract_version")
    version = "4.1" if raw_version is None else str(raw_version)
    if version not in CONTRACT_VERSIONS:
        raise ValueError("Unsupported contract version")
    schemas = _V41_FIELDS if version == "4.1" else _V412_FIELDS
    if contract_type not in schemas:
        raise ValueError("Contract type is unsupported for this version")
    expected_fields = schemas[contract_type]
    if set(payload) != expected_fields:
        missing = sorted(expected_fields - set(payload))
        unknown = sorted(set(payload) - expected_fields)
        raise ValueError(
            f"Contract fields do not match version schema: missing={missing}, unknown={unknown}"
        )
    id_field = _ID_FIELDS[contract_type]
    raw_id = str(payload[id_field])
    if raw_id != expected_contract_id:
        raise ValueError("Contract ID does not match expected binding")
    canonical_payload = dict(payload)
    canonical_payload.pop(id_field)
    if canonical_sha256(canonical_payload) != raw_id:
        raise ValueError("Contract canonical ID mismatch")
    normalized = dict(payload)
    normalized.pop(id_field)
    normalized.pop("contract_version", None)
    return ContractRuntimeAdapterV4_1_2_R1(
        contract_type=contract_type,
        contract_version=version,
        raw_contract_payload=dict(payload),
        raw_contract_id=raw_id,
        raw_file_sha256=actual_file_sha,
        authoring_source_commit=str(payload["source_commit"]),
        normalized_runtime_view=normalized,
    ).with_id()


@dataclass(frozen=True)
class Round513E2AuthorizationSupersessionDecision(_Hashed):
    source_commit: str
    old_authorization_input_id: str
    old_authorization_input_file_sha256: str
    old_approval_statement_sha256: str
    old_assignment_seal_id: str
    old_execution_source_sha: str
    authorization_content_valid: bool = True
    execution_started: bool = False
    smoke_outcomes_observed: bool = False
    reusable_after_source_change: bool = False
    historical_object_preserved: bool = True
    status: str = "superseded_before_execution_due_to_source_hardening"
    schema_version: int = 1
    decision_id: str = ""

    _id_field = "decision_id"

    def __post_init__(self) -> None:
        if not self.authorization_content_valid or not self.historical_object_preserved:
            raise ValueError("Valid historical authorization was not preserved")
        if any((self.execution_started, self.smoke_outcomes_observed, self.reusable_after_source_change)):
            raise ValueError("Superseded authorization crossed an execution boundary")
        if self.status != "superseded_before_execution_due_to_source_hardening":
            raise ValueError("Unexpected supersession status")
        if self.decision_id and self.decision_id != self.compute_id():
            raise ValueError("Supersession decision hash mismatch")


@dataclass(frozen=True)
class ContractCompatibilityEntry:
    contract_type: str
    filename: str
    contract_id: str
    file_sha256: str
    contract_version: str
    authoring_source_commit: str
    runtime_adapter_version: str
    allowed_execution_source_commits: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.filename or Path(self.filename).name != self.filename:
            raise ValueError("Compatibility entry filename must be a safe basename")
        if self.contract_version not in CONTRACT_VERSIONS:
            raise ValueError("Compatibility entry has an unsupported contract version")
        if self.runtime_adapter_version != ADAPTER_VERSION:
            raise ValueError("Compatibility entry has an unsupported adapter")
        if not self.allowed_execution_source_commits:
            raise ValueError("Compatibility entry has no execution source allowlist")


@dataclass(frozen=True)
class Round513E2ContractCompatibilityReleaseR1(_Hashed):
    source_commit: str
    scientific_method_version: str
    runtime_binding_revision: str
    entries: tuple[ContractCompatibilityEntry, ...]
    exact_match_required: bool = True
    schema_version: int = 1
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        if (
            self.scientific_method_version != SCIENTIFIC_METHOD_VERSION
            or self.runtime_binding_revision != RUNTIME_BINDING_REVISION
            or not self.exact_match_required
        ):
            raise ValueError("Compatibility release changed the method or matching policy")
        keys = [(x.contract_type, x.contract_id) for x in self.entries]
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("Compatibility release entries are empty or duplicated")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("Compatibility release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["entries"] = [
            {**asdict(item), "allowed_execution_source_commits": list(item.allowed_execution_source_commits)}
            for item in self.entries
        ]
        return payload

    def require_compatible(self, adapter: ContractRuntimeAdapterV4_1_2_R1, execution_source: str) -> None:
        matches = [
            item for item in self.entries
            if item.contract_type == adapter.contract_type
            and item.contract_id == adapter.raw_contract_id
            and item.file_sha256 == adapter.raw_file_sha256
            and item.contract_version == adapter.contract_version
            and item.authoring_source_commit == adapter.authoring_source_commit
            and item.runtime_adapter_version == adapter.adapter_version
            and execution_source in item.allowed_execution_source_commits
        ]
        if len(matches) != 1:
            raise PermissionError("Contract is not in the exact runtime compatibility allowlist")


def _required_text(value: str, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{label} is required")
    return result


def _gamma_text(value: str, expected: str, label: str) -> str:
    text = _required_text(value, label)
    if text != expected:
        raise ValueError(f"{label} must preserve the approved exact decimal string")
    try:
        Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{label} is not a decimal") from exc
    return text


@dataclass(frozen=True)
class TrackERunBindingV4_1_2_R1(_Hashed):
    execution_source_commit: str
    authorization_receipt_id: str
    authorization_input_id: str
    authorization_input_file_sha256: str
    approval_statement_sha256: str
    smoke_pool_id: str
    smoke_assignments_id: str
    smoke_exclusion_audit_id: str
    smoke_assignment_seal_id: str
    ordered_assignment_root: str
    gamma_candidate: str
    gamma_cov_text: str
    gamma_minus_text: str
    gamma_plus_text: str
    paper_memory_release_id: str
    paper_memory_root: str
    mineclip_policy_id: str
    scene_exemplar_release_id: str
    planner_prompt_id: str
    planner_schema_id: str
    planner_parser_id: str
    rule_registry_id: str
    bilateral_policy_id: str
    decision_record_schema_id: str
    step_outcome_registry_id: str
    instrumentation_release_id: str
    controller_id: str
    evaluator_id: str
    budget_profile_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    compatibility_release_id: str
    runtime_release_id: str
    assignment_id: str
    campaign_id: str
    run_id: str
    episode_id: str
    task: str
    terminal_task: str
    seed_commitment: str
    seed: int
    collection_mode: str
    output_root: str
    scientific_method_version: str = SCIENTIFIC_METHOD_VERSION
    runtime_binding_revision: str = RUNTIME_BINDING_REVISION
    engineering_only: bool = True
    schema_version: int = 1
    binding_id: str = ""

    _id_field = "binding_id"

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if name not in {"binding_id", "schema_version", "engineering_only"} and isinstance(value, str):
                _required_text(value, name)
        if (
            self.scientific_method_version != SCIENTIFIC_METHOD_VERSION
            or self.runtime_binding_revision != RUNTIME_BINDING_REVISION
            or not self.engineering_only
        ):
            raise ValueError("Track E R1 binding changed method or engineering isolation")
        _gamma_text(self.gamma_cov_text, "1.0", "gamma_cov_text")
        minus = Decimal(_gamma_text(self.gamma_minus_text, "-0.01040883", "gamma_minus_text"))
        plus = Decimal(_gamma_text(self.gamma_plus_text, "0.00744657", "gamma_plus_text"))
        if minus >= plus:
            raise ValueError("Approved gamma ordering is invalid")
        if self.collection_mode != "chrmlite_estimation_collection_v41":
            raise ValueError("Track E R1 binding has the wrong collection mode")
        if isinstance(self.seed, bool) or self.seed <= 0:
            raise ValueError("Track E R1 binding requires a positive numeric seed")
        if self.binding_id and self.binding_id != self.compute_id():
            raise ValueError("Track E R1 binding hash mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeRuntimeReleaseV4_1_2_R1(_Hashed):
    source_commit: str
    compatibility_release_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    source_hardening_audit_id: str
    run_binding_schema_id: str
    assignment_schema_id: str
    decision_store_revision: str
    preflight_before_environment: bool
    controller_evaluator_budget_validation: bool
    track_e_image_vector_bridge_validation: bool
    numeric_seed_binding_validation: bool
    python_hash_seed_process_start_validation: bool
    effective_environment_seed_validation: bool
    scientific_method_version: str = SCIENTIFIC_METHOD_VERSION
    runtime_binding_revision: str = RUNTIME_BINDING_REVISION
    minedojo_started: bool = False
    schema_version: int = 1
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        for name in (
            "compatibility_release_id", "technical_retry_policy_id",
            "process_cleanup_policy_id", "source_hardening_audit_id",
            "run_binding_schema_id", "assignment_schema_id",
        ):
            _required_text(getattr(self, name), name)
        if not all((
            self.preflight_before_environment,
            self.controller_evaluator_budget_validation,
            self.track_e_image_vector_bridge_validation,
            self.numeric_seed_binding_validation,
            self.python_hash_seed_process_start_validation,
            self.effective_environment_seed_validation,
        )):
            raise ValueError("Runtime release lacks fail-closed preflight")
        if self.minedojo_started:
            raise ValueError("Source-hardening runtime release cannot start MineDojo")
        if (
            self.scientific_method_version != SCIENTIFIC_METHOD_VERSION
            or self.runtime_binding_revision != RUNTIME_BINDING_REVISION
        ):
            raise ValueError("Runtime release changed the scientific method")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("Runtime release hash mismatch")


@dataclass(frozen=True)
class TrackEExecutionManifestV4_1_2_R1(_Hashed):
    execution_source_commit: str
    run_binding_id: str
    compatibility_release_id: str
    runtime_release_id: str
    authorization_receipt_id: str
    authorization_input_id: str
    authorization_input_file_sha256: str
    approval_statement_sha256: str
    smoke_assignment_seal_id: str
    ordered_assignment_root: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    seed: int
    output_root: str
    gamma_candidate: str
    gamma_cov_text: str
    gamma_minus_text: str
    gamma_plus_text: str
    environment_execution_permitted: bool
    schema_version: int = 1
    manifest_id: str = ""

    _id_field = "manifest_id"

    def __post_init__(self) -> None:
        require_execution_manifest_prerequisites(
            authorization_receipt_id=self.authorization_receipt_id,
            technical_retry_policy_id=self.technical_retry_policy_id,
            process_cleanup_policy_id=self.process_cleanup_policy_id,
        )
        for name, value in asdict(self).items():
            if name not in {"schema_version", "manifest_id", "environment_execution_permitted"} and isinstance(value, str):
                _required_text(value, name)
        _gamma_text(self.gamma_cov_text, "1.0", "gamma_cov_text")
        _gamma_text(self.gamma_minus_text, "-0.01040883", "gamma_minus_text")
        _gamma_text(self.gamma_plus_text, "0.00744657", "gamma_plus_text")
        if not self.environment_execution_permitted:
            raise PermissionError("Execution manifest does not permit environment launch")
        if isinstance(self.seed, bool) or self.seed <= 0:
            raise ValueError("Execution manifest requires a positive numeric seed")
        if self.manifest_id and self.manifest_id != self.compute_id():
            raise ValueError("Execution manifest hash mismatch")


def validate_track_e_r1_artifacts(
    *,
    binding: TrackERunBindingV4_1_2_R1,
    compatibility: Round513E2ContractCompatibilityReleaseR1,
    runtime_release: CHRMLiteEngineeringSmokeRuntimeReleaseV4_1_2_R1,
    technical_retry_policy: TechnicalRetryPolicyV4_1_2_R1,
    process_cleanup_policy: ProcessCleanupPolicyV4_1_2_R1,
    execution_manifest: TrackEExecutionManifestV4_1_2_R1,
    adapters: Mapping[str, ContractRuntimeAdapterV4_1_2_R1],
    cli_output_root: str,
) -> None:
    expected_binding_schema_id = dataclass_schema_id(
        TrackERunBindingV4_1_2_R1,
        invariants={
            "scientific_method_version": "V4.1.2",
            "runtime_binding_revision": "R1",
            "engineering_only": True,
            "gamma_candidate": "B",
        },
    )
    if (
        compatibility.source_commit != binding.execution_source_commit
        or runtime_release.source_commit != binding.execution_source_commit
        or runtime_release.run_binding_schema_id != expected_binding_schema_id
        or runtime_release.technical_retry_policy_id != binding.technical_retry_policy_id
        or runtime_release.process_cleanup_policy_id != binding.process_cleanup_policy_id
        or technical_retry_policy.policy_id != binding.technical_retry_policy_id
        or process_cleanup_policy.policy_id != binding.process_cleanup_policy_id
        or technical_retry_policy.source_commit != binding.execution_source_commit
        or process_cleanup_policy.source_commit != binding.execution_source_commit
    ):
        raise ValueError("Runtime release/source/policy binding mismatch")
    required_types = {
        "planner_schema", "rule_registry", "bilateral_retrieval_policy",
        "decision_record_schema", "step_outcome_registry", "instrumentation_release",
        "support_policy",
    }
    if set(adapters) != required_types:
        raise ValueError("Track E R1 contract adapter inventory is incomplete")
    for adapter in adapters.values():
        compatibility.require_compatible(adapter, binding.execution_source_commit)
    ids = {name: item.raw_contract_id for name, item in adapters.items()}
    expected_ids = {
        "planner_schema": binding.planner_schema_id,
        "rule_registry": binding.rule_registry_id,
        "bilateral_retrieval_policy": binding.bilateral_policy_id,
        "decision_record_schema": binding.decision_record_schema_id,
        "step_outcome_registry": binding.step_outcome_registry_id,
        "instrumentation_release": binding.instrumentation_release_id,
    }
    if any(ids[name] != expected for name, expected in expected_ids.items()):
        raise ValueError("Run binding/contract ID mismatch")
    outcome = adapters["step_outcome_registry"].raw_contract_payload
    if (
        outcome["controller_contract_id"] != binding.controller_id
        or outcome["evaluator_contract_id"] != binding.evaluator_id
        or outcome["execution_budget_profile_id"] != binding.budget_profile_id
    ):
        raise ValueError("Controller/Evaluator/Budget binding mismatch")
    record = adapters["decision_record_schema"].raw_contract_payload
    if (
        record["planner_schema_id"] != binding.planner_schema_id
        or record["rule_registry_id"] != binding.rule_registry_id
        or record["retrieval_policy_id"] != binding.bilateral_policy_id
        or record["outcome_registry_id"] != binding.step_outcome_registry_id
    ):
        raise ValueError("Decision Record Schema lineage mismatch")
    instrument = adapters["instrumentation_release"].raw_contract_payload
    if instrument["record_schema_id"] != binding.decision_record_schema_id:
        raise ValueError("Instrumentation/Decision Schema lineage mismatch")
    if runtime_release.release_id != binding.runtime_release_id:
        raise ValueError("Runtime release binding mismatch")
    if runtime_release.compatibility_release_id != compatibility.release_id:
        raise ValueError("Runtime/Compatibility release mismatch")
    pairs = (
        (execution_manifest.execution_source_commit, binding.execution_source_commit),
        (execution_manifest.run_binding_id, binding.binding_id),
        (execution_manifest.compatibility_release_id, binding.compatibility_release_id),
        (execution_manifest.runtime_release_id, binding.runtime_release_id),
        (execution_manifest.authorization_receipt_id, binding.authorization_receipt_id),
        (execution_manifest.authorization_input_id, binding.authorization_input_id),
        (execution_manifest.authorization_input_file_sha256, binding.authorization_input_file_sha256),
        (execution_manifest.approval_statement_sha256, binding.approval_statement_sha256),
        (execution_manifest.smoke_assignment_seal_id, binding.smoke_assignment_seal_id),
        (execution_manifest.ordered_assignment_root, binding.ordered_assignment_root),
        (execution_manifest.technical_retry_policy_id, binding.technical_retry_policy_id),
        (execution_manifest.process_cleanup_policy_id, binding.process_cleanup_policy_id),
        (execution_manifest.seed, binding.seed),
        (execution_manifest.output_root, binding.output_root),
        (execution_manifest.gamma_candidate, binding.gamma_candidate),
        (execution_manifest.gamma_cov_text, binding.gamma_cov_text),
        (execution_manifest.gamma_minus_text, binding.gamma_minus_text),
        (execution_manifest.gamma_plus_text, binding.gamma_plus_text),
        (str(Path(cli_output_root).resolve()), str(Path(binding.output_root).resolve())),
    )
    if any(left != right for left, right in pairs):
        raise ValueError("Execution Manifest/Run Binding/CLI mismatch")


@dataclass(frozen=True)
class SmokeAssignmentV4_1_2_R1(_Hashed):
    source_commit: str
    legacy_assignment_id: str
    terminal_task: str
    task_path_label: str
    task_file_sha256: str
    difficulty: str
    target_action_family: str
    coverage_feasibility: str
    feasibility_reason: str
    rule_case: str
    knowledge_case: str
    bilateral_case: str
    seed_commitment: str
    seed: int
    engineering_only: bool
    formal_fitting_eligible: bool
    channel_calibration_eligible: bool
    CHRM_fitting_eligible: bool
    CDT_identification_eligible: bool
    holdout_eligible: bool
    final_evaluation_eligible: bool
    contract_version: str = "4.1.2-R1"
    schema_version: int = 1
    assignment_id: str = ""

    _id_field = "assignment_id"

    def __post_init__(self) -> None:
        eligibility = (
            self.formal_fitting_eligible,
            self.channel_calibration_eligible,
            self.CHRM_fitting_eligible,
            self.CDT_identification_eligible,
            self.holdout_eligible,
            self.final_evaluation_eligible,
        )
        if not self.engineering_only or any(eligibility):
            raise ValueError("Smoke R1 assignment is not permanently fitting-ineligible")
        if self.contract_version != "4.1.2-R1":
            raise ValueError("Smoke assignment is not an R1 contract")
        if self.assignment_id and self.assignment_id != self.compute_id():
            raise ValueError("Smoke R1 assignment hash mismatch")

    @classmethod
    def from_legacy(cls, payload: Mapping[str, Any], *, source_commit: str):
        item = dict(payload)
        legacy_id = str(item.pop("assignment_id"))
        item.pop("engineering_only", None)
        item.pop("formal_fitting_eligible", None)
        return cls(
            source_commit=source_commit,
            legacy_assignment_id=legacy_id,
            engineering_only=True,
            formal_fitting_eligible=False,
            channel_calibration_eligible=False,
            CHRM_fitting_eligible=False,
            CDT_identification_eligible=False,
            holdout_eligible=False,
            final_evaluation_eligible=False,
            **item,
        ).with_id()

    def scientific_payload(self) -> dict[str, Any]:
        return {
            key: getattr(self, key)
            for key in (
                "terminal_task", "task_path_label", "task_file_sha256", "difficulty",
                "target_action_family", "coverage_feasibility", "feasibility_reason",
                "rule_case", "knowledge_case", "bilateral_case", "seed_commitment", "seed",
            )
        }


def legacy_scientific_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in (
            "terminal_task", "task_path_label", "task_file_sha256", "difficulty",
            "target_action_family", "coverage_feasibility", "feasibility_reason",
            "rule_case", "knowledge_case", "bilateral_case", "seed_commitment", "seed",
        )
    }


def ordered_scientific_payload_root(items: Sequence[Mapping[str, Any]]) -> str:
    return canonical_sha256(
        [{"order": index, **legacy_scientific_payload(item)} for index, item in enumerate(items)]
    )


@dataclass(frozen=True)
class SmokeAssignmentScientificPayloadEquivalenceAudit(_Hashed):
    source_commit: str
    old_assignments_id: str
    new_assignments_id: str
    old_ordered_scientific_payload_root: str
    new_ordered_scientific_payload_root: str
    assignment_count: int
    tasks_changed: int
    seeds_changed: int
    order_changed: int
    status: str
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        equivalent = (
            self.assignment_count == 9
            and self.old_ordered_scientific_payload_root == self.new_ordered_scientific_payload_root
            and not any((self.tasks_changed, self.seeds_changed, self.order_changed))
        )
        if self.status != ("EQUIVALENT" if equivalent else "MISMATCH"):
            raise ValueError("Scientific assignment equivalence conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Scientific assignment equivalence audit hash mismatch")


class AtomicDecisionStoreV4_1_2_R1:
    """Separate scientific acceptance from data-use eligibility and failures."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.pending = self.root / "incomplete_pending"
        self.accepted = self.root / "accepted_scientific"
        self.ambiguous = self.root / "audit_only_ambiguous"
        self.technical = self.root / "technical_quarantine"
        for path in (self.pending, self.accepted, self.ambiguous, self.technical):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def paths_for(self, record_id: str) -> dict[str, Path]:
        if not record_id or any(ch not in "0123456789abcdef" for ch in record_id):
            raise ValueError("record_id must be a lowercase hexadecimal digest")
        return {
            "incomplete_pending": self.pending / f"{record_id}.json",
            "accepted_scientific": self.accepted / f"{record_id}.json",
            "audit_only_ambiguous": self.ambiguous / f"{record_id}.json",
            "technical_quarantine": self.technical / f"{record_id}.json",
        }

    def should_execute(self, record_id: str) -> bool:
        paths = self.paths_for(record_id)
        return not any(path.exists() for key, path in paths.items() if key != "incomplete_pending")

    def persist_pre(self, record: Any) -> str:
        paths = self.paths_for(record.record_id)
        if any(paths[key].exists() for key in RECORD_DISPOSITIONS - {"incomplete_pending"}):
            return "completed_do_not_relaunch"
        payload = record.to_dict()
        pending = paths["incomplete_pending"]
        if pending.exists():
            if canonical_json(json.loads(pending.read_text(encoding="utf-8"))) != canonical_json(payload):
                raise ValueError("Pending record ID collision")
            return "pending_resume"
        self._write_exclusive(pending, payload)
        return "created"

    def join_post(self, record: Any) -> Path:
        item = record.with_hash()
        paths = self.paths_for(item.pre.record_id)
        state = item.label.state
        disposition = {
            "success": "accepted_scientific",
            "scientific_failure": "accepted_scientific",
            "ambiguous_unobservable": "audit_only_ambiguous",
            "technical_failure": "technical_quarantine",
        }.get(state)
        if disposition is None:
            raise ValueError("Unknown record disposition for label")
        existing = [key for key, path in paths.items() if key != "incomplete_pending" and path.exists()]
        if existing and existing != [disposition]:
            raise ValueError("Record ID already finalized in another disposition")
        payload = {**item.to_dict(), "record_disposition": disposition}
        target = paths[disposition]
        if target.exists():
            if canonical_json(json.loads(target.read_text(encoding="utf-8"))) != canonical_json(payload):
                raise ValueError("Final record ID collision")
            paths["incomplete_pending"].unlink(missing_ok=True)
            return target
        if not paths["incomplete_pending"].exists():
            raise ValueError("Post receipt has no persisted pre-record")
        temporary = target.with_suffix(".tmp")
        self._write_exclusive(temporary, payload)
        os.replace(temporary, target)
        paths["incomplete_pending"].unlink()
        return target


@dataclass(frozen=True)
class PolicyCandidate:
    candidate_id: str
    source_scope: str
    source_file_sha256: str
    completeness: str
    scientific_validity_impact: str
    engineering_cost: str


@dataclass(frozen=True)
class TechnicalRetryPolicyProvenanceAudit(_Hashed):
    source_commit: str
    candidates: tuple[PolicyCandidate, ...]
    unique_complete_forward_policy_found: bool
    missing_required_fields: tuple[str, ...]
    conclusion: str
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        expected = "REUSABLE" if self.unique_complete_forward_policy_found else "AUTHOR_DECISION_REQUIRED"
        if self.conclusion != expected:
            raise ValueError("Retry provenance conclusion is inconsistent")
        if not self.unique_complete_forward_policy_found and not self.missing_required_fields:
            raise ValueError("Incomplete retry provenance lacks explicit gaps")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Retry provenance audit hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["candidates"] = [asdict(item) for item in self.candidates]
        payload["missing_required_fields"] = list(self.missing_required_fields)
        return payload


@dataclass(frozen=True)
class ProcessCleanupPolicyProvenanceAudit(_Hashed):
    source_commit: str
    candidates: tuple[PolicyCandidate, ...]
    unique_complete_forward_policy_found: bool
    missing_required_fields: tuple[str, ...]
    unrelated_process_kill_risk: bool
    conclusion: str
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        expected = "REUSABLE" if self.unique_complete_forward_policy_found else "AUTHOR_DECISION_REQUIRED"
        if self.conclusion != expected:
            raise ValueError("Cleanup provenance conclusion is inconsistent")
        if not self.unique_complete_forward_policy_found and not self.missing_required_fields:
            raise ValueError("Incomplete cleanup provenance lacks explicit gaps")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Cleanup provenance audit hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["candidates"] = [asdict(item) for item in self.candidates]
        payload["missing_required_fields"] = list(self.missing_required_fields)
        return payload


@dataclass(frozen=True)
class TechnicalRetryAndCleanupDecisionInput(_Hashed):
    source_commit: str
    retry_provenance_audit_id: str
    cleanup_provenance_audit_id: str
    retry_candidates: tuple[Mapping[str, Any], ...]
    cleanup_candidates: tuple[Mapping[str, Any], ...]
    required_author_fields: tuple[str, ...]
    status: str = "pending_ZYF_decision"
    minedojo_execution_permitted: bool = False
    schema_version: int = 1
    decision_input_id: str = ""

    _id_field = "decision_input_id"

    def __post_init__(self) -> None:
        if self.status != "pending_ZYF_decision" or self.minedojo_execution_permitted:
            raise ValueError("Policy decision input fabricated authorization")
        if not self.retry_candidates or not self.cleanup_candidates or not self.required_author_fields:
            raise ValueError("Policy decision input is incomplete")
        if self.decision_input_id and self.decision_input_id != self.compute_id():
            raise ValueError("Policy decision input hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["retry_candidates"] = [dict(item) for item in self.retry_candidates]
        payload["cleanup_candidates"] = [dict(item) for item in self.cleanup_candidates]
        payload["required_author_fields"] = list(self.required_author_fields)
        return payload


@dataclass(frozen=True)
class TechnicalRetryPolicyV4_1_2_R1(_Hashed):
    source_commit: str
    decision_input_id: str
    decision_input_file_sha256: str
    approval_statement_sha256: str
    retry_candidate: str
    allowed_technical_failure_categories: tuple[str, ...]
    maximum_attempts_per_technical_category: int
    total_maximum_attempts: int
    backoff_seconds: int
    scientific_success_retries: int
    scientific_failure_retries: int
    pre_action_proof_required: bool
    attempt_isolation_required: bool
    technical_partial_record_disposition: str
    unclassified_technical_failure_policy: str
    schema_version: int = 1
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        expected = (
            "environment_start_failure", "seed_application_failure",
            "provider_transport_failure", "provider_empty_response",
        )
        if self.retry_candidate != "T1_one_retry":
            raise ValueError("Technical retry policy does not match the author decision")
        if self.allowed_technical_failure_categories != expected:
            raise ValueError("Technical retry categories do not match the author decision")
        if (
            self.maximum_attempts_per_technical_category != 2
            or self.total_maximum_attempts != 2
            or self.backoff_seconds != 30
        ):
            raise ValueError("Technical retry budget does not match the author decision")
        if self.scientific_success_retries or self.scientific_failure_retries:
            raise ValueError("Scientific outcomes must never be retried")
        if not self.pre_action_proof_required or not self.attempt_isolation_required:
            raise ValueError("Technical retries require pre-action proof and isolation")
        if self.technical_partial_record_disposition != "technical_quarantine":
            raise ValueError("Technical partial records must be quarantined")
        if self.unclassified_technical_failure_policy != "stop_immediately":
            raise ValueError("Unclassified technical failures must stop immediately")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("Technical retry policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["allowed_technical_failure_categories"] = list(
            self.allowed_technical_failure_categories
        )
        return payload


@dataclass(frozen=True)
class ProcessCleanupPolicyV4_1_2_R1(_Hashed):
    source_commit: str
    decision_input_id: str
    decision_input_file_sha256: str
    approval_statement_sha256: str
    cleanup_candidate: str
    cleanup_grace_seconds: int
    campaign_owned_ports: tuple[str, ...]
    campaign_owned_lock_patterns: tuple[str, ...]
    campaign_owned_display_sessions: tuple[str, ...]
    required_target_checks: tuple[str, ...]
    launch_ownership_ledger_required: bool
    unrelated_process_kill_permitted: bool
    residual_process_policy: str
    output_directory_policy: str
    schema_version: int = 1
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        expected_targets = (
            "MineDojo", "Minecraft", "Mineflayer", "bridge",
            "ports", "lock_files", "display_sessions",
        )
        if self.cleanup_candidate != "C1_scoped_process_group_cleanup":
            raise ValueError("Cleanup candidate does not match the author decision")
        if self.cleanup_grace_seconds != 20:
            raise ValueError("Cleanup grace period does not match the author decision")
        if not all((
            self.campaign_owned_ports,
            self.campaign_owned_lock_patterns,
            self.campaign_owned_display_sessions,
        )):
            raise ValueError("Cleanup ownership scope is incomplete")
        if self.required_target_checks != expected_targets:
            raise ValueError("Cleanup target inventory is incomplete")
        if not self.launch_ownership_ledger_required or self.unrelated_process_kill_permitted:
            raise ValueError("Cleanup must be ledger-scoped and non-invasive")
        if self.residual_process_policy != "stop_if_campaign_owned_residual_remains":
            raise ValueError("Cleanup residual policy is not fail closed")
        if self.output_directory_policy != "exclusive_per_attempt_then_atomic_disposition":
            raise ValueError("Cleanup output policy does not isolate attempts")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("Process cleanup policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        for name in (
            "campaign_owned_ports", "campaign_owned_lock_patterns",
            "campaign_owned_display_sessions", "required_target_checks",
        ):
            payload[name] = list(getattr(self, name))
        return payload


def dataclass_schema_id(cls: type, *, invariants: Mapping[str, Any]) -> str:
    return canonical_sha256({
        "class": cls.__name__,
        "fields": list(cls.__dataclass_fields__),
        "invariants": dict(invariants),
    })


@dataclass(frozen=True)
class Round513E2SourceHardeningAudit(_Hashed):
    source_commit: str
    supersession_decision_id: str
    compatibility_release_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    adapter_version: str
    raw_identity_round_trip_passed: bool
    canonical_hash_before_adaptation_passed: bool
    source_provenance_separation_passed: bool
    exact_compatibility_allowlist_passed: bool
    controller_evaluator_budget_validation_passed: bool
    snapshot_guard_passed: bool
    paper_memory_write_probe_rejected: bool
    relevant_skips: int
    minedojo_launch_count: int
    scientific_method_changed: bool
    gamma_changed: bool
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        required = (
            self.raw_identity_round_trip_passed,
            self.canonical_hash_before_adaptation_passed,
            self.source_provenance_separation_passed,
            self.exact_compatibility_allowlist_passed,
            self.controller_evaluator_budget_validation_passed,
            self.snapshot_guard_passed,
            self.paper_memory_write_probe_rejected,
        )
        if not all(required) or self.relevant_skips or self.minedojo_launch_count:
            raise ValueError("Source-hardening audit is not eligible for source freeze")
        if self.scientific_method_changed or self.gamma_changed:
            raise ValueError("Source hardening changed frozen scientific content")
        if self.adapter_version != ADAPTER_VERSION:
            raise ValueError("Source-hardening audit uses an unknown adapter")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Source-hardening audit hash mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeAssignmentsV4_1_2_R1(_Hashed):
    source_commit: str
    legacy_assignments_id: str
    pool_id: str
    runtime_release_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    assignments: tuple[SmokeAssignmentV4_1_2_R1, ...]
    fixed_before_outcomes: bool = True
    observed_coverage_can_expand_set: bool = False
    schema_version: int = 1
    assignments_id: str = ""

    _id_field = "assignments_id"

    def __post_init__(self) -> None:
        if len(self.assignments) != 9 or len({x.assignment_id for x in self.assignments}) != 9:
            raise ValueError("R1 smoke assignments must contain exactly nine unique rows")
        if not self.fixed_before_outcomes or self.observed_coverage_can_expand_set:
            raise ValueError("R1 smoke assignments are not prospectively frozen")
        if self.assignments_id and self.assignments_id != self.compute_id():
            raise ValueError("R1 smoke assignments hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["assignments"] = [item.to_dict() for item in self.assignments]
        return payload


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeExclusionAuditV4_1_2_R1(_Hashed):
    source_commit: str
    assignments_id: str
    prior_exclusion_audit_id: str
    acquisition_overlap_count: int
    historical_development_overlap_count: int
    previous_smoke_overlap_count: int
    future_formal_v412_overlap_count: int
    holdout_overlap_count: int
    final_overlap_count: int
    proof_method: str
    eligible: bool
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        counts = (
            self.acquisition_overlap_count, self.historical_development_overlap_count,
            self.previous_smoke_overlap_count, self.future_formal_v412_overlap_count,
            self.holdout_overlap_count, self.final_overlap_count,
        )
        if any(counts) or not self.eligible:
            raise ValueError("R1 smoke assignments overlap an excluded split")
        if self.proof_method != "legacy_cryptographic_namespace_proof_rebound_to_equivalent_payload":
            raise ValueError("R1 exclusion audit has an unknown proof method")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("R1 exclusion audit hash mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeSealV4_1_2_R1(_Hashed):
    source_commit: str
    compatibility_release_id: str
    runtime_release_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    assignments_id: str
    assignments_root_sha256: str
    ordered_scientific_payload_root: str
    exclusion_audit_id: str
    equivalence_audit_id: str
    assignment_count: int
    permanently_engineering_only: bool
    fitting_ineligible: bool
    sealed: bool
    schema_version: int = 1
    seal_id: str = ""

    _id_field = "seal_id"

    def __post_init__(self) -> None:
        if self.assignment_count != 9:
            raise ValueError("R1 smoke seal must bind exactly nine assignments")
        if not all((self.permanently_engineering_only, self.fitting_ineligible, self.sealed)):
            raise ValueError("R1 smoke seal does not enforce permanent exclusion")
        if self.seal_id and self.seal_id != self.compute_id():
            raise ValueError("R1 smoke seal hash mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2_R1(_Hashed):
    source_commit: str
    runtime_release_id: str
    compatibility_release_id: str
    run_binding_schema_id: str
    assignment_schema_id: str
    smoke_assignments_id: str
    smoke_assignment_seal_id: str
    smoke_exclusion_audit_id: str
    scientific_payload_equivalence_audit_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    paper_memory_release_id: str
    paper_memory_root: str
    mineclip_policy_id: str
    scene_exemplar_release_id: str
    planner_prompt_id: str
    planner_schema_id: str
    planner_parser_id: str
    rule_registry_id: str
    bilateral_policy_id: str
    decision_record_schema_id: str
    step_outcome_registry_id: str
    instrumentation_release_id: str
    controller_id: str
    evaluator_id: str
    budget_profile_id: str
    gamma_candidate: str
    gamma_cov_text: str
    gamma_minus_text: str
    gamma_plus_text: str
    declarations: tuple[str, ...]
    reauthorization_status: str = "pending"
    minedojo_execution_permitted: bool = False
    formal_development_permitted: bool = False
    holdout_final_round6_permitted: bool = False
    approved_by: str | None = None
    schema_version: int = 1
    authorization_input_id: str = ""

    _id_field = "authorization_input_id"

    def __post_init__(self) -> None:
        if self.reauthorization_status != "pending" or self.approved_by is not None:
            raise ValueError("R1 authorization input fabricated author approval")
        if any((
            self.minedojo_execution_permitted,
            self.formal_development_permitted,
            self.holdout_final_round6_permitted,
        )):
            raise ValueError("R1 authorization input opens a forbidden execution boundary")
        if len(self.declarations) < 12 or len(set(self.declarations)) != len(self.declarations):
            raise ValueError("R1 authorization input declarations are incomplete")
        _gamma_text(self.gamma_cov_text, "1.0", "gamma_cov_text")
        _gamma_text(self.gamma_minus_text, "-0.01040883", "gamma_minus_text")
        _gamma_text(self.gamma_plus_text, "0.00744657", "gamma_plus_text")
        if self.gamma_candidate != "0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f":
            raise ValueError("R1 authorization input changed Candidate B")
        if self.authorization_input_id and self.authorization_input_id != self.compute_id():
            raise ValueError("R1 authorization input hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["declarations"] = list(self.declarations)
        return payload


def require_execution_manifest_prerequisites(
    *, authorization_receipt_id: str, technical_retry_policy_id: str,
    process_cleanup_policy_id: str,
) -> None:
    for label, value in (
        ("authorization_receipt_id", authorization_receipt_id),
        ("technical_retry_policy_id", technical_retry_policy_id),
        ("process_cleanup_policy_id", process_cleanup_policy_id),
    ):
        _required_text(value, label)


def validate_all_before_environment_launch(
    validators: Sequence[Callable[[], None]], environment_launcher: Callable[[], Any]
) -> Any:
    for validator in validators:
        validator()
    return environment_launcher()
