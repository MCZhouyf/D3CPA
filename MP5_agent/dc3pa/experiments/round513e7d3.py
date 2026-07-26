"""Round 5.13E7 D3 tree-only diagnostic contracts.

These contracts are a narrow execution closure for the author-selected
T3+I1 outcome: replay only the tree/sapling boundary plus the log positive
control.  Iron ore is closed by policy and is intentionally not executable
through this D3 closure.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .round513e5d1 import ScientificContractReferenceD1, seed_from_commitment
from .round513e6d2 import CANDIDATE_B_ID, GAMMA_TEXT


D3_TASK_ORDER = ("mine sapling", "mine log")
D3_ALLOWED_RUNTIME_TASKS = ("sapling", "log")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
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
        return {**item.payload_without_id(), self._id_field: getattr(item, self._id_field)}


@dataclass(frozen=True)
class D3TreeDiagnosticAssignment:
    order: int
    formal_task: str
    runtime_task: str
    terminal_task: str
    task_asset: str
    task_asset_sha256: str
    seed_commitment: str
    d2_origin_assignment_id: str
    d2_origin_record_hash: str
    diagnostic_path_id: str
    paired_replay: bool = True
    independent_sample: bool = False
    engineering_diagnostic_only: bool = True
    fitting_eligible: bool = False
    calibration_eligible: bool = False
    holdout_eligible: bool = False
    final_evaluation_eligible: bool = False
    assignment_id: str = ""

    def __post_init__(self) -> None:
        if self.runtime_task not in D3_ALLOWED_RUNTIME_TASKS:
            raise ValueError("D3 tree-only assignment cannot include non-tree tasks")
        if self.formal_task != f"mine {self.runtime_task}":
            raise ValueError("D3 formal/runtime task mismatch")
        if self.terminal_task != self.runtime_task:
            raise ValueError("D3 terminal task must match runtime task")
        if not self.diagnostic_path_id.startswith("d3_tree_"):
            raise ValueError("D3 diagnostic path must be tree-only")
        if any(
            (
                not self.paired_replay,
                self.independent_sample,
                not self.engineering_diagnostic_only,
                self.fitting_eligible,
                self.calibration_eligible,
                self.holdout_eligible,
                self.final_evaluation_eligible,
            )
        ):
            raise ValueError("D3 assignment crossed its engineering-only boundary")
        if self.assignment_id and self.assignment_id != self.compute_id():
            raise ValueError("D3 assignment ID mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("assignment_id", None)
        return payload

    def compute_id(self) -> str:
        return canonical_sha256(self.payload_without_id())

    def with_id(self):
        return replace(self, assignment_id=self.compute_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.assignment_id else self.with_id()
        return {**item.payload_without_id(), "assignment_id": item.assignment_id}


@dataclass(frozen=True)
class D3TreeDiagnosticAssignments(_Hashed):
    source_commit: str
    semantic_decision_receipt_id: str
    d3_blueprint_id: str
    d2_execution_source_commit: str
    rows: tuple[D3TreeDiagnosticAssignment, ...]
    paired_replay_only: bool = True
    iron_ore_replay_permitted: bool = False
    full_nine_assignment_rerun_permitted: bool = False
    plaintext_seeds_stored: bool = False
    minedojo_execution_permitted: bool = False
    assignments_id: str = ""

    _id_field = "assignments_id"

    def __post_init__(self) -> None:
        if tuple(row.formal_task for row in self.rows) != D3_TASK_ORDER:
            raise ValueError("D3 tree-only task order must be sapling then log")
        if any(row.runtime_task == "iron ore" for row in self.rows):
            raise ValueError("D3 tree-only assignments cannot include iron ore")
        if any(
            (
                not self.paired_replay_only,
                self.iron_ore_replay_permitted,
                self.full_nine_assignment_rerun_permitted,
                self.plaintext_seeds_stored,
                self.minedojo_execution_permitted,
            )
        ):
            raise ValueError("D3 assignments cannot authorize execution or non-tree replay")
        if self.assignments_id and self.assignments_id != self.compute_id():
            raise ValueError("D3 assignments ID mismatch")


@dataclass(frozen=True)
class D3TreeDiagnosticSeal(_Hashed):
    source_commit: str
    assignments_id: str
    ordered_assignment_root: str
    selected_tree_wood_option: str = "T3"
    selected_iron_ore_option: str = "I1"
    paired_replay_only: bool = True
    iron_ore_replay_permitted: bool = False
    full_nine_assignment_rerun_permitted: bool = False
    minedojo_execution_permitted: bool = False
    seal_id: str = ""

    _id_field = "seal_id"

    def __post_init__(self) -> None:
        if (self.selected_tree_wood_option, self.selected_iron_ore_option) != ("T3", "I1"):
            raise ValueError("D3 seal must bind the author-selected T3+I1 decision")
        if any(
            (
                not self.paired_replay_only,
                self.iron_ore_replay_permitted,
                self.full_nine_assignment_rerun_permitted,
                self.minedojo_execution_permitted,
            )
        ):
            raise ValueError("D3 seal crossed the tree-only boundary")
        if self.seal_id and self.seal_id != self.compute_id():
            raise ValueError("D3 seal ID mismatch")


@dataclass(frozen=True)
class D3TreeDiagnosticRuntimeRelease(_Hashed):
    source_commit: str
    parent_e7_manifest_id: str
    semantic_decision_receipt_id: str
    d3_blueprint_id: str
    outcome_schema_id: str
    find_contract_id: str
    safety_semantics_audit_id: str
    safety_policy_id: str
    signature_registry_id: str
    scene_compatibility_audit_id: str
    planner_schema_id: str
    planner_prompt_id: str
    planner_parser_id: str
    rule_registry_id: str
    dependency_schema_id: str
    budget_profile_id: str
    technical_retry_policy_id: str
    technical_retry_policy_file_sha256: str
    process_cleanup_policy_id: str
    process_cleanup_policy_file_sha256: str
    paper_memory_release_id: str
    scene_exemplar_release_id: str
    mineclip_policy_id: str
    controller_id: str
    evaluator_id: str
    scientific_contracts: tuple[ScientificContractReferenceD1, ...]
    candidate_b_id: str = CANDIDATE_B_ID
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    memory_readonly: bool = True
    acquisition_writes: int = 0
    evaluation_before_action_calls: int = 0
    iron_ore_replay_permitted: bool = False
    minedojo_execution_permitted: bool = False
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        if self.candidate_b_id != CANDIDATE_B_ID or self.gamma_text != GAMMA_TEXT:
            raise ValueError("D3 runtime changed Candidate B or Gamma")
        if not self.memory_readonly or self.acquisition_writes or self.evaluation_before_action_calls:
            raise ValueError("D3 runtime changed Memory/Evaluation isolation")
        if self.iron_ore_replay_permitted or self.minedojo_execution_permitted:
            raise ValueError("D3 runtime cannot authorize execution or iron replay")
        required = {"planner_schema", "rule_registry", "bilateral_retrieval_policy", "support_policy"}
        if not required.issubset({item.contract_type for item in self.scientific_contracts}):
            raise ValueError("D3 runtime scientific contract inventory is incomplete")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("D3 runtime release ID mismatch")


@dataclass(frozen=True)
class D3TreeDiagnosticAuthorizationInput(_Hashed):
    source_commit: str
    runtime_release_id: str
    semantic_decision_receipt_id: str
    d3_blueprint_id: str
    assignments_id: str
    assignment_seal_id: str
    ordered_assignment_root: str
    pending_binding_root: str
    pending_execution_manifest_root: str
    planner_schema_id: str
    planner_prompt_id: str
    planner_parser_id: str
    controller_id: str
    evaluator_id: str
    paper_memory_release_id: str
    scene_exemplar_release_id: str
    mineclip_policy_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    declarations: tuple[str, ...] = (
        "D3 executes only the author-selected T3 tree/sapling semantic diagnostic.",
        "Iron ore is closed by I1 policy and is not replayed.",
        "D3 is an engineering diagnostic paired to D2 records, not an independent scientific sample.",
        "D1/D2 historical records and labels remain immutable.",
        "No full nine-assignment rerun is permitted.",
        "Candidate B and Gamma remain unchanged.",
        "Paper Memory remains read-only and Acquisition writes remain zero.",
        "Holdout, Final Evaluation, and Round 6 remain closed.",
    )
    selected_tree_wood_option: str = "T3"
    selected_iron_ore_option: str = "I1"
    authorization_status: str = "pending_exact_zyf_authorization"
    d3_execution_permitted: bool = False
    minedojo_launch_count: int = 0
    authorization_input_id: str = ""

    _id_field = "authorization_input_id"

    def __post_init__(self) -> None:
        if (self.selected_tree_wood_option, self.selected_iron_ore_option) != ("T3", "I1"):
            raise ValueError("D3 authorization input must bind T3+I1")
        if self.authorization_status != "pending_exact_zyf_authorization":
            raise ValueError("D3 authorization input is not pending")
        if self.d3_execution_permitted or self.minedojo_launch_count:
            raise ValueError("D3 authorization input cannot self-authorize")
        if self.authorization_input_id and self.authorization_input_id != self.compute_id():
            raise ValueError("D3 authorization input ID mismatch")


@dataclass(frozen=True)
class D3TreeDiagnosticAuthorizationReceiptR1(_Hashed):
    source_commit: str
    authorization_input_id: str
    authorization_input_file_sha256: str
    runtime_release_id: str
    assignment_seal_id: str
    authorized_task_order: tuple[str, ...]
    approved_by: str
    approval_statement_sha256: str
    contract_kind: str = "Round513D3TreeDiagnosticAuthorizationReceiptR1"
    diagnostic_only: bool = True
    paired_replay_only: bool = True
    independent_sample: bool = False
    iron_ore_replay_authorized: bool = False
    minedojo_execution_authorized: bool = True
    full_nine_assignment_rerun_permitted: bool = False
    development_or_holdout_permitted: bool = False
    source_change_permitted: bool = False
    receipt_id: str = ""

    _id_field = "receipt_id"

    def __post_init__(self) -> None:
        if self.contract_kind != "Round513D3TreeDiagnosticAuthorizationReceiptR1":
            raise ValueError("Unknown D3 authorization receipt contract")
        if self.approved_by != "ZYF" or not self.minedojo_execution_authorized:
            raise PermissionError("D3 receipt lacks exact author execution approval")
        if self.authorized_task_order != D3_TASK_ORDER:
            raise ValueError("D3 receipt must authorize only sapling then log")
        if any(
            (
                not self.diagnostic_only,
                not self.paired_replay_only,
                self.independent_sample,
                self.iron_ore_replay_authorized,
                self.full_nine_assignment_rerun_permitted,
                self.development_or_holdout_permitted,
                self.source_change_permitted,
            )
        ):
            raise PermissionError("D3 receipt opened a forbidden boundary")
        if self.receipt_id and self.receipt_id != self.compute_id():
            raise ValueError("D3 receipt ID mismatch")


@dataclass(frozen=True)
class D3TreeDiagnosticRunBindingR1(_Hashed):
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
    outcome_schema_id: str
    find_contract_id: str
    safety_policy_id: str
    signature_registry_id: str
    scene_compatibility_audit_id: str
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
    contract_kind: str = "Round513D3TreeDiagnosticRunBindingR1"
    candidate_b_id: str = CANDIDATE_B_ID
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    diagnostic_only: bool = True
    paired_replay_only: bool = True
    independent_sample: bool = False
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
        if self.contract_kind != "Round513D3TreeDiagnosticRunBindingR1":
            raise ValueError("Unknown D3 run binding contract")
        if self.task not in D3_ALLOWED_RUNTIME_TASKS:
            raise ValueError("D3 run binding cannot execute non-tree tasks")
        if not self.diagnostic_only or not self.paired_replay_only or self.independent_sample or not self.execution_authorized:
            raise PermissionError("D3 run binding is not tree-diagnostic authorized")
        if self.seed != seed_from_commitment(self.seed_commitment):
            raise ValueError("D3 run seed does not match its frozen commitment")
        if self.candidate_b_id != CANDIDATE_B_ID or self.gamma_text != GAMMA_TEXT:
            raise ValueError("D3 run binding changed Candidate B or Gamma")
        if self.binding_id and self.binding_id != self.compute_id():
            raise ValueError("D3 run binding ID mismatch")


@dataclass(frozen=True)
class D3TreeDiagnosticExecutionManifestR1(_Hashed):
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
    contract_kind: str = "Round513D3TreeDiagnosticExecutionManifestR1"
    diagnostic_only: bool = True
    paired_replay_only: bool = True
    independent_sample: bool = False
    minedojo_execution_permitted: bool = True
    scientific_success_retries: int = 0
    scientific_failure_retries: int = 0
    manifest_id: str = ""

    _id_field = "manifest_id"

    def __post_init__(self) -> None:
        if self.contract_kind != "Round513D3TreeDiagnosticExecutionManifestR1":
            raise ValueError("Unknown D3 execution manifest contract")
        if self.task not in D3_ALLOWED_RUNTIME_TASKS:
            raise ValueError("D3 execution manifest cannot execute non-tree tasks")
        if not self.diagnostic_only or not self.paired_replay_only or self.independent_sample:
            raise PermissionError("D3 manifest is not paired-diagnostic only")
        if not self.minedojo_execution_permitted:
            raise PermissionError("D3 manifest does not authorize MineDojo")
        if self.scientific_success_retries or self.scientific_failure_retries:
            raise ValueError("D3 manifest permits scientific retries")
        if self.manifest_id and self.manifest_id != self.compute_id():
            raise ValueError("D3 execution manifest ID mismatch")


_D3_CONTRACT_TYPES: dict[str, tuple[type[_Hashed], str]] = {
    "assignments": (D3TreeDiagnosticAssignments, "assignments_id"),
    "assignment_seal": (D3TreeDiagnosticSeal, "seal_id"),
    "runtime": (D3TreeDiagnosticRuntimeRelease, "release_id"),
    "authorization_input": (D3TreeDiagnosticAuthorizationInput, "authorization_input_id"),
    "authorization_receipt": (D3TreeDiagnosticAuthorizationReceiptR1, "receipt_id"),
    "binding": (D3TreeDiagnosticRunBindingR1, "binding_id"),
    "execution_manifest": (D3TreeDiagnosticExecutionManifestR1, "manifest_id"),
}


def d3_contract_from_mapping(contract_kind: str, payload: Mapping[str, Any]) -> _Hashed:
    if contract_kind not in _D3_CONTRACT_TYPES:
        raise ValueError("Unknown D3 contract kind")
    item = dict(payload)
    if contract_kind == "assignments":
        item["rows"] = tuple(D3TreeDiagnosticAssignment(**row) for row in item["rows"])
    elif contract_kind == "runtime":
        item["scientific_contracts"] = tuple(
            ScientificContractReferenceD1(**entry) for entry in item["scientific_contracts"]
        )
        item["gamma_text"] = tuple(item["gamma_text"])
    elif contract_kind == "binding":
        item["gamma_text"] = tuple(item["gamma_text"])
    elif contract_kind == "authorization_input":
        item["declarations"] = tuple(item["declarations"])
    elif contract_kind == "authorization_receipt":
        item["authorized_task_order"] = tuple(item["authorized_task_order"])
    cls, _ = _D3_CONTRACT_TYPES[contract_kind]
    return cls(**item)


def load_d3_contract(
    path: Path,
    *,
    contract_kind: str,
    expected_file_sha256: str,
    expected_contract_id: str,
) -> _Hashed:
    if file_sha256(path) != expected_file_sha256:
        raise ValueError("D3 raw file SHA-256 mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("D3 contract payload must be an object")
    contract = d3_contract_from_mapping(contract_kind, payload)
    _, id_field = _D3_CONTRACT_TYPES[contract_kind]
    if getattr(contract, id_field) != expected_contract_id:
        raise ValueError("D3 expected contract ID mismatch")
    return contract


def validate_d3_execution_closure(
    *,
    current_source: str,
    task_path: Path,
    output_root: Path,
    binding: D3TreeDiagnosticRunBindingR1,
    authorization: D3TreeDiagnosticAuthorizationInput,
    receipt: D3TreeDiagnosticAuthorizationReceiptR1,
    assignments: D3TreeDiagnosticAssignments,
    seal: D3TreeDiagnosticSeal,
    runtime: D3TreeDiagnosticRuntimeRelease,
    manifest: D3TreeDiagnosticExecutionManifestR1,
    authorization_input_file_sha256: str,
    authorization_receipt_file_sha256: str,
) -> D3TreeDiagnosticAssignment:
    sources = {
        binding.execution_source_commit,
        authorization.source_commit,
        receipt.source_commit,
        assignments.source_commit,
        seal.source_commit,
        runtime.source_commit,
        manifest.execution_source_commit,
    }
    if sources != {current_source}:
        raise ValueError("D3 source closure mismatch")
    ordered_root = canonical_sha256([row.assignment_id for row in assignments.rows])
    if seal.assignments_id != assignments.assignments_id or seal.ordered_assignment_root != ordered_root:
        raise ValueError("D3 assignments/seal closure mismatch")
    if (authorization.assignments_id, authorization.assignment_seal_id, authorization.ordered_assignment_root) != (
        assignments.assignments_id, seal.seal_id, ordered_root
    ):
        raise ValueError("D3 authorization assignment closure mismatch")
    if authorization.runtime_release_id != runtime.release_id:
        raise ValueError("D3 authorization/runtime release mismatch")
    if receipt.authorization_input_id != authorization.authorization_input_id:
        raise ValueError("D3 authorization input/receipt mismatch")
    if receipt.authorization_input_file_sha256 != authorization_input_file_sha256:
        raise ValueError("D3 authorization raw file SHA mismatch")
    if binding.authorization_receipt_file_sha256 != authorization_receipt_file_sha256:
        raise ValueError("D3 authorization receipt raw file SHA mismatch")
    if (receipt.runtime_release_id, receipt.assignment_seal_id) != (runtime.release_id, seal.seal_id):
        raise ValueError("D3 receipt runtime/seal mismatch")
    if (binding.authorization_input_id, binding.authorization_receipt_id, binding.runtime_release_id, binding.assignment_seal_id) != (
        authorization.authorization_input_id, receipt.receipt_id, runtime.release_id, seal.seal_id
    ):
        raise ValueError("D3 binding authorization/runtime closure mismatch")
    if (manifest.binding_id, manifest.authorization_receipt_id, manifest.runtime_release_id, manifest.assignment_seal_id) != (
        binding.binding_id, receipt.receipt_id, runtime.release_id, seal.seal_id
    ):
        raise ValueError("D3 manifest binding/authorization closure mismatch")
    if Path(binding.output_root).resolve() != output_root.resolve() or Path(manifest.output_root).resolve() != output_root.resolve():
        raise ValueError("D3 output root mismatch")
    selected = tuple(row for row in assignments.rows if row.assignment_id == binding.assignment_id)
    if len(selected) != 1:
        raise ValueError("D3 binding does not select exactly one assignment")
    assignment = selected[0]
    expected = (
        assignment.order,
        assignment.runtime_task,
        assignment.terminal_task,
        assignment.seed_commitment,
        assignment.task_asset_sha256,
    )
    if (binding.assignment_order, binding.task, binding.terminal_task, binding.seed_commitment, binding.task_asset_sha256) != expected:
        raise ValueError("D3 selected assignment binding mismatch")
    if (manifest.assignment_id, manifest.assignment_order, manifest.task, manifest.seed_commitment, manifest.task_asset_sha256) != (
        assignment.assignment_id,
        assignment.order,
        assignment.runtime_task,
        assignment.seed_commitment,
        assignment.task_asset_sha256,
    ):
        raise ValueError("D3 selected assignment manifest mismatch")
    if file_sha256(task_path) != assignment.task_asset_sha256:
        raise ValueError("D3 task asset SHA-256 mismatch")
    runtime_ids = (
        runtime.outcome_schema_id,
        runtime.find_contract_id,
        runtime.safety_policy_id,
        runtime.signature_registry_id,
        runtime.scene_compatibility_audit_id,
        runtime.planner_schema_id,
        runtime.planner_prompt_id,
        runtime.planner_parser_id,
        runtime.rule_registry_id,
        runtime.dependency_schema_id,
        runtime.paper_memory_release_id,
        runtime.scene_exemplar_release_id,
        runtime.mineclip_policy_id,
        runtime.controller_id,
        runtime.evaluator_id,
        runtime.budget_profile_id,
        runtime.technical_retry_policy_id,
        runtime.process_cleanup_policy_id,
    )
    binding_ids = (
        binding.outcome_schema_id,
        binding.find_contract_id,
        binding.safety_policy_id,
        binding.signature_registry_id,
        binding.scene_compatibility_audit_id,
        binding.planner_schema_id,
        binding.planner_prompt_id,
        binding.planner_parser_id,
        binding.rule_registry_id,
        binding.dependency_schema_id,
        binding.paper_memory_release_id,
        binding.scene_exemplar_release_id,
        binding.mineclip_policy_id,
        binding.controller_id,
        binding.evaluator_id,
        binding.budget_profile_id,
        binding.technical_retry_policy_id,
        binding.process_cleanup_policy_id,
    )
    if runtime_ids != binding_ids:
        raise ValueError("D3 runtime/binding scientific lineage mismatch")
    authorization_ids = (
        authorization.planner_schema_id,
        authorization.planner_prompt_id,
        authorization.planner_parser_id,
        authorization.paper_memory_release_id,
        authorization.scene_exemplar_release_id,
        authorization.mineclip_policy_id,
        authorization.controller_id,
        authorization.evaluator_id,
        authorization.technical_retry_policy_id,
        authorization.process_cleanup_policy_id,
    )
    expected_authorization_ids = (
        runtime.planner_schema_id,
        runtime.planner_prompt_id,
        runtime.planner_parser_id,
        runtime.paper_memory_release_id,
        runtime.scene_exemplar_release_id,
        runtime.mineclip_policy_id,
        runtime.controller_id,
        runtime.evaluator_id,
        runtime.technical_retry_policy_id,
        runtime.process_cleanup_policy_id,
    )
    if authorization_ids != expected_authorization_ids:
        raise ValueError("D3 authorization/runtime scientific lineage mismatch")
    return assignment
