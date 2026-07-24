"""Round 5.13E3H versioned runtime contracts.

The E3H layer adapts frozen E3 scientific contracts for execution without
changing their identities or the historical E2H runtime classes. Raw bytes and
canonical identities are verified before any normalized runtime view is built.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .round513e2h import (
    ADAPTER_VERSION as E2H_ADAPTER_VERSION,
    ContractCompatibilityEntry,
    ContractRuntimeAdapterV4_1_2_R1,
    ProcessCleanupPolicyV4_1_2_R1,
    TechnicalRetryPolicyV4_1_2_R1,
    canonical_json,
    canonical_sha256,
    file_sha256,
)


E3X_CONTRACT_VERSION = "E3X-R1"
E3X_SCHEMA_VERSION = 1
E3X_RUNTIME_ADAPTER_VERSION = "Round513E3XRuntimeAdapterR1"
E3X_POLICY_ADAPTER_VERSION = "Round513E3PolicyAdapterR1"
E3X_RUNTIME_SCHEMA = "CHRMLiteEngineeringSmokeRuntimeReleaseE3X_R1"
GAMMA_CANDIDATE_B = "0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f"
GAMMA_TEXT = ("1.0", "-0.01040883", "0.00744657")


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
        return {**item.payload_without_id(), self._id_field: getattr(item, self._id_field)}


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")


def _require_contract_header(
    *, contract_type: str, expected_type: str, contract_version: str, schema_version: int
) -> None:
    if contract_type != expected_type:
        raise ValueError(f"Expected contract_type={expected_type}")
    if contract_version != E3X_CONTRACT_VERSION:
        raise ValueError("Unsupported E3X contract version")
    if schema_version != E3X_SCHEMA_VERSION:
        raise ValueError("Unsupported E3X schema version")


@dataclass(frozen=True)
class TrackERunBindingE3X_R1(_Hashed):
    contract_type: str
    contract_version: str
    execution_source_commit: str
    authorization_input_id: str
    authorization_input_file_sha256: str
    authorization_receipt_id: str
    authorization_receipt_file_sha256: str
    approval_statement_sha256: str
    pool_id: str
    assignments_id: str
    exclusion_audit_id: str
    assignment_seal_id: str
    ordered_assignment_root: str
    assignment_count: int
    formal_taskset_release_id: str
    formal_catalog_sha256: str
    namespace_id: str
    proxy_policy: str
    proxy_decision_input_id: str
    iron_ingot_asset_audit_id: str
    gamma_candidate: str
    gamma_cov_text: str
    gamma_minus_text: str
    gamma_plus_text: str
    planner_prompt_id: str
    planner_schema_id: str
    planner_parser_id: str
    planner_runtime_request_contract_id: str
    provider_request_policy_id: str
    rule_registry_id: str
    bilateral_policy_id: str
    decision_record_schema_id: str
    step_outcome_registry_id: str
    instrumentation_release_id: str
    paper_memory_release_id: str
    paper_memory_root: str
    mineclip_policy_id: str
    scene_exemplar_release_id: str
    controller_id: str
    evaluator_id: str
    budget_profile_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    policy_compatibility_release_id: str
    contract_compatibility_release_id: str
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
    engineering_only: bool = True
    schema_version: int = E3X_SCHEMA_VERSION
    binding_id: str = ""

    _id_field = "binding_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, str) and item.name != "binding_id":
                _require_text(value, item.name)
        if self.assignment_count != 9 or not self.engineering_only:
            raise ValueError("E3X binding is not the frozen nine-item engineering smoke")
        if self.proxy_policy != "P1":
            raise ValueError("E3X binding changed the approved proxy policy")
        if self.gamma_candidate != GAMMA_CANDIDATE_B or (
            self.gamma_cov_text, self.gamma_minus_text, self.gamma_plus_text
        ) != GAMMA_TEXT:
            raise ValueError("E3X binding changed Candidate B or exact Gamma strings")
        if self.collection_mode != "chrmlite_estimation_collection_v41":
            raise ValueError("E3X binding has the wrong collection mode")
        if isinstance(self.seed, bool) or self.seed <= 0:
            raise ValueError("E3X binding requires a positive numeric seed")
        if self.binding_id and self.binding_id != self.compute_id():
            raise ValueError("E3X binding canonical ID mismatch")


@dataclass(frozen=True)
class Round513E3PolicyCompatibilityEntryR1:
    policy_type: str
    policy_id: str
    file_sha256: str
    authoring_source_commit: str
    allowed_runtime_adapter_versions: tuple[str, ...]
    allowed_runtime_schemas: tuple[str, ...]
    allowed_execution_source_commits: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.policy_type not in {"technical_retry", "process_cleanup"}:
            raise ValueError("Unknown policy compatibility type")
        if not all((
            self.policy_id, self.file_sha256, self.authoring_source_commit,
            self.allowed_runtime_adapter_versions, self.allowed_runtime_schemas,
            self.allowed_execution_source_commits,
        )):
            raise ValueError("Policy compatibility entry is incomplete")


@dataclass(frozen=True)
class Round513E3PolicyCompatibilityReleaseR1(_Hashed):
    contract_type: str
    contract_version: str
    source_commit: str
    entries: tuple[Round513E3PolicyCompatibilityEntryR1, ...]
    exact_id_hash_match_required: bool = True
    schema_version: int = E3X_SCHEMA_VERSION
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        if tuple(item.policy_type for item in self.entries) != (
            "technical_retry", "process_cleanup"
        ):
            raise ValueError("Policy compatibility release must contain retry then cleanup")
        if not self.exact_id_hash_match_required:
            raise ValueError("Policy compatibility must require exact ID/hash")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("Policy compatibility release canonical ID mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["entries"] = [
            {
                **asdict(item),
                "allowed_runtime_adapter_versions": list(item.allowed_runtime_adapter_versions),
                "allowed_runtime_schemas": list(item.allowed_runtime_schemas),
                "allowed_execution_source_commits": list(item.allowed_execution_source_commits),
            }
            for item in self.entries
        ]
        return payload


@dataclass(frozen=True)
class Round513E3ContractCompatibilityReleaseR1(_Hashed):
    contract_type: str
    contract_version: str
    source_commit: str
    source_hardening_audit_id: str
    historical_e3_compatibility_release_id: str
    historical_e3_compatibility_file_sha256: str
    historical_e2h_compatibility_release_id: str
    provider_request_policy_id: str
    planner_runtime_request_contract_id: str
    planner_schema_id: str
    planner_parser_id: str
    scientific_contract_entries: tuple[ContractCompatibilityEntry, ...]
    runtime_adapter_version: str
    runtime_schema: str
    historical_e2h_reconstructable: bool = True
    exact_match_required: bool = True
    schema_version: int = E3X_SCHEMA_VERSION
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        if self.runtime_adapter_version != E3X_RUNTIME_ADAPTER_VERSION:
            raise ValueError("Unsupported E3X runtime adapter")
        if self.runtime_schema != E3X_RUNTIME_SCHEMA:
            raise ValueError("Unsupported E3X runtime schema")
        if not self.historical_e2h_reconstructable or not self.exact_match_required:
            raise ValueError("E3X compatibility weakens historical or exact matching")
        if len(self.scientific_contract_entries) != 7:
            raise ValueError("E3X scientific contract inventory is incomplete")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("E3X compatibility release canonical ID mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["scientific_contract_entries"] = [
            {
                **asdict(item),
                "allowed_execution_source_commits": list(item.allowed_execution_source_commits),
            }
            for item in self.scientific_contract_entries
        ]
        return payload

    def require_scientific_contract(
        self, adapter: ContractRuntimeAdapterV4_1_2_R1, execution_source: str
    ) -> None:
        matches = [
            item for item in self.scientific_contract_entries
            if item.contract_type == adapter.contract_type
            and item.contract_id == adapter.raw_contract_id
            and item.file_sha256 == adapter.raw_file_sha256
            and item.contract_version == adapter.contract_version
            and item.authoring_source_commit == adapter.authoring_source_commit
            and item.runtime_adapter_version == E2H_ADAPTER_VERSION
            and execution_source in item.allowed_execution_source_commits
        ]
        if len(matches) != 1:
            raise PermissionError("Scientific contract is not in the exact E3X allowlist")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeRuntimeReleaseE3X_R1(_Hashed):
    contract_type: str
    contract_version: str
    source_commit: str
    source_hardening_audit_id: str
    contract_compatibility_release_id: str
    policy_compatibility_release_id: str
    provider_request_policy_id: str
    planner_runtime_request_contract_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    controller_id: str
    evaluator_id: str
    budget_profile_id: str
    run_binding_schema_id: str
    execution_manifest_schema_id: str
    runtime_adapter_version: str
    preflight_order_id: str
    memory_no_write: bool = True
    evaluation_chain_changed: bool = False
    scientific_method_changed: bool = False
    minedojo_started: bool = False
    schema_version: int = E3X_SCHEMA_VERSION
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        if self.runtime_adapter_version != E3X_RUNTIME_ADAPTER_VERSION:
            raise ValueError("Runtime release uses an unsupported adapter")
        if not self.memory_no_write or any((
            self.evaluation_chain_changed, self.scientific_method_changed, self.minedojo_started
        )):
            raise ValueError("E3X runtime release changed frozen scientific behavior")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("E3X runtime release canonical ID mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeExecutionManifestE3X_R1(_Hashed):
    contract_type: str
    contract_version: str
    execution_source_commit: str
    run_binding_id: str
    authorization_input_id: str
    authorization_input_file_sha256: str
    authorization_receipt_id: str
    authorization_receipt_file_sha256: str
    approval_statement_sha256: str
    assignment_seal_id: str
    ordered_assignment_root: str
    assignment_id: str
    contract_compatibility_release_id: str
    policy_compatibility_release_id: str
    runtime_release_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    controller_id: str
    evaluator_id: str
    budget_profile_id: str
    seed: int
    output_root: str
    gamma_candidate: str
    gamma_cov_text: str
    gamma_minus_text: str
    gamma_plus_text: str
    environment_execution_permitted: bool
    schema_version: int = E3X_SCHEMA_VERSION
    manifest_id: str = ""

    _id_field = "manifest_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        if self.gamma_candidate != GAMMA_CANDIDATE_B or (
            self.gamma_cov_text, self.gamma_minus_text, self.gamma_plus_text
        ) != GAMMA_TEXT:
            raise ValueError("E3X manifest changed Candidate B or exact Gamma strings")
        if not self.environment_execution_permitted:
            raise PermissionError("E3X manifest does not authorize environment execution")
        if isinstance(self.seed, bool) or self.seed <= 0:
            raise ValueError("E3X manifest requires a positive numeric seed")
        if self.manifest_id and self.manifest_id != self.compute_id():
            raise ValueError("E3X execution manifest canonical ID mismatch")


_E3X_TYPES: dict[str, tuple[type[_Hashed], str]] = {
    "TrackERunBindingE3X_R1": (TrackERunBindingE3X_R1, "binding_id"),
    "Round513E3ContractCompatibilityReleaseR1": (
        Round513E3ContractCompatibilityReleaseR1, "release_id"
    ),
    "Round513E3PolicyCompatibilityReleaseR1": (
        Round513E3PolicyCompatibilityReleaseR1, "release_id"
    ),
    "CHRMLiteEngineeringSmokeRuntimeReleaseE3X_R1": (
        CHRMLiteEngineeringSmokeRuntimeReleaseE3X_R1, "release_id"
    ),
    "CHRMLiteEngineeringSmokeExecutionManifestE3X_R1": (
        CHRMLiteEngineeringSmokeExecutionManifestE3X_R1, "manifest_id"
    ),
}


@dataclass(frozen=True)
class E3XRawContractAdapter:
    raw_contract_payload: Mapping[str, Any]
    raw_file_sha256: str
    raw_canonical_id: str
    contract_type: str
    contract_version: str
    schema_version: int
    authoring_source_commit: str
    adapter_version: str
    normalized_runtime_view: Any
    adapter_id: str = ""

    def compute_id(self) -> str:
        payload = asdict(self)
        payload.pop("adapter_id", None)
        payload["normalized_runtime_view"] = self.normalized_runtime_view.to_dict()
        return canonical_sha256(payload)

    def with_id(self) -> "E3XRawContractAdapter":
        return replace(self, adapter_id=self.compute_id())


def _strict_fields(cls: type, payload: Mapping[str, Any]) -> None:
    expected = {item.name for item in fields(cls)}
    actual = set(payload)
    if actual != expected:
        raise ValueError(
            f"E3X contract fields mismatch: missing={sorted(expected-actual)}, "
            f"unknown={sorted(actual-expected)}"
        )


def _construct_e3x(contract_type: str, payload: Mapping[str, Any]) -> _Hashed:
    cls, _ = _E3X_TYPES[contract_type]
    item = dict(payload)
    if cls is Round513E3PolicyCompatibilityReleaseR1:
        item["entries"] = tuple(
            Round513E3PolicyCompatibilityEntryR1(
                **{
                    **entry,
                    "allowed_runtime_adapter_versions": tuple(entry["allowed_runtime_adapter_versions"]),
                    "allowed_runtime_schemas": tuple(entry["allowed_runtime_schemas"]),
                    "allowed_execution_source_commits": tuple(entry["allowed_execution_source_commits"]),
                }
            )
            for entry in item["entries"]
        )
    elif cls is Round513E3ContractCompatibilityReleaseR1:
        item["scientific_contract_entries"] = tuple(
            ContractCompatibilityEntry(
                **{
                    **entry,
                    "allowed_execution_source_commits": tuple(entry["allowed_execution_source_commits"]),
                }
            )
            for entry in item["scientific_contract_entries"]
        )
    elif cls is CHRMLiteEngineeringSmokeAssignmentsE3X_R1:
        item["assignments"] = tuple(
            SmokeAssignmentE3X_R1(**entry) for entry in item["assignments"]
        )
    elif cls is CHRMLiteEngineeringSmokeAuthorizationInputE3X_R1:
        item["declarations"] = tuple(item["declarations"])
    return cls(**item)


def load_e3x_contract(
    path: str | Path, *, expected_file_sha256: str, expected_contract_id: str
) -> E3XRawContractAdapter:
    """Load an E3X contract with raw SHA and canonical ID checks first."""

    source = Path(path)
    raw_bytes = source.read_bytes()
    actual_sha = hashlib.sha256(raw_bytes).hexdigest()
    if actual_sha != expected_file_sha256:
        raise ValueError("E3X raw file SHA-256 mismatch")
    payload = json.loads(raw_bytes)
    if not isinstance(payload, dict):
        raise ValueError("E3X contract payload must be an object")
    for discriminator in ("contract_type", "contract_version", "schema_version"):
        if discriminator not in payload:
            raise ValueError(f"E3X contract discriminator missing: {discriminator}")
    contract_type = str(payload["contract_type"])
    if contract_type not in _E3X_TYPES:
        raise ValueError("Unknown E3X contract type")
    if payload["contract_version"] != E3X_CONTRACT_VERSION:
        raise ValueError("Unknown E3X contract version")
    if payload["schema_version"] != E3X_SCHEMA_VERSION:
        raise ValueError("Unknown E3X schema version")
    cls, id_field = _E3X_TYPES[contract_type]
    _strict_fields(cls, payload)
    raw_id = str(payload[id_field])
    if raw_id != expected_contract_id:
        raise ValueError("E3X raw contract ID does not match the binding")
    canonical = dict(payload)
    canonical.pop(id_field)
    if canonical_sha256(canonical) != raw_id:
        raise ValueError("E3X raw canonical ID mismatch")
    normalized = _construct_e3x(contract_type, payload)
    source_commit = str(
        payload.get("source_commit", payload.get("execution_source_commit", ""))
    )
    return E3XRawContractAdapter(
        raw_contract_payload=dict(payload),
        raw_file_sha256=actual_sha,
        raw_canonical_id=raw_id,
        contract_type=contract_type,
        contract_version=E3X_CONTRACT_VERSION,
        schema_version=E3X_SCHEMA_VERSION,
        authoring_source_commit=source_commit,
        adapter_version=E3X_RUNTIME_ADAPTER_VERSION,
        normalized_runtime_view=normalized,
    ).with_id()


@dataclass(frozen=True)
class FrozenPolicyAdapterE3X_R1:
    policy_type: str
    raw_policy_payload: Mapping[str, Any]
    raw_file_sha256: str
    raw_policy_id: str
    authoring_source_commit: str
    adapter_version: str
    normalized_runtime_view: TechnicalRetryPolicyV4_1_2_R1 | ProcessCleanupPolicyV4_1_2_R1
    adapter_id: str = ""

    def compute_id(self) -> str:
        payload = asdict(self)
        payload.pop("adapter_id", None)
        payload["normalized_runtime_view"] = self.normalized_runtime_view.to_dict()
        return canonical_sha256(payload)

    def with_id(self) -> "FrozenPolicyAdapterE3X_R1":
        return replace(self, adapter_id=self.compute_id())


def load_frozen_policy(
    path: str | Path, *, policy_type: str, expected_policy_id: str,
    expected_file_sha256: str,
) -> FrozenPolicyAdapterE3X_R1:
    source = Path(path)
    actual_sha = file_sha256(source)
    if actual_sha != expected_file_sha256:
        raise ValueError("Frozen policy file SHA-256 mismatch")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Frozen policy payload must be an object")
    if payload.get("policy_id") != expected_policy_id:
        raise ValueError("Frozen policy ID does not match the compatibility release")
    canonical = dict(payload)
    canonical.pop("policy_id", None)
    if canonical_sha256(canonical) != expected_policy_id:
        raise ValueError("Frozen policy canonical ID mismatch")
    item = dict(payload)
    if policy_type == "technical_retry":
        item["allowed_technical_failure_categories"] = tuple(
            item["allowed_technical_failure_categories"]
        )
        normalized = TechnicalRetryPolicyV4_1_2_R1(**item)
    elif policy_type == "process_cleanup":
        for field_name in (
            "campaign_owned_ports", "campaign_owned_lock_patterns",
            "campaign_owned_display_sessions", "required_target_checks",
        ):
            item[field_name] = tuple(item[field_name])
        normalized = ProcessCleanupPolicyV4_1_2_R1(**item)
    else:
        raise ValueError("Unknown frozen policy type")
    return FrozenPolicyAdapterE3X_R1(
        policy_type=policy_type,
        raw_policy_payload=payload,
        raw_file_sha256=actual_sha,
        raw_policy_id=expected_policy_id,
        authoring_source_commit=str(payload["source_commit"]),
        adapter_version=E3X_POLICY_ADAPTER_VERSION,
        normalized_runtime_view=normalized,
    ).with_id()


def require_policy_compatible(
    release: Round513E3PolicyCompatibilityReleaseR1,
    adapter: FrozenPolicyAdapterE3X_R1,
    *, execution_source: str,
) -> None:
    matches = [
        entry for entry in release.entries
        if entry.policy_type == adapter.policy_type
        and entry.policy_id == adapter.raw_policy_id
        and entry.file_sha256 == adapter.raw_file_sha256
        and entry.authoring_source_commit == adapter.authoring_source_commit
        and adapter.adapter_version in entry.allowed_runtime_adapter_versions
        and E3X_RUNTIME_SCHEMA in entry.allowed_runtime_schemas
        and execution_source in entry.allowed_execution_source_commits
    ]
    if len(matches) != 1:
        raise PermissionError("Frozen policy is not in the exact E3X compatibility allowlist")


def retry_semantics(policy: TechnicalRetryPolicyV4_1_2_R1, category: str) -> dict[str, Any]:
    allowed = category in policy.allowed_technical_failure_categories
    return {
        "category": category,
        "retry_permitted": allowed,
        "maximum_attempts": policy.total_maximum_attempts if allowed else 1,
        "maximum_attempts_per_category": (
            policy.maximum_attempts_per_technical_category if allowed else 1
        ),
        "stop_condition": (
            "budget_exhausted" if allowed else policy.unclassified_technical_failure_policy
        ),
        "quarantine_disposition": policy.technical_partial_record_disposition,
        "backoff_seconds": policy.backoff_seconds if allowed else 0,
    }


def cleanup_semantics(policy: ProcessCleanupPolicyV4_1_2_R1) -> dict[str, Any]:
    return {
        "candidate": policy.cleanup_candidate,
        "grace_seconds": policy.cleanup_grace_seconds,
        "target_checks": list(policy.required_target_checks),
        "ownership_ledger_required": policy.launch_ownership_ledger_required,
        "unrelated_process_kill_permitted": policy.unrelated_process_kill_permitted,
        "residual_process_policy": policy.residual_process_policy,
        "output_directory_policy": policy.output_directory_policy,
        "command_plan": [
            "signal_campaign_process_group",
            "wait_cleanup_grace_seconds",
            "verify_ownership_ledger_targets",
            "stop_if_campaign_owned_residual_remains",
        ],
    }


def validate_e3x_runtime_artifacts(
    *, binding: TrackERunBindingE3X_R1,
    compatibility: Round513E3ContractCompatibilityReleaseR1,
    policy_compatibility: Round513E3PolicyCompatibilityReleaseR1,
    runtime: CHRMLiteEngineeringSmokeRuntimeReleaseE3X_R1,
    manifest: CHRMLiteEngineeringSmokeExecutionManifestE3X_R1,
    retry_adapter: FrozenPolicyAdapterE3X_R1,
    cleanup_adapter: FrozenPolicyAdapterE3X_R1,
    scientific_adapters: Mapping[str, ContractRuntimeAdapterV4_1_2_R1],
    cli_output_root: str,
) -> None:
    if not all(
        item == binding.execution_source_commit
        for item in (compatibility.source_commit, policy_compatibility.source_commit, runtime.source_commit)
    ):
        raise ValueError("E3X execution source closure mismatch")
    expected_runtime = (
        runtime.contract_compatibility_release_id == compatibility.release_id
        and runtime.policy_compatibility_release_id == policy_compatibility.release_id
        and runtime.provider_request_policy_id == binding.provider_request_policy_id
        and runtime.planner_runtime_request_contract_id == binding.planner_runtime_request_contract_id
        and runtime.technical_retry_policy_id == binding.technical_retry_policy_id
        and runtime.process_cleanup_policy_id == binding.process_cleanup_policy_id
        and runtime.controller_id == binding.controller_id
        and runtime.evaluator_id == binding.evaluator_id
        and runtime.budget_profile_id == binding.budget_profile_id
        and runtime.release_id == binding.runtime_release_id
    )
    if not expected_runtime:
        raise ValueError("E3X Runtime/Binding Controller/Evaluator/Budget/Policy mismatch")
    if (
        binding.contract_compatibility_release_id != compatibility.release_id
        or binding.policy_compatibility_release_id != policy_compatibility.release_id
    ):
        raise ValueError("E3X compatibility release binding mismatch")
    require_policy_compatible(
        policy_compatibility, retry_adapter, execution_source=binding.execution_source_commit
    )
    require_policy_compatible(
        policy_compatibility, cleanup_adapter, execution_source=binding.execution_source_commit
    )
    if (
        retry_adapter.raw_policy_id != binding.technical_retry_policy_id
        or cleanup_adapter.raw_policy_id != binding.process_cleanup_policy_id
    ):
        raise ValueError("E3X policy ID mismatch")
    required_scientific = {
        "planner_schema", "rule_registry", "bilateral_retrieval_policy",
        "decision_record_schema", "step_outcome_registry", "instrumentation_release",
        "support_policy",
    }
    if set(scientific_adapters) != required_scientific:
        raise ValueError("E3X scientific adapter inventory is incomplete")
    for adapter in scientific_adapters.values():
        compatibility.require_scientific_contract(adapter, binding.execution_source_commit)
    ids = {name: item.raw_contract_id for name, item in scientific_adapters.items()}
    expected_ids = {
        "planner_schema": binding.planner_schema_id,
        "rule_registry": binding.rule_registry_id,
        "bilateral_retrieval_policy": binding.bilateral_policy_id,
        "decision_record_schema": binding.decision_record_schema_id,
        "step_outcome_registry": binding.step_outcome_registry_id,
        "instrumentation_release": binding.instrumentation_release_id,
    }
    if any(ids[name] != expected for name, expected in expected_ids.items()):
        raise ValueError("E3X scientific contract lineage mismatch")
    outcome = scientific_adapters["step_outcome_registry"].raw_contract_payload
    if (
        outcome["controller_contract_id"] != binding.controller_id
        or outcome["evaluator_contract_id"] != binding.evaluator_id
        or outcome["execution_budget_profile_id"] != binding.budget_profile_id
    ):
        raise ValueError("E3X Controller/Evaluator/Budget contract mismatch")
    pairs = (
        (manifest.execution_source_commit, binding.execution_source_commit),
        (manifest.run_binding_id, binding.binding_id),
        (manifest.authorization_input_id, binding.authorization_input_id),
        (manifest.authorization_input_file_sha256, binding.authorization_input_file_sha256),
        (manifest.authorization_receipt_id, binding.authorization_receipt_id),
        (manifest.authorization_receipt_file_sha256, binding.authorization_receipt_file_sha256),
        (manifest.approval_statement_sha256, binding.approval_statement_sha256),
        (manifest.assignment_seal_id, binding.assignment_seal_id),
        (manifest.ordered_assignment_root, binding.ordered_assignment_root),
        (manifest.assignment_id, binding.assignment_id),
        (manifest.contract_compatibility_release_id, binding.contract_compatibility_release_id),
        (manifest.policy_compatibility_release_id, binding.policy_compatibility_release_id),
        (manifest.runtime_release_id, binding.runtime_release_id),
        (manifest.technical_retry_policy_id, binding.technical_retry_policy_id),
        (manifest.process_cleanup_policy_id, binding.process_cleanup_policy_id),
        (manifest.controller_id, binding.controller_id),
        (manifest.evaluator_id, binding.evaluator_id),
        (manifest.budget_profile_id, binding.budget_profile_id),
        (manifest.seed, binding.seed),
        (manifest.output_root, binding.output_root),
        (manifest.gamma_candidate, binding.gamma_candidate),
        (manifest.gamma_cov_text, binding.gamma_cov_text),
        (manifest.gamma_minus_text, binding.gamma_minus_text),
        (manifest.gamma_plus_text, binding.gamma_plus_text),
        (str(Path(cli_output_root).resolve()), str(Path(binding.output_root).resolve())),
    )
    if any(left != right for left, right in pairs):
        raise ValueError("E3X Execution Manifest/Run Binding/CLI mismatch")


E3H_PREFLIGHT_ORDER = (
    "source_and_worktree",
    "authorization_closure",
    "raw_contract_identity_and_version",
    "compatibility_allowlist",
    "policy_provenance_and_semantics",
    "assignment_seal_and_order",
    "artifact_and_task_asset_bindings",
    "provider_preflight_eligibility",
    "task_preflight_eligibility",
    "execution_manifest_eligibility",
)
E3H_PREFLIGHT_ORDER_ID = canonical_sha256(E3H_PREFLIGHT_ORDER)


def execute_preflight_sequence(
    checks: Mapping[str, Any], *, provider_call: Any, minedojo_launch: Any
) -> None:
    """Run all frozen preflight checks before side-effect callbacks."""

    if set(checks) != set(E3H_PREFLIGHT_ORDER):
        raise ValueError("E3H preflight check inventory is incomplete")
    for name in E3H_PREFLIGHT_ORDER:
        checks[name]()
    provider_call()
    minedojo_launch()


@dataclass(frozen=True)
class Round513E3XAuthorizationSupersessionDecision(_Hashed):
    source_commit: str
    old_authorization_input_id: str
    old_authorization_input_file_sha256: str
    old_authorization_receipt_id: str
    old_authorization_receipt_file_sha256: str
    old_assignment_seal_id: str
    old_execution_source: str
    authorization_closure_audit_id: str
    runtime_semantics_audit_id: str
    blocked_manifest_id: str
    authorization_content_valid: bool = True
    execution_started: bool = False
    provider_preflight_started: bool = False
    minedojo_started: bool = False
    smoke_outcomes_observed: bool = False
    scientific_records_created: int = 0
    reusable_after_source_change: bool = False
    historical_objects_preserved: bool = True
    supersession_reason: str = "runtime_schema_source_hardening"
    schema_version: int = 1
    decision_id: str = ""

    _id_field = "decision_id"

    def __post_init__(self) -> None:
        if not self.authorization_content_valid or not self.historical_objects_preserved:
            raise ValueError("Historical Boundary B objects were not preserved")
        if any((
            self.execution_started, self.provider_preflight_started, self.minedojo_started,
            self.smoke_outcomes_observed, self.scientific_records_created,
            self.reusable_after_source_change,
        )):
            raise ValueError("Superseded Boundary B authorization crossed an execution boundary")
        if self.supersession_reason != "runtime_schema_source_hardening":
            raise ValueError("Unexpected E3X supersession reason")
        if self.decision_id and self.decision_id != self.compute_id():
            raise ValueError("E3X supersession decision canonical ID mismatch")


@dataclass(frozen=True)
class Round513E3HScopeAudit(_Hashed):
    source_commit: str
    changed_files: tuple[str, ...]
    allowed_change_categories: tuple[str, ...]
    frozen_object_identity_audit_root: str
    scientific_method_changed: bool
    smoke_scientific_payload_changed: bool
    runtime_contract_revision_only: bool
    provider_call_count: int
    minedojo_launch_count: int
    status: str
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        eligible = (
            bool(self.changed_files) and bool(self.allowed_change_categories)
            and not self.scientific_method_changed
            and not self.smoke_scientific_payload_changed
            and self.runtime_contract_revision_only
            and self.provider_call_count == self.minedojo_launch_count == 0
        )
        if self.status != ("PASS" if eligible else "BLOCKED"):
            raise ValueError("E3H scope audit conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("E3H scope audit canonical ID mismatch")


@dataclass(frozen=True)
class Round513E3HAssignmentDependencyAudit(_Hashed):
    source_commit: str
    old_assignments_id: str
    binds_source_commit: bool
    binds_runtime_release: bool
    binds_compatibility_release: bool
    binds_run_binding_schema: bool
    binds_policy_ids: bool
    dependency_case: str
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        runtime_bound = any((
            self.binds_source_commit, self.binds_runtime_release,
            self.binds_compatibility_release, self.binds_run_binding_schema,
            self.binds_policy_ids,
        ))
        if self.dependency_case != ("B" if runtime_bound else "A"):
            raise ValueError("Assignment dependency case is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Assignment dependency audit canonical ID mismatch")


SCIENTIFIC_ASSIGNMENT_FIELDS = (
    "namespace_id", "terminal_task", "formal_task_name", "formal_catalog_row_id",
    "task_path_label", "task_file_sha256", "difficulty", "target_action_family",
    "coverage_naturalness", "natural_action_coverage_eligible",
    "instrumentation_target_eligible", "observed_runtime_coverage", "seed_commitment",
    "seed", "order", "engineering_only", "formal_fitting_eligible",
    "channel_calibration_eligible", "CHRM_fitting_eligible",
    "CDT_identification_eligible", "holdout_eligible", "final_evaluation_eligible",
)


def smoke_scientific_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {name: payload[name] for name in SCIENTIFIC_ASSIGNMENT_FIELDS}


def smoke_scientific_payload_root(items: Sequence[Mapping[str, Any]]) -> str:
    return canonical_sha256([smoke_scientific_payload(item) for item in items])


@dataclass(frozen=True)
class SmokeScientificPayloadEquivalenceAuditE3X_R1(_Hashed):
    source_commit: str
    old_assignments_id: str
    new_assignments_id: str
    old_payload_root: str
    new_payload_root: str
    assignment_count: int
    task_changes: int
    seed_changes: int
    order_changes: int
    asset_changes: int
    proxy_changes: int
    eligibility_changes: int
    namespace_changes: int
    status: str
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        equivalent = (
            self.assignment_count == 9
            and self.old_payload_root == self.new_payload_root
            and not any((
                self.task_changes, self.seed_changes, self.order_changes, self.asset_changes,
                self.proxy_changes, self.eligibility_changes, self.namespace_changes,
            ))
        )
        if self.status != ("EQUIVALENT" if equivalent else "MISMATCH"):
            raise ValueError("E3X scientific payload equivalence conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("E3X scientific payload audit canonical ID mismatch")


@dataclass(frozen=True)
class SmokeAssignmentE3X_R1(_Hashed):
    contract_type: str
    contract_version: str
    source_commit: str
    namespace_id: str
    terminal_task: str
    formal_task_name: str
    formal_catalog_row_id: str
    task_path_label: str
    task_file_sha256: str
    difficulty: str
    target_action_family: str
    coverage_naturalness: str
    natural_action_coverage_eligible: bool
    instrumentation_target_eligible: bool
    observed_runtime_coverage: str
    seed_commitment: str
    seed: int
    order: int
    engineering_only: bool = True
    formal_fitting_eligible: bool = False
    channel_calibration_eligible: bool = False
    CHRM_fitting_eligible: bool = False
    CDT_identification_eligible: bool = False
    holdout_eligible: bool = False
    final_evaluation_eligible: bool = False
    schema_version: int = E3X_SCHEMA_VERSION
    assignment_id: str = ""

    _id_field = "assignment_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        if self.coverage_naturalness not in {"natural", "proxy_only"}:
            raise ValueError("Unknown E3X action coverage naturalness")
        if self.coverage_naturalness == "proxy_only" and self.natural_action_coverage_eligible:
            raise ValueError("Proxy-only E3X assignment claims natural coverage")
        if self.observed_runtime_coverage != "not_observed_before_execution":
            raise ValueError("Prospective E3X assignment fabricated observed coverage")
        eligibility = (
            self.formal_fitting_eligible, self.channel_calibration_eligible,
            self.CHRM_fitting_eligible, self.CDT_identification_eligible,
            self.holdout_eligible, self.final_evaluation_eligible,
        )
        if not self.engineering_only or any(eligibility):
            raise ValueError("E3X assignment entered a protected scientific split")
        if self.assignment_id and self.assignment_id != self.compute_id():
            raise ValueError("E3X assignment canonical ID mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeAssignmentsE3X_R1(_Hashed):
    contract_type: str
    contract_version: str
    source_commit: str
    namespace_id: str
    runtime_release_id: str
    contract_compatibility_release_id: str
    policy_compatibility_release_id: str
    run_binding_schema_id: str
    assignments: tuple[SmokeAssignmentE3X_R1, ...]
    fixed_before_outcomes: bool = True
    observed_coverage_can_expand_set: bool = False
    schema_version: int = E3X_SCHEMA_VERSION
    assignments_id: str = ""

    _id_field = "assignments_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        if len(self.assignments) != 9 or len({item.assignment_id for item in self.assignments}) != 9:
            raise ValueError("E3X requires nine unique assignments")
        if not self.fixed_before_outcomes or self.observed_coverage_can_expand_set:
            raise ValueError("E3X assignments are adaptive")
        if self.assignments_id and self.assignments_id != self.compute_id():
            raise ValueError("E3X assignments canonical ID mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["assignments"] = [item.to_dict() for item in self.assignments]
        return payload


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokePoolE3X_R1(_Hashed):
    contract_type: str
    contract_version: str
    source_commit: str
    namespace_id: str
    task_asset_audit_id: str
    proxy_policy: str
    assignment_count: int
    engineering_only: bool = True
    fitting_eligible: bool = False
    outcome_selected: bool = False
    schema_version: int = E3X_SCHEMA_VERSION
    pool_id: str = ""

    _id_field = "pool_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        if self.proxy_policy != "P1" or self.assignment_count != 9:
            raise ValueError("E3X pool changed approved assignment policy")
        if not self.engineering_only or self.fitting_eligible or self.outcome_selected:
            raise ValueError("E3X pool entered fitting or selected outcomes")
        if self.pool_id and self.pool_id != self.compute_id():
            raise ValueError("E3X pool canonical ID mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeExclusionAuditE3X_R1(_Hashed):
    contract_type: str
    contract_version: str
    source_commit: str
    assignments_id: str
    namespace_id: str
    protected_namespace_root: str
    acquisition_overlap_count: int
    historical_development_overlap_count: int
    previous_smoke_overlap_count: int
    future_formal_v412_overlap_count: int
    holdout_overlap_count: int
    final_overlap_count: int
    proof_method: str
    eligible: bool
    schema_version: int = E3X_SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        counts = (
            self.acquisition_overlap_count, self.historical_development_overlap_count,
            self.previous_smoke_overlap_count, self.future_formal_v412_overlap_count,
            self.holdout_overlap_count, self.final_overlap_count,
        )
        if any(counts) or not self.eligible:
            raise ValueError("E3X assignments overlap a protected split")
        if self.proof_method != "cryptographic_namespace_and_assignment_id_domain_separation":
            raise ValueError("Unknown E3X exclusion proof")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("E3X exclusion audit canonical ID mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeAssignmentSealE3X_R1(_Hashed):
    contract_type: str
    contract_version: str
    source_commit: str
    pool_id: str
    assignments_id: str
    assignments_root_sha256: str
    scientific_payload_root: str
    exclusion_audit_id: str
    contract_compatibility_release_id: str
    policy_compatibility_release_id: str
    runtime_release_id: str
    run_binding_schema_id: str
    execution_manifest_schema_id: str
    assignment_count: int
    proxy_policy: str
    permanently_engineering_only: bool = True
    fitting_ineligible: bool = True
    sealed: bool = True
    schema_version: int = E3X_SCHEMA_VERSION
    seal_id: str = ""

    _id_field = "seal_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        if self.assignment_count != 9 or self.proxy_policy != "P1":
            raise ValueError("E3X seal changed approved assignment policy")
        if not all((self.permanently_engineering_only, self.fitting_ineligible, self.sealed)):
            raise ValueError("E3X assignment seal is incomplete")
        if self.seal_id and self.seal_id != self.compute_id():
            raise ValueError("E3X assignment seal canonical ID mismatch")


@dataclass(frozen=True)
class RetryCleanupSemanticEquivalenceAudit(_Hashed):
    source_commit: str
    retry_policy_id: str
    cleanup_policy_id: str
    retry_policy_file_sha256: str
    cleanup_policy_file_sha256: str
    retry_authoring_source_commit: str
    cleanup_authoring_source_commit: str
    fixture_count: int
    classification_changes: int
    retry_decision_changes: int
    maximum_attempt_changes: int
    stop_condition_changes: int
    quarantine_disposition_changes: int
    cleanup_plan_changes: int
    status: str
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        changes = (
            self.classification_changes, self.retry_decision_changes,
            self.maximum_attempt_changes, self.stop_condition_changes,
            self.quarantine_disposition_changes, self.cleanup_plan_changes,
        )
        equivalent = self.fixture_count >= 5 and not any(changes)
        if self.status != ("EQUIVALENT" if equivalent else "MISMATCH"):
            raise ValueError("Retry/Cleanup semantic equivalence conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Retry/Cleanup audit canonical ID mismatch")


@dataclass(frozen=True)
class Round513E3HSourceHardeningAudit(_Hashed):
    source_commit: str
    scope_audit_id: str
    supersession_decision_id: str
    assignment_dependency_audit_id: str
    retry_cleanup_semantic_equivalence_audit_id: str
    github_actions_run_id: str
    github_actions_url: str
    github_actions_conclusion: str
    full_tests_passed: int
    full_tests_failed: int
    full_tests_skipped: int
    full_environment_tests_passed: int
    full_environment_tests_failed: int
    full_environment_tests_skipped: int
    snapshot_guard_passed: bool
    paper_memory_write_probe_rejected: bool
    secret_generated_artifact_scan_passed: bool
    e2h_historical_round_trip_passed: bool
    e3x_round_trip_passed: bool
    cross_version_masquerade_rejected: bool
    policy_exact_identity_passed: bool
    preflight_zero_side_effects_passed: bool
    provider_call_count: int
    minedojo_launch_count: int
    scientific_method_changed: bool
    smoke_scientific_payload_changed: bool
    runtime_contract_revision_only: bool
    status: str
    schema_version: int = 1
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        required = (
            self.snapshot_guard_passed, self.paper_memory_write_probe_rejected,
            self.secret_generated_artifact_scan_passed,
            self.e2h_historical_round_trip_passed, self.e3x_round_trip_passed,
            self.cross_version_masquerade_rejected, self.policy_exact_identity_passed,
            self.preflight_zero_side_effects_passed, self.runtime_contract_revision_only,
        )
        eligible = (
            all(required)
            and self.github_actions_conclusion == "success"
            and self.full_tests_passed > 0
            and self.full_environment_tests_passed > 0
            and not any((
                self.full_tests_failed, self.full_tests_skipped,
                self.full_environment_tests_failed, self.full_environment_tests_skipped,
                self.provider_call_count, self.minedojo_launch_count,
                self.scientific_method_changed, self.smoke_scientific_payload_changed,
            ))
        )
        if self.status != ("PASS" if eligible else "BLOCKED"):
            raise ValueError("E3H source-hardening conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("E3H source-hardening audit canonical ID mismatch")


E3H_AUTHORIZATION_DECLARATIONS = (
    "The prior Boundary B authorization was valid but retired before execution for runner source hardening.",
    "No Provider preflight, MineDojo construction, or scientific action started under the prior authorization.",
    "No Engineering Smoke outcome was observed.",
    "All nine tasks, seeds, order, task assets, and proxy semantics are unchanged.",
    "Planner, Controller, Memory, Candidate B, and the exact Gamma strings are unchanged.",
    "Retry and Cleanup Policy IDs and semantics are unchanged; only authoring-source validation was corrected.",
    "The new execution source changes only E3X contract loading and fail-closed preflight validation.",
    "Engineering Smoke records remain engineering-only and can never enter fitting or calibration.",
    "Scientific failures receive no retry.",
    "Evaluation before the original action remains disabled; CHRM and CDT are unfitted and action-inactive.",
    "Formal Development, Holdout, Final Evaluation, and Round 6 remain closed.",
    "Any new authorization applies only to the new E3H Source, Runtime, Binding, and Seal closure.",
)


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeAuthorizationInputE3X_R1(_Hashed):
    contract_type: str
    contract_version: str
    source_commit: str
    source_hardening_audit_id: str
    supersession_decision_id: str
    scope_audit_id: str
    assignment_dependency_audit_id: str
    scientific_payload_equivalence_audit_id: str
    retry_cleanup_semantic_equivalence_audit_id: str
    runtime_release_id: str
    contract_compatibility_release_id: str
    policy_compatibility_release_id: str
    run_binding_schema_id: str
    execution_manifest_schema_id: str
    provider_request_policy_id: str
    planner_runtime_request_contract_id: str
    planner_schema_id: str
    planner_prompt_id: str
    planner_parser_id: str
    formal_taskset_release_id: str
    formal_catalog_sha256: str
    namespace_id: str
    proxy_policy: str
    proxy_decision_input_id: str
    iron_ingot_asset_audit_id: str
    pool_id: str
    assignments_id: str
    exclusion_audit_id: str
    assignment_seal_id: str
    ordered_assignment_root: str
    paper_memory_release_id: str
    paper_memory_root: str
    mineclip_policy_id: str
    scene_exemplar_release_id: str
    rule_registry_id: str
    bilateral_policy_id: str
    decision_record_schema_id: str
    step_outcome_registry_id: str
    instrumentation_release_id: str
    controller_id: str
    evaluator_id: str
    budget_profile_id: str
    technical_retry_policy_id: str
    technical_retry_policy_file_sha256: str
    process_cleanup_policy_id: str
    process_cleanup_policy_file_sha256: str
    gamma_candidate: str
    gamma_cov_text: str
    gamma_minus_text: str
    gamma_plus_text: str
    declarations: tuple[str, ...]
    reauthorization_status: str = "pending"
    provider_preflight_permitted: bool = False
    minedojo_execution_permitted: bool = False
    formal_development_permitted: bool = False
    holdout_final_round6_permitted: bool = False
    schema_version: int = 1
    authorization_input_id: str = ""

    _id_field = "authorization_input_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        if self.declarations != E3H_AUTHORIZATION_DECLARATIONS:
            raise ValueError("E3H authorization declarations changed")
        if self.proxy_policy != "P1" or self.gamma_candidate != GAMMA_CANDIDATE_B:
            raise ValueError("E3H authorization changed proxy policy or Candidate B")
        if (self.gamma_cov_text, self.gamma_minus_text, self.gamma_plus_text) != GAMMA_TEXT:
            raise ValueError("E3H authorization changed exact Gamma strings")
        if self.reauthorization_status != "pending" or any((
            self.provider_preflight_permitted, self.minedojo_execution_permitted,
            self.formal_development_permitted, self.holdout_final_round6_permitted,
        )):
            raise ValueError("E3H authorization input crossed the Author Boundary")
        if self.authorization_input_id and self.authorization_input_id != self.compute_id():
            raise ValueError("E3H authorization input canonical ID mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeAuthorizationReceiptE3X_R1(_Hashed):
    contract_type: str
    contract_version: str
    source_commit: str
    authorization_input_id: str
    authorization_input_file_sha256: str
    source_hardening_audit_id: str
    runtime_release_id: str
    contract_compatibility_release_id: str
    policy_compatibility_release_id: str
    assignment_seal_id: str
    declarations_sha256: str
    declaration_count: int
    approval_statement_sha256: str
    approved_by: str
    provider_preflight_permitted: bool
    minedojo_execution_permitted: bool
    schema_version: int = E3X_SCHEMA_VERSION
    receipt_id: str = ""

    _id_field = "receipt_id"

    def __post_init__(self) -> None:
        _require_contract_header(
            contract_type=self.contract_type,
            expected_type=type(self).__name__,
            contract_version=self.contract_version,
            schema_version=self.schema_version,
        )
        if self.approved_by != "ZYF" or not all((
            self.provider_preflight_permitted, self.minedojo_execution_permitted
        )):
            raise PermissionError("E3X authorization receipt does not permit execution")
        if self.declaration_count != len(E3H_AUTHORIZATION_DECLARATIONS):
            raise ValueError("E3X authorization receipt declaration count mismatch")
        if self.declarations_sha256 != canonical_sha256(E3H_AUTHORIZATION_DECLARATIONS):
            raise ValueError("E3X authorization receipt declaration identity mismatch")
        if self.receipt_id and self.receipt_id != self.compute_id():
            raise ValueError("E3X authorization receipt canonical ID mismatch")


def validate_e3x_authorization_assignment_closure(
    *,
    authorization: CHRMLiteEngineeringSmokeAuthorizationInputE3X_R1,
    receipt: CHRMLiteEngineeringSmokeAuthorizationReceiptE3X_R1,
    assignments: CHRMLiteEngineeringSmokeAssignmentsE3X_R1,
    seal: CHRMLiteEngineeringSmokeAssignmentSealE3X_R1,
    binding: TrackERunBindingE3X_R1,
    task_path: str | Path,
) -> None:
    if not all(
        item == binding.execution_source_commit
        for item in (
            authorization.source_commit, receipt.source_commit,
            assignments.source_commit, seal.source_commit,
        )
    ):
        raise ValueError("E3X authorization/assignment source closure mismatch")
    pairs = (
        (receipt.authorization_input_id, authorization.authorization_input_id),
        (receipt.authorization_input_file_sha256, binding.authorization_input_file_sha256),
        (receipt.receipt_id, binding.authorization_receipt_id),
        (receipt.approval_statement_sha256, binding.approval_statement_sha256),
        (receipt.runtime_release_id, authorization.runtime_release_id),
        (receipt.contract_compatibility_release_id, authorization.contract_compatibility_release_id),
        (receipt.policy_compatibility_release_id, authorization.policy_compatibility_release_id),
        (receipt.assignment_seal_id, authorization.assignment_seal_id),
        (authorization.authorization_input_id, binding.authorization_input_id),
        (authorization.runtime_release_id, binding.runtime_release_id),
        (authorization.contract_compatibility_release_id, binding.contract_compatibility_release_id),
        (authorization.policy_compatibility_release_id, binding.policy_compatibility_release_id),
        (authorization.pool_id, binding.pool_id),
        (authorization.assignments_id, binding.assignments_id),
        (authorization.exclusion_audit_id, binding.exclusion_audit_id),
        (authorization.assignment_seal_id, binding.assignment_seal_id),
        (assignments.assignments_id, binding.assignments_id),
        (assignments.runtime_release_id, binding.runtime_release_id),
        (assignments.contract_compatibility_release_id, binding.contract_compatibility_release_id),
        (assignments.policy_compatibility_release_id, binding.policy_compatibility_release_id),
        (assignments.run_binding_schema_id, authorization.run_binding_schema_id),
        (seal.pool_id, binding.pool_id),
        (seal.assignments_id, binding.assignments_id),
        (seal.exclusion_audit_id, binding.exclusion_audit_id),
        (seal.runtime_release_id, binding.runtime_release_id),
        (seal.contract_compatibility_release_id, binding.contract_compatibility_release_id),
        (seal.policy_compatibility_release_id, binding.policy_compatibility_release_id),
        (seal.seal_id, binding.assignment_seal_id),
        (seal.assignments_root_sha256, binding.ordered_assignment_root),
    )
    if any(left != right for left, right in pairs):
        raise ValueError("E3X authorization/assignment binding mismatch")
    rows = tuple(sorted(assignments.assignments, key=lambda item: item.order))
    if tuple(item.order for item in rows) != tuple(range(9)):
        raise ValueError("E3X assignment order is not the frozen 0..8 sequence")
    if canonical_sha256([item.to_dict() for item in rows]) != seal.assignments_root_sha256:
        raise ValueError("E3X assignment ordered root mismatch")
    selected = [item for item in rows if item.assignment_id == binding.assignment_id]
    if len(selected) != 1:
        raise ValueError("E3X binding does not select exactly one frozen assignment")
    item = selected[0]
    if (
        item.terminal_task != binding.terminal_task
        or item.seed != binding.seed
        or item.seed_commitment != binding.seed_commitment
    ):
        raise ValueError("E3X selected task/seed binding mismatch")
    if file_sha256(task_path) != item.task_file_sha256:
        raise ValueError("E3X selected task asset SHA-256 mismatch")


_E3X_TYPES.update({
    "CHRMLiteEngineeringSmokeAuthorizationInputE3X_R1": (
        CHRMLiteEngineeringSmokeAuthorizationInputE3X_R1, "authorization_input_id"
    ),
    "CHRMLiteEngineeringSmokeAuthorizationReceiptE3X_R1": (
        CHRMLiteEngineeringSmokeAuthorizationReceiptE3X_R1, "receipt_id"
    ),
    "CHRMLiteEngineeringSmokeAssignmentsE3X_R1": (
        CHRMLiteEngineeringSmokeAssignmentsE3X_R1, "assignments_id"
    ),
    "CHRMLiteEngineeringSmokeAssignmentSealE3X_R1": (
        CHRMLiteEngineeringSmokeAssignmentSealE3X_R1, "seal_id"
    ),
})


def dataclass_contract_schema_id(cls: type, *, invariants: Mapping[str, Any]) -> str:
    return canonical_sha256({
        "class": cls.__name__,
        "fields": [item.name for item in fields(cls)],
        "invariants": dict(invariants),
    })
