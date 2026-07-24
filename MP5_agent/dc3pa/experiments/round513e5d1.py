"""Fail-closed runtime contracts for the Round 5.13E5 D1 diagnostics.

This module only adapts the already frozen E3 planner contract to the E5
diagnostic closure.  It does not change planner, controller, evaluator, memory,
retry, cleanup, Candidate B, or Gamma semantics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .round513_collection import CHRMLitePlannerOutputSchemaV4_1
from .round513e2h import ContractRuntimeAdapterV4_1_2_R1, file_sha256


CONTRACT_VERSION = "E5-D1-R1"
SCHEMA_VERSION = 1
DIAGNOSTIC_TASKS = ("mine sapling", "mine iron ore", "mine log")
CANDIDATE_B_ID = "0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f"
GAMMA_TEXT = ("1.0", "-0.01040883", "0.00744657")
E3_PLANNER_SCHEMA_ID = "15819bea54da489d711f61d2cdafae8dfa1008e3694f9c09280a7691cdca9681"
E3_PLANNER_PROMPT_ID = "b0107cfcd4856c2bea8f7e13f9757a7598719b63d756c2b24d1fb83f0346caa2"
E3_PLANNER_PARSER_ID = "24963aca08feaa9c90331faee2435cf5226052f689d3b4c41912c6ae04fd58bd"


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


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


def _require_source(source_commit: str) -> None:
    if len(source_commit) != 40 or any(ch not in "0123456789abcdef" for ch in source_commit):
        raise ValueError("E5 D1 requires an exact lowercase 40-character source commit")


def seed_from_commitment(commitment: str) -> int:
    if len(commitment) != 64:
        raise ValueError("E5 D1 seed commitment must be a SHA-256 value")
    seed = int(commitment[:8], 16) & 0x7FFFFFFF
    if seed <= 0:
        raise ValueError("E5 D1 commitment derived a non-positive seed")
    return seed


@dataclass(frozen=True)
class ScientificContractReferenceD1:
    contract_type: str
    filename: str
    contract_id: str
    file_sha256: str

    def __post_init__(self) -> None:
        if not all((self.contract_type, self.filename)):
            raise ValueError("E5 D1 scientific contract reference is incomplete")
        if len(self.contract_id) != 64 or len(self.file_sha256) != 64:
            raise ValueError("E5 D1 scientific contract reference has an invalid digest")


@dataclass(frozen=True)
class DiagnosticAssignmentD1(_Hashed):
    contract_type: str
    source_commit: str
    order: int
    formal_task: str
    runtime_task: str
    terminal_task: str
    difficulty: str
    asset: str
    asset_sha256: str
    seed_commitment: str
    seed_strategy_receipt_id: str
    e4_origin_assignment_id: str
    e4_origin_binding_id: str
    e4_origin_execution_source: str
    diagnostic_only: bool = True
    seed_value_published: bool = False
    formal_fitting_eligible: bool = False
    channel_calibration_eligible: bool = False
    chrm_fitting_eligible: bool = False
    cdt_identification_eligible: bool = False
    holdout_eligible: bool = False
    final_evaluation_eligible: bool = False
    assignment_id: str = ""

    _id_field = "assignment_id"

    def __post_init__(self) -> None:
        _require_source(self.source_commit)
        if self.contract_type != "Round513E5DiagnosticAssignmentD1R1":
            raise ValueError("Unknown E5 D1 assignment contract")
        if not self.diagnostic_only or self.seed_value_published:
            raise ValueError("E5 D1 assignment escaped diagnostic-only seed handling")
        if any((self.formal_fitting_eligible, self.channel_calibration_eligible,
                self.chrm_fitting_eligible, self.cdt_identification_eligible,
                self.holdout_eligible, self.final_evaluation_eligible)):
            raise ValueError("E5 D1 assignment entered a protected scientific phase")
        seed_from_commitment(self.seed_commitment)
        if self.assignment_id and self.assignment_id != self.compute_id():
            raise ValueError("E5 D1 assignment canonical ID mismatch")


@dataclass(frozen=True)
class DiagnosticAssignmentsD1(_Hashed):
    contract_type: str
    contract_version: str
    schema_version: int
    source_commit: str
    namespace: str
    seed_strategy_receipt_id: str
    rows: tuple[DiagnosticAssignmentD1, ...]
    assignment_count: int = 3
    plaintext_seeds_stored: bool = False
    minedojo_execution_permitted: bool = False
    assignments_id: str = ""

    _id_field = "assignments_id"

    def __post_init__(self) -> None:
        _require_source(self.source_commit)
        if (self.contract_type, self.contract_version, self.schema_version) != (
            "Round513E5DiagnosticAssignmentsD1R1", CONTRACT_VERSION, SCHEMA_VERSION
        ):
            raise ValueError("Unknown E5 D1 assignments contract")
        if self.assignment_count != 3 or len(self.rows) != 3:
            raise ValueError("E5 D1 requires exactly three assignments")
        if tuple(row.formal_task for row in self.rows) != DIAGNOSTIC_TASKS:
            raise ValueError("E5 D1 task order changed")
        if tuple(row.order for row in self.rows) != (0, 1, 2):
            raise ValueError("E5 D1 assignment order changed")
        if any(row.source_commit != self.source_commit for row in self.rows):
            raise ValueError("E5 D1 assignment/source closure mismatch")
        if self.plaintext_seeds_stored or self.minedojo_execution_permitted:
            raise ValueError("E5 D1 assignments opened execution or published seeds")
        if self.assignments_id and self.assignments_id != self.compute_id():
            raise ValueError("E5 D1 assignments canonical ID mismatch")


@dataclass(frozen=True)
class DiagnosticAssignmentSealD1(_Hashed):
    contract_type: str
    contract_version: str
    schema_version: int
    source_commit: str
    assignments_id: str
    seed_strategy_receipt_id: str
    ordered_assignment_root: str
    assignment_count: int = 3
    tasks_seeds_order_frozen: bool = True
    diagnostic_only: bool = True
    formal_fitting_eligible: bool = False
    full_9_assignment_rerun_permitted: bool = False
    minedojo_execution_permitted: bool = False
    seal_id: str = ""

    _id_field = "seal_id"

    def __post_init__(self) -> None:
        _require_source(self.source_commit)
        if (self.contract_type, self.contract_version, self.schema_version) != (
            "Round513E5DiagnosticAssignmentSealD1R1", CONTRACT_VERSION, SCHEMA_VERSION
        ):
            raise ValueError("Unknown E5 D1 assignment seal")
        if self.assignment_count != 3 or not self.tasks_seeds_order_frozen:
            raise ValueError("E5 D1 assignment seal is incomplete")
        if not self.diagnostic_only or any((self.formal_fitting_eligible,
                                            self.full_9_assignment_rerun_permitted,
                                            self.minedojo_execution_permitted)):
            raise ValueError("E5 D1 assignment seal opened an unauthorized phase")
        if self.seal_id and self.seal_id != self.compute_id():
            raise ValueError("E5 D1 assignment seal canonical ID mismatch")


@dataclass(frozen=True)
class DiagnosticRuntimeReleaseD1(_Hashed):
    contract_type: str
    contract_version: str
    schema_version: int
    source_commit: str
    prior_e5_runtime_release_id: str
    amendment_receipt_id: str
    planner_schema_id: str
    planner_prompt_id: str
    planner_parser_id: str
    rule_registry_id: str
    dependency_schema_id: str
    paper_memory_release_id: str
    scene_exemplar_release_id: str
    mineclip_policy_id: str
    controller_id: str
    evaluator_id: str
    budget_profile_id: str
    technical_retry_policy_id: str
    technical_retry_policy_file_sha256: str
    process_cleanup_policy_id: str
    process_cleanup_policy_file_sha256: str
    scientific_contracts: tuple[ScientificContractReferenceD1, ...]
    candidate_b_id: str = CANDIDATE_B_ID
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    memory_readonly: bool = True
    acquisition_writes: int = 0
    prompt_text_changed: bool = False
    parser_semantics_changed: bool = False
    minedojo_execution_permitted: bool = False
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        _require_source(self.source_commit)
        if (self.contract_type, self.contract_version, self.schema_version) != (
            "Round513E5DiagnosticRuntimeReleaseD1R1", CONTRACT_VERSION, SCHEMA_VERSION
        ):
            raise ValueError("Unknown E5 D1 runtime release")
        if (self.planner_schema_id, self.planner_prompt_id, self.planner_parser_id) != (
            E3_PLANNER_SCHEMA_ID, E3_PLANNER_PROMPT_ID, E3_PLANNER_PARSER_ID
        ):
            raise ValueError("E5 D1 did not bind the exact canonical E3 planner")
        if self.candidate_b_id != CANDIDATE_B_ID or self.gamma_text != GAMMA_TEXT:
            raise ValueError("E5 D1 changed Candidate B or Gamma")
        if not self.memory_readonly or self.acquisition_writes:
            raise ValueError("E5 D1 runtime opened Memory writes")
        if self.prompt_text_changed or self.parser_semantics_changed:
            raise ValueError("E5 D1 runtime changed planner semantics")
        if self.minedojo_execution_permitted:
            raise ValueError("Runtime release cannot itself authorize MineDojo")
        if len(self.technical_retry_policy_file_sha256) != 64 or len(self.process_cleanup_policy_file_sha256) != 64:
            raise ValueError("E5 D1 runtime policy raw SHA binding is incomplete")
        required = {"planner_schema", "rule_registry", "bilateral_retrieval_policy", "support_policy"}
        if not required.issubset({item.contract_type for item in self.scientific_contracts}):
            raise ValueError("E5 D1 runtime scientific contract inventory is incomplete")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("E5 D1 runtime release canonical ID mismatch")


@dataclass(frozen=True)
class DiagnosticAuthorizationInputD1(_Hashed):
    contract_type: str
    contract_version: str
    schema_version: int
    source_commit: str
    runtime_release_id: str
    assignments_id: str
    assignment_seal_id: str
    ordered_assignment_root: str
    pending_binding_root: str
    pending_execution_manifest_root: str
    amendment_receipt_id: str
    prior_authorization_input_id: str
    prior_authorization_receipt_id: str
    planner_schema_id: str
    planner_prompt_id: str
    planner_parser_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    paper_memory_release_id: str
    scene_exemplar_release_id: str
    mineclip_policy_id: str
    controller_id: str
    evaluator_id: str
    candidate_b_id: str = CANDIDATE_B_ID
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    authorized_task_order: tuple[str, ...] = DIAGNOSTIC_TASKS
    authorization_status: str = "pending_exact_zyf_authorization"
    minedojo_execution_permitted: bool = False
    full_9_assignment_rerun_permitted: bool = False
    authorization_input_id: str = ""

    _id_field = "authorization_input_id"

    def __post_init__(self) -> None:
        _require_source(self.source_commit)
        if (self.contract_type, self.contract_version, self.schema_version) != (
            "Round513E5DiagnosticAuthorizationInputD1R1", CONTRACT_VERSION, SCHEMA_VERSION
        ):
            raise ValueError("Unknown E5 D1 authorization input")
        if self.authorization_status != "pending_exact_zyf_authorization":
            raise ValueError("E5 D1 authorization input is not pending")
        if self.minedojo_execution_permitted or self.full_9_assignment_rerun_permitted:
            raise ValueError("E5 D1 authorization input opened execution")
        if self.authorized_task_order != DIAGNOSTIC_TASKS:
            raise ValueError("E5 D1 authorization task order changed")
        if (self.planner_schema_id, self.planner_prompt_id, self.planner_parser_id) != (
            E3_PLANNER_SCHEMA_ID, E3_PLANNER_PROMPT_ID, E3_PLANNER_PARSER_ID
        ):
            raise ValueError("E5 D1 authorization changed canonical planner lineage")
        if self.candidate_b_id != CANDIDATE_B_ID or self.gamma_text != GAMMA_TEXT:
            raise ValueError("E5 D1 authorization changed Candidate B or Gamma")
        if self.authorization_input_id and self.authorization_input_id != self.compute_id():
            raise ValueError("E5 D1 authorization input canonical ID mismatch")


@dataclass(frozen=True)
class DiagnosticAuthorizationReceiptD1(_Hashed):
    contract_type: str
    contract_version: str
    schema_version: int
    source_commit: str
    authorization_input_id: str
    authorization_input_file_sha256: str
    runtime_release_id: str
    assignment_seal_id: str
    authorized_task_order: tuple[str, ...]
    approved_by: str
    approval_statement_sha256: str
    diagnostic_only: bool = True
    minedojo_execution_authorized: bool = True
    full_9_assignment_rerun_permitted: bool = False
    source_change_permitted: bool = False
    receipt_id: str = ""

    _id_field = "receipt_id"

    def __post_init__(self) -> None:
        _require_source(self.source_commit)
        if (self.contract_type, self.contract_version, self.schema_version) != (
            "Round513E5DiagnosticAuthorizationReceiptD1R1", CONTRACT_VERSION, SCHEMA_VERSION
        ):
            raise ValueError("Unknown E5 D1 authorization receipt")
        if self.approved_by != "ZYF" or not self.diagnostic_only:
            raise PermissionError("E5 D1 receipt lacks exact author approval")
        if not self.minedojo_execution_authorized or self.full_9_assignment_rerun_permitted:
            raise PermissionError("E5 D1 receipt does not authorize only the diagnostics")
        if self.source_change_permitted or self.authorized_task_order != DIAGNOSTIC_TASKS:
            raise ValueError("E5 D1 receipt changed source or task order")
        if self.receipt_id and self.receipt_id != self.compute_id():
            raise ValueError("E5 D1 authorization receipt canonical ID mismatch")


@dataclass(frozen=True)
class DiagnosticRunBindingD1(_Hashed):
    contract_type: str
    contract_version: str
    schema_version: int
    execution_source_commit: str
    campaign_id: str
    run_id: str
    episode_id: str
    assignment_id: str
    assignment_order: int
    task: str
    terminal_task: str
    task_asset_sha256: str
    seed: int
    seed_commitment: str
    authorization_input_id: str
    authorization_receipt_id: str
    authorization_receipt_file_sha256: str
    runtime_release_id: str
    assignment_seal_id: str
    planner_schema_id: str
    planner_prompt_id: str
    planner_parser_id: str
    rule_registry_id: str
    dependency_schema_id: str
    paper_memory_release_id: str
    scene_exemplar_release_id: str
    mineclip_policy_id: str
    controller_id: str
    evaluator_id: str
    budget_profile_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    output_root: str
    candidate_b_id: str = CANDIDATE_B_ID
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    diagnostic_only: bool = True
    execution_authorized: bool = True
    binding_id: str = ""

    _id_field = "binding_id"

    @property
    def gamma_minus_text(self) -> str:
        return self.gamma_text[1]

    @property
    def gamma_plus_text(self) -> str:
        return self.gamma_text[2]

    def __post_init__(self) -> None:
        _require_source(self.execution_source_commit)
        if (self.contract_type, self.contract_version, self.schema_version) != (
            "Round513E5DiagnosticRunBindingD1R1", CONTRACT_VERSION, SCHEMA_VERSION
        ):
            raise ValueError("Unknown E5 D1 run binding")
        if not self.diagnostic_only or not self.execution_authorized:
            raise PermissionError("E5 D1 run binding is not execution-authorized")
        if self.seed != seed_from_commitment(self.seed_commitment):
            raise ValueError("E5 D1 run seed does not match its frozen commitment")
        if (self.planner_schema_id, self.planner_prompt_id, self.planner_parser_id) != (
            E3_PLANNER_SCHEMA_ID, E3_PLANNER_PROMPT_ID, E3_PLANNER_PARSER_ID
        ):
            raise ValueError("E5 D1 run binding changed canonical planner lineage")
        if self.candidate_b_id != CANDIDATE_B_ID or self.gamma_text != GAMMA_TEXT:
            raise ValueError("E5 D1 run binding changed Candidate B or Gamma")
        if self.binding_id and self.binding_id != self.compute_id():
            raise ValueError("E5 D1 run binding canonical ID mismatch")


@dataclass(frozen=True)
class DiagnosticExecutionManifestD1(_Hashed):
    contract_type: str
    contract_version: str
    schema_version: int
    execution_source_commit: str
    binding_id: str
    authorization_receipt_id: str
    runtime_release_id: str
    assignment_seal_id: str
    assignment_id: str
    assignment_order: int
    task: str
    task_asset_sha256: str
    seed_commitment: str
    output_root: str
    diagnostic_only: bool = True
    minedojo_execution_permitted: bool = True
    scientific_success_retries: int = 0
    scientific_failure_retries: int = 0
    manifest_id: str = ""

    _id_field = "manifest_id"

    def __post_init__(self) -> None:
        _require_source(self.execution_source_commit)
        if (self.contract_type, self.contract_version, self.schema_version) != (
            "Round513E5DiagnosticExecutionManifestD1R1", CONTRACT_VERSION, SCHEMA_VERSION
        ):
            raise ValueError("Unknown E5 D1 execution manifest")
        if not self.diagnostic_only or not self.minedojo_execution_permitted:
            raise PermissionError("E5 D1 manifest does not authorize diagnostic execution")
        if self.scientific_success_retries or self.scientific_failure_retries:
            raise ValueError("E5 D1 manifest permits scientific retries")
        if self.manifest_id and self.manifest_id != self.compute_id():
            raise ValueError("E5 D1 execution manifest canonical ID mismatch")


_CONTRACT_TYPES: dict[str, tuple[type[_Hashed], str]] = {
    "Round513E5DiagnosticAssignmentsD1R1": (DiagnosticAssignmentsD1, "assignments_id"),
    "Round513E5DiagnosticAssignmentSealD1R1": (DiagnosticAssignmentSealD1, "seal_id"),
    "Round513E5DiagnosticRuntimeReleaseD1R1": (DiagnosticRuntimeReleaseD1, "release_id"),
    "Round513E5DiagnosticAuthorizationInputD1R1": (DiagnosticAuthorizationInputD1, "authorization_input_id"),
    "Round513E5DiagnosticAuthorizationReceiptD1R1": (DiagnosticAuthorizationReceiptD1, "receipt_id"),
    "Round513E5DiagnosticRunBindingD1R1": (DiagnosticRunBindingD1, "binding_id"),
    "Round513E5DiagnosticExecutionManifestD1R1": (DiagnosticExecutionManifestD1, "manifest_id"),
}


def contract_from_mapping(payload: Mapping[str, Any]) -> _Hashed:
    item = dict(payload)
    contract_type = str(item.get("contract_type", ""))
    if contract_type not in _CONTRACT_TYPES:
        raise ValueError("Unknown E5 D1 contract type")
    if contract_type == "Round513E5DiagnosticAssignmentsD1R1":
        item["rows"] = tuple(DiagnosticAssignmentD1(**row) for row in item["rows"])
    elif contract_type == "Round513E5DiagnosticRuntimeReleaseD1R1":
        item["scientific_contracts"] = tuple(
            ScientificContractReferenceD1(**entry) for entry in item["scientific_contracts"]
        )
        item["gamma_text"] = tuple(item["gamma_text"])
    elif contract_type in {
        "Round513E5DiagnosticAuthorizationInputD1R1",
        "Round513E5DiagnosticRunBindingD1R1",
    }:
        item["gamma_text"] = tuple(item["gamma_text"])
        if "authorized_task_order" in item:
            item["authorized_task_order"] = tuple(item["authorized_task_order"])
    elif contract_type == "Round513E5DiagnosticAuthorizationReceiptD1R1":
        item["authorized_task_order"] = tuple(item["authorized_task_order"])
    cls, _ = _CONTRACT_TYPES[contract_type]
    return cls(**item)


def load_d1_contract(
    path: Path,
    *,
    expected_file_sha256: str,
    expected_contract_id: str,
) -> _Hashed:
    actual_file_sha = file_sha256(path)
    if actual_file_sha != expected_file_sha256:
        raise ValueError("E5 D1 raw file SHA-256 mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("E5 D1 contract payload must be an object")
    contract = contract_from_mapping(payload)
    _, id_field = _CONTRACT_TYPES[str(payload["contract_type"])]
    if getattr(contract, id_field) != expected_contract_id:
        raise ValueError("E5 D1 expected contract ID mismatch")
    return contract


def adapt_e3_canonical_planner(
    adapter: ContractRuntimeAdapterV4_1_2_R1,
) -> CHRMLitePlannerOutputSchemaV4_1:
    if adapter.contract_type != "planner_schema" or adapter.raw_contract_id != E3_PLANNER_SCHEMA_ID:
        raise ValueError("E5 D1 planner adapter did not load the exact E3 schema")
    schema = CHRMLitePlannerOutputSchemaV4_1(**dict(adapter.raw_contract_payload))
    if (schema.schema_id, schema.prompt_id, schema.parser_id) != (
        E3_PLANNER_SCHEMA_ID, E3_PLANNER_PROMPT_ID, E3_PLANNER_PARSER_ID
    ):
        raise ValueError("E5 D1 canonical planner metadata mismatch")
    return schema


def validate_d1_execution_closure(
    *,
    current_source: str,
    task_path: Path,
    output_root: Path,
    binding: DiagnosticRunBindingD1,
    authorization: DiagnosticAuthorizationInputD1,
    receipt: DiagnosticAuthorizationReceiptD1,
    assignments: DiagnosticAssignmentsD1,
    seal: DiagnosticAssignmentSealD1,
    runtime: DiagnosticRuntimeReleaseD1,
    manifest: DiagnosticExecutionManifestD1,
    authorization_input_file_sha256: str,
) -> DiagnosticAssignmentD1:
    sources = {
        binding.execution_source_commit, authorization.source_commit, receipt.source_commit,
        assignments.source_commit, seal.source_commit, runtime.source_commit,
        manifest.execution_source_commit,
    }
    if sources != {current_source}:
        raise ValueError("E5 D1 source closure mismatch")
    ordered_root = canonical_sha256([row.assignment_id for row in assignments.rows])
    if seal.assignments_id != assignments.assignments_id or seal.ordered_assignment_root != ordered_root:
        raise ValueError("E5 D1 assignments/seal closure mismatch")
    if authorization.assignments_id != assignments.assignments_id:
        raise ValueError("E5 D1 authorization/assignments mismatch")
    if authorization.assignment_seal_id != seal.seal_id:
        raise ValueError("E5 D1 authorization/seal mismatch")
    if authorization.ordered_assignment_root != ordered_root:
        raise ValueError("E5 D1 authorization order root mismatch")
    if receipt.authorization_input_id != authorization.authorization_input_id:
        raise ValueError("E5 D1 authorization input/receipt mismatch")
    if receipt.authorization_input_file_sha256 != authorization_input_file_sha256:
        raise ValueError("E5 D1 authorization raw file SHA mismatch")
    if receipt.runtime_release_id != runtime.release_id or receipt.assignment_seal_id != seal.seal_id:
        raise ValueError("E5 D1 receipt runtime/seal mismatch")
    if binding.authorization_input_id != authorization.authorization_input_id:
        raise ValueError("E5 D1 binding authorization input mismatch")
    if binding.authorization_receipt_id != receipt.receipt_id:
        raise ValueError("E5 D1 binding authorization receipt mismatch")
    if binding.runtime_release_id != runtime.release_id or binding.assignment_seal_id != seal.seal_id:
        raise ValueError("E5 D1 binding runtime/seal mismatch")
    if manifest.binding_id != binding.binding_id or manifest.authorization_receipt_id != receipt.receipt_id:
        raise ValueError("E5 D1 manifest binding/receipt mismatch")
    if manifest.runtime_release_id != runtime.release_id or manifest.assignment_seal_id != seal.seal_id:
        raise ValueError("E5 D1 manifest runtime/seal mismatch")
    if Path(binding.output_root).resolve() != output_root.resolve() or Path(manifest.output_root).resolve() != output_root.resolve():
        raise ValueError("E5 D1 output root mismatch")
    selected = tuple(row for row in assignments.rows if row.assignment_id == binding.assignment_id)
    if len(selected) != 1:
        raise ValueError("E5 D1 binding does not select exactly one assignment")
    assignment = selected[0]
    if (binding.assignment_order, binding.task, binding.terminal_task,
        binding.seed_commitment, binding.task_asset_sha256) != (
        assignment.order, assignment.runtime_task, assignment.terminal_task,
        assignment.seed_commitment, assignment.asset_sha256,
    ):
        raise ValueError("E5 D1 selected assignment binding mismatch")
    if (manifest.assignment_id, manifest.assignment_order, manifest.task,
        manifest.seed_commitment, manifest.task_asset_sha256) != (
        assignment.assignment_id, assignment.order, assignment.runtime_task,
        assignment.seed_commitment, assignment.asset_sha256,
    ):
        raise ValueError("E5 D1 selected assignment manifest mismatch")
    if file_sha256(task_path) != assignment.asset_sha256:
        raise ValueError("E5 D1 task asset SHA-256 mismatch")
    runtime_ids = (
        runtime.planner_schema_id, runtime.planner_prompt_id, runtime.planner_parser_id,
        runtime.paper_memory_release_id, runtime.scene_exemplar_release_id,
        runtime.mineclip_policy_id, runtime.controller_id, runtime.evaluator_id,
        runtime.technical_retry_policy_id, runtime.process_cleanup_policy_id,
    )
    binding_ids = (
        binding.planner_schema_id, binding.planner_prompt_id, binding.planner_parser_id,
        binding.paper_memory_release_id, binding.scene_exemplar_release_id,
        binding.mineclip_policy_id, binding.controller_id, binding.evaluator_id,
        binding.technical_retry_policy_id, binding.process_cleanup_policy_id,
    )
    if runtime_ids != binding_ids:
        raise ValueError("E5 D1 runtime/binding scientific lineage mismatch")
    return assignment
