"""Round 5.13E3F pre-authorization contracts and adversarial audits.

This module deliberately stops before source freeze, assignment sealing, or
MineDojo execution.  Historical E1R/E2H objects remain owned by their original
versioned pipeline.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .round513_collection import CHRMLitePlannerOutputSchemaV4_1
from .round513e2h import canonical_sha256, file_sha256


E3F_SCHEMA_VERSION = 1
GAMMA_CANDIDATE_B = "0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f"
GAMMA_TEXT = ("1.0", "-0.01040883", "0.00744657")
FORMAL_TASKSET_RELEASE_ID = "acec5270985fdd11f653a00ad195860ba8c0f21c6ea093e293030a502fef22d5"
FORMAL_CATALOG_CANONICAL_SHA256 = "10efe3143119c741b15247bb9aa242157ff7587951868925a247fac8dcc5b778"
HISTORICAL_E2H_ASSIGNMENTS_ID = "fbbf39672c264a12de7c173f366ea955600b61b882ac5373963b8cce118868d2"
HISTORICAL_E2H_SEAL_ID = "3157a431b880872f08f6c410978bc2b57e46428cfef6e2699ddfc4765279890f"
HISTORICAL_E2H_AUTHORIZATION_INPUT_ID = "ab2307023731adc42c594c589fd67fadda0f28bb4c9f871893ecb8e592d2c1d8"


CONTROLLER_ACTION_ARGUMENTS = {
    "find": ("obj",),
    "move_to": ("obj",),
    "mine": ("obj", "tool"),
    "craft": ("materials", "obj", "platform"),
    "fight": ("obj", "tool"),
    "equip": ("obj",),
    "dig_down": ("tool", "y_level"),
    "dig_up": ("tool",),
    "apply": ("obj", "tool"),
}


FORMAL_SMOKE_ROWS = (
    ("log", "mine log", "basic", "find", "feasible", "log.json", "mine_log.json"),
    ("cobblestone", "mine cobblestone", "easy", "move_to", "feasible", "cobblestone.json", "mine_cobblestone.json"),
    ("iron ore", "mine iron ore", "medium", "mine", "feasible", "iron_ore.json", "mine_iron_ore.json"),
    ("crafting table", "craft crafting table", "basic", "craft", "feasible", "crafting_table.json", "craft_crafting_table.json"),
    ("iron ingot", "smelt iron ingot", "hard", "craft", "feasible", "iron_ingot.json", "smelt_iron_ingot.json"),
    ("wooden pickaxe", "craft wooden pickaxe", "easy", "equip", "proxy_only", "wooden_pickaxe.json", "craft_wooden_pickaxe.json"),
    ("diamond", "obtain diamond", "complex", "dig_down", "feasible", "diamond.json", "obtain_diamond.json"),
    ("redstone", "mine redstone", "complex", "dig_up", "proxy_only", "redstone.json", "mine_redstone.json"),
    ("sapling", "mine sapling", "medium", "apply", "proxy_only", "sapling.json", "mine_sapling.json"),
)


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
class Round513E2TechnicalCampaignCloseout(_Hashed):
    source_commit: str
    campaign_id: str
    campaign_summary_file_sha256: str
    campaign_report_file_sha256: str
    campaign_class: str = "pre_action_technical_failure"
    assignment_count: int = 9
    scientific_records: int = 0
    scientific_successes: int = 0
    scientific_failures: int = 0
    provider_reached_assignments: int = 8
    environment_construction_failure_assignments: int = 1
    original_high_level_actions_executed: int = 0
    evaluation_calls: int = 0
    memory_writes: int = 0
    acquisition_writes: int = 0
    reusable_as_scientific_data: bool = False
    schema_version: int = E3F_SCHEMA_VERSION
    closeout_id: str = ""

    _id_field = "closeout_id"

    def __post_init__(self) -> None:
        zeroes = (
            self.scientific_records, self.scientific_successes,
            self.scientific_failures, self.original_high_level_actions_executed,
            self.evaluation_calls, self.memory_writes, self.acquisition_writes,
        )
        if self.campaign_class != "pre_action_technical_failure" or any(zeroes):
            raise ValueError("E2 closeout would misclassify technical evidence")
        if self.assignment_count != 9 or self.provider_reached_assignments != 8:
            raise ValueError("E2 closeout counts do not match frozen evidence")
        if self.environment_construction_failure_assignments != 1:
            raise ValueError("E2 environment failure count changed")
        if self.reusable_as_scientific_data:
            raise ValueError("Technical campaign cannot become scientific data")
        if self.closeout_id and self.closeout_id != self.compute_id():
            raise ValueError("E2 closeout hash mismatch")


@dataclass(frozen=True)
class Round513E3SourceChangeAudit(_Hashed):
    source_commit: str
    historical_execution_source: str
    reviewed_commits: tuple[str, ...]
    changed_files: tuple[str, ...]
    allowed_change_categories: tuple[str, ...]
    controller_production_changed: bool
    evaluator_production_changed: bool
    memory_production_changed: bool
    scientific_method_changed: bool
    gamma_changed: bool
    retry_policy_changed: bool
    cleanup_policy_changed: bool
    formal_task_assets_changed: bool
    status: str
    schema_version: int = E3F_SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        forbidden = (
            self.controller_production_changed, self.evaluator_production_changed,
            self.memory_production_changed, self.scientific_method_changed,
            self.gamma_changed, self.retry_policy_changed,
            self.cleanup_policy_changed, self.formal_task_assets_changed,
        )
        expected = "PASS" if self.changed_files and not any(forbidden) else "BLOCKED"
        if self.status != expected:
            raise ValueError("Source change conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Source change audit hash mismatch")


@dataclass(frozen=True)
class TrackEProviderRequestPolicyV4_1_2_E3(_Hashed):
    source_commit: str
    provider_profile_id: str
    endpoint_profile_id: str
    model_profile: str
    response_format: Mapping[str, str]
    temperature: float
    top_p: str
    max_output_tokens: int
    timeout_seconds: int
    provider_retry_policy: str
    scope: str = "track_e_planner_only"
    plain_text_fallback_permitted: bool = False
    fence_stripping_permitted: bool = False
    field_alias_repair_permitted: bool = False
    hidden_planner_retry_permitted: bool = False
    schema_version: int = E3F_SCHEMA_VERSION
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        if self.response_format != {"type": "json_object"}:
            raise ValueError("Track-E must use JSON object mode")
        if self.temperature != 0 or self.top_p != "provider_default_not_overridden":
            raise ValueError("Track-E sampling policy changed")
        if self.max_output_tokens < 1 or self.timeout_seconds < 1:
            raise ValueError("Provider request budget is not explicit")
        if self.provider_retry_policy != "zero_hidden_sdk_retries_campaign_policy_external":
            raise ValueError("Provider retry policy is not fail closed")
        if self.scope != "track_e_planner_only" or any((
            self.plain_text_fallback_permitted, self.fence_stripping_permitted,
            self.field_alias_repair_permitted, self.hidden_planner_retry_permitted,
        )):
            raise ValueError("Provider policy permits an unapproved fallback")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("Provider request policy hash mismatch")


def validate_action_schema(schema: Mapping[str, Any]) -> None:
    action = schema["properties"]["action"]
    variants = action["oneOf"]
    observed: dict[str, tuple[str, ...]] = {}
    for variant in variants:
        if variant.get("additionalProperties") is not False:
            raise ValueError("Action variant permits extra fields")
        properties = variant["properties"]
        name = properties["name"]["enum"][0]
        arguments = properties["arguments"]
        if arguments.get("additionalProperties") is not False:
            raise ValueError("Action arguments permit extra fields")
        required = tuple(sorted(arguments["required"]))
        if required != tuple(sorted(arguments["properties"])):
            raise ValueError("Action argument required/properties mismatch")
        observed[name] = required
    if observed != CONTROLLER_ACTION_ARGUMENTS:
        raise ValueError("Planner actions are not Controller-compatible")


@dataclass(frozen=True)
class PlannerRuntimeRequestContractV4_1_2_E3(_Hashed):
    source_commit: str
    prompt_template_id: str
    planner_schema_id: str
    parser_id: str
    provider_request_policy_id: str
    controller_action_arguments: Mapping[str, tuple[str, ...]]
    calls_per_decision: int = 1
    confidence_policy: str = "same_generation_required"
    malformed_policy: str = "audit_and_stop_without_retry"
    bound_schema_source: str = "self.schema.output_schema"
    schema_version: int = E3F_SCHEMA_VERSION
    contract_id: str = ""

    _id_field = "contract_id"

    def __post_init__(self) -> None:
        if self.controller_action_arguments != CONTROLLER_ACTION_ARGUMENTS:
            raise ValueError("Runtime contract action schema changed")
        if self.calls_per_decision != 1 or self.confidence_policy != "same_generation_required":
            raise ValueError("Runtime contract permits an extra Planner call")
        if self.malformed_policy != "audit_and_stop_without_retry":
            raise ValueError("Runtime contract weakens malformed handling")
        if self.bound_schema_source != "self.schema.output_schema":
            raise ValueError("Runtime contract bypasses the bound schema")
        if self.contract_id and self.contract_id != self.compute_id():
            raise ValueError("Planner runtime contract hash mismatch")


@dataclass(frozen=True)
class TrackEJSONModeCapabilityReceipt(_Hashed):
    source_commit: str
    probe_source_commit: str
    provider_request_policy_id: str
    planner_runtime_contract_id: str
    probe_kind: str
    http_success: bool
    nonempty: bool
    begins_with_object: bool
    code_fence_absent: bool
    strict_json_parseable: bool
    planner_call_count: int
    controller_compatible_arguments: bool
    raw_provider_response_persisted: bool
    api_key_persisted: bool
    scientific_result_eligible: bool = False
    schema_version: int = E3F_SCHEMA_VERSION
    receipt_id: str = ""

    _id_field = "receipt_id"

    def __post_init__(self) -> None:
        required = (
            self.http_success, self.nonempty, self.begins_with_object,
            self.code_fence_absent, self.strict_json_parseable,
            self.controller_compatible_arguments,
        )
        if not all(required) or self.planner_call_count != 1:
            raise ValueError("JSON mode capability is not established")
        if self.raw_provider_response_persisted or self.api_key_persisted:
            raise ValueError("Capability receipt persisted sensitive evidence")
        if self.scientific_result_eligible:
            raise ValueError("Provider capability cannot become scientific data")
        if self.receipt_id and self.receipt_id != self.compute_id():
            raise ValueError("Capability receipt hash mismatch")


@dataclass(frozen=True)
class Formal50TaskAssetBindingAudit(_Hashed):
    source_commit: str
    formal_taskset_release_id: str
    catalog_canonical_sha256: str
    catalog_file_sha256: str
    candidate_count: int
    catalog_match_count: int
    difficulty_match_count: int
    repository_asset_exists_count: int
    authoritative_asset_exists_count: int
    exact_asset_sha_match_count: int
    semantic_asset_match_count: int
    rows: tuple[Mapping[str, Any], ...]
    status: str
    schema_version: int = E3F_SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        eligible = (
            self.candidate_count == self.catalog_match_count
            == self.difficulty_match_count
            == self.repository_asset_exists_count
            == self.authoritative_asset_exists_count
            == self.exact_asset_sha_match_count
            == self.semantic_asset_match_count
        )
        if self.status != ("PASS" if eligible else "BLOCKED"):
            raise ValueError("Task asset audit conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Task asset audit hash mismatch")


@dataclass(frozen=True)
class Formal50AlignedSmokeCandidateAudit(_Hashed):
    source_commit: str
    namespace_id: str
    task_asset_audit_id: str
    candidate_count: int
    scientific_payload_root: str
    task_seed_order_changed_after_observation: bool
    contains_pig_or_creature: bool
    asset_binding_passed: bool
    status: str
    schema_version: int = E3F_SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        eligible = (
            self.candidate_count == 9
            and not self.task_seed_order_changed_after_observation
            and not self.contains_pig_or_creature
            and self.asset_binding_passed
        )
        if self.status != ("PASS" if eligible else "BLOCKED"):
            raise ValueError("Formal-50 candidate conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Formal-50 candidate audit hash mismatch")


@dataclass(frozen=True)
class IronIngotTaskAssetDecisionInput(_Hashed):
    source_commit: str
    task_asset_audit_id: str
    formal_task_name: str
    semantic_process_family: str
    controller_action_family: str
    repository_asset_sha256: str
    authoritative_asset_sha256: str
    repository_iron_ore_requirement: int
    authoritative_iron_ore_requirement: int
    platform: str
    runtime_material_semantics: str
    conflict_confirmed: bool
    choices: tuple[Mapping[str, str], ...]
    selected_choice: str | None = None
    source_freeze_permitted: bool = False
    assignment_seal_permitted: bool = False
    schema_version: int = E3F_SCHEMA_VERSION
    decision_input_id: str = ""

    _id_field = "decision_input_id"

    def __post_init__(self) -> None:
        if self.semantic_process_family != "smelt" or self.controller_action_family != "craft":
            raise ValueError("Iron-ingot process/action mapping changed")
        if self.platform != "furnace" or not self.conflict_confirmed:
            raise ValueError("Iron-ingot conflict is not represented")
        if self.selected_choice is not None or self.source_freeze_permitted or self.assignment_seal_permitted:
            raise ValueError("Iron-ingot author decision was fabricated")
        if self.decision_input_id and self.decision_input_id != self.compute_id():
            raise ValueError("Iron-ingot decision input hash mismatch")


@dataclass(frozen=True)
class ProxyActionCoverageAudit(_Hashed):
    source_commit: str
    candidates: tuple[Mapping[str, Any], ...]
    proxy_count: int
    natural_coverage_claim_count: int
    observed_coverage_claim_count: int
    status: str
    schema_version: int = E3F_SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.proxy_count != 3:
            raise ValueError("Expected exactly three proxy-only candidates")
        if self.natural_coverage_claim_count or self.observed_coverage_claim_count:
            raise ValueError("Proxy candidates were mislabeled as coverage")
        if self.status != "PENDING_AUTHOR_POLICY":
            raise ValueError("Proxy audit crossed the author boundary")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Proxy audit hash mismatch")


@dataclass(frozen=True)
class ProxyActionCoverageDecisionInput(_Hashed):
    source_commit: str
    proxy_audit_id: str
    choices: tuple[Mapping[str, str], ...]
    selected_choice: str | None = None
    source_freeze_permitted: bool = False
    assignment_seal_permitted: bool = False
    schema_version: int = E3F_SCHEMA_VERSION
    decision_input_id: str = ""

    _id_field = "decision_input_id"

    def __post_init__(self) -> None:
        labels = tuple(choice["id"] for choice in self.choices)
        if labels != ("P1", "P2", "P3"):
            raise ValueError("Proxy policy choices changed")
        if self.selected_choice is not None or self.source_freeze_permitted or self.assignment_seal_permitted:
            raise ValueError("Proxy author decision was fabricated")
        if self.decision_input_id and self.decision_input_id != self.compute_id():
            raise ValueError("Proxy decision input hash mismatch")


def build_provider_contracts(source_commit: str):
    schema = CHRMLitePlannerOutputSchemaV4_1(source_commit=source_commit).with_computed_id()
    validate_action_schema(schema.output_schema)
    policy = TrackEProviderRequestPolicyV4_1_2_E3(
        source_commit=source_commit,
        provider_profile_id=canonical_sha256({"api_family": "openai_compatible_chat_completions_v1"}),
        endpoint_profile_id=canonical_sha256({"endpoint_class": "authorized_external_openai_compatible_v1"}),
        model_profile="glm-5.2",
        response_format={"type": "json_object"},
        temperature=0,
        top_p="provider_default_not_overridden",
        max_output_tokens=2048,
        timeout_seconds=60,
        provider_retry_policy="zero_hidden_sdk_retries_campaign_policy_external",
    ).with_id()
    contract = PlannerRuntimeRequestContractV4_1_2_E3(
        source_commit=source_commit,
        prompt_template_id=schema.prompt_id,
        planner_schema_id=schema.schema_id,
        parser_id=schema.parser_id,
        provider_request_policy_id=policy.policy_id,
        controller_action_arguments=CONTROLLER_ACTION_ARGUMENTS,
    ).with_id()
    receipt = TrackEJSONModeCapabilityReceipt(
        source_commit=source_commit,
        probe_source_commit="01cba8dc66e6caf10b378f9be9ca0907b9dc4f25",
        provider_request_policy_id=policy.policy_id,
        planner_runtime_contract_id=contract.contract_id,
        probe_kind="credentialed_nonpersistent_technical_probe",
        http_success=True,
        nonempty=True,
        begins_with_object=True,
        code_fence_absent=True,
        strict_json_parseable=True,
        planner_call_count=1,
        controller_compatible_arguments=True,
        raw_provider_response_persisted=False,
        api_key_persisted=False,
    ).with_id()
    return schema, policy, contract, receipt


def build_task_asset_audit(
    *, source_commit: str, agent_root: Path, formal_root: Path,
) -> Formal50TaskAssetBindingAudit:
    catalog_path = formal_root / "schema_v2" / "final_tasks.csv"
    with catalog_path.open(encoding="utf-8", newline="") as handle:
        catalog = {row["task"]: row for row in csv.DictReader(handle)}
    rows = []
    for terminal, formal_task, declared, action, feasibility, repo_name, formal_name in FORMAL_SMOKE_ROWS:
        repo_path = agent_root / "agent" / "tasks" / "creative" / repo_name
        formal_path = formal_root / "creative_task_jsons" / formal_name
        repo_exists, formal_exists = repo_path.is_file(), formal_path.is_file()
        repo_payload = json.loads(repo_path.read_text(encoding="utf-8")) if repo_exists else None
        formal_payload = json.loads(formal_path.read_text(encoding="utf-8")) if formal_exists else None
        catalog_row = catalog.get(formal_task)
        rows.append({
            "terminal_task": terminal,
            "formal_task": formal_task,
            "declared_difficulty": declared,
            "catalog_difficulty": catalog_row["difficulty"] if catalog_row else None,
            "target_action_family": action,
            "coverage_feasibility": feasibility,
            "repository_asset_label": f"agent/tasks/creative/{repo_name}",
            "repository_asset_sha256": file_sha256(repo_path) if repo_exists else None,
            "authoritative_asset_label": f"creative_task_jsons/{formal_name}",
            "authoritative_asset_sha256": file_sha256(formal_path) if formal_exists else None,
            "catalog_match": catalog_row is not None,
            "difficulty_match": bool(catalog_row and catalog_row["difficulty"] == declared),
            "repository_asset_exists": repo_exists,
            "authoritative_asset_exists": formal_exists,
            "exact_asset_sha_match": bool(repo_exists and formal_exists and file_sha256(repo_path) == file_sha256(formal_path)),
            "semantic_asset_match": bool(repo_exists and formal_exists and repo_payload == formal_payload),
        })
    count = lambda key: sum(bool(row[key]) for row in rows)
    audit = Formal50TaskAssetBindingAudit(
        source_commit=source_commit,
        formal_taskset_release_id=FORMAL_TASKSET_RELEASE_ID,
        catalog_canonical_sha256=FORMAL_CATALOG_CANONICAL_SHA256,
        catalog_file_sha256=file_sha256(catalog_path),
        candidate_count=len(rows),
        catalog_match_count=count("catalog_match"),
        difficulty_match_count=count("difficulty_match"),
        repository_asset_exists_count=count("repository_asset_exists"),
        authoritative_asset_exists_count=count("authoritative_asset_exists"),
        exact_asset_sha_match_count=count("exact_asset_sha_match"),
        semantic_asset_match_count=count("semantic_asset_match"),
        rows=tuple(rows),
        status="PASS" if all(count(key) == len(rows) for key in (
            "catalog_match", "difficulty_match", "repository_asset_exists",
            "authoritative_asset_exists", "exact_asset_sha_match", "semantic_asset_match",
        )) else "BLOCKED",
    ).with_id()
    return audit


def build_decision_inputs(*, source_commit: str, task_audit: Formal50TaskAssetBindingAudit):
    iron = next(row for row in task_audit.rows if row["formal_task"] == "smelt iron ingot")
    iron_decision = IronIngotTaskAssetDecisionInput(
        source_commit=source_commit,
        task_asset_audit_id=task_audit.audit_id,
        formal_task_name="smelt iron ingot",
        semantic_process_family="smelt",
        controller_action_family="craft",
        repository_asset_sha256=str(iron["repository_asset_sha256"]),
        authoritative_asset_sha256=str(iron["authoritative_asset_sha256"]),
        repository_iron_ore_requirement=8,
        authoritative_iron_ore_requirement=1,
        platform="furnace",
        runtime_material_semantics="required_inventory_quantity_checked_then_consumed_by_legacy_craft_mapping",
        conflict_confirmed=True,
        choices=(
            {"id": "I1", "effect": "bind the immutable formal asset with iron ore requirement 1; preserve the repository asset as history"},
            {"id": "I2", "effect": "remove iron ingot and derive a newly authorized candidate set and namespace"},
            {"id": "I3", "effect": "prospectively amend the formal task asset through a separate formal taskset procedure"},
        ),
    ).with_id()
    proxy_rows = tuple({
        "terminal_task": terminal,
        "target_action_family": action,
        "task_alignment": "formal_catalog_aligned",
        "action_naturalness": "proxy_only",
        "instrumentation_targeting": "targeted_engineering_probe",
        "observed_runtime_coverage": "not_observed",
        "natural_action_coverage_eligible": False,
    } for terminal, _, _, action, feasibility, _, _ in FORMAL_SMOKE_ROWS if feasibility == "proxy_only")
    proxy_audit = ProxyActionCoverageAudit(
        source_commit=source_commit,
        candidates=proxy_rows,
        proxy_count=len(proxy_rows),
        natural_coverage_claim_count=0,
        observed_coverage_claim_count=0,
        status="PENDING_AUTHOR_POLICY",
    ).with_id()
    proxy_decision = ProxyActionCoverageDecisionInput(
        source_commit=source_commit,
        proxy_audit_id=proxy_audit.audit_id,
        choices=(
            {"id": "P1", "effect": "retain all three as engineering-only targeted probes; never claim natural or observed coverage"},
            {"id": "P2", "effect": "remove all three and freeze a six-assignment smoke without equip/dig_up/apply claims"},
            {"id": "P3", "effect": "replace prospectively with verified natural formal tasks under a new namespace, seeds, assignments, and authorization"},
        ),
    ).with_id()
    return iron_decision, proxy_audit, proxy_decision


def scientific_payload_root_without_seed_disclosure(assignments: Sequence[Any]) -> str:
    return canonical_sha256([
        {
            "order": index,
            "terminal_task": item.terminal_task,
            "difficulty": item.difficulty,
            "target_action_family": item.target_action_family,
            "coverage_feasibility": item.coverage_feasibility,
            "seed_commitment": item.seed_commitment,
            "seed": item.seed,
            "task_file_sha256": item.task_file_sha256,
        }
        for index, item in enumerate(assignments)
    ])


BOUNDARY_A_APPROVAL_REQUIRED_LITERALS = (
    "ProxyActionCoverageDecisionInput 085c53aea5a629cfb5d6e220f52136bfdb357aa6b9c42aa2516abb5d04565512",
    "file SHA-256 93d228dcf98d801513f7d734e89ba19bd6b6976d8e34f42876ffcd3d6bcfd6fe",
    "selecting P1",
    "IronIngotTaskAssetDecisionInput c7a0827769b36d48e67f5899d4af79a76e2b886267504d5c5fe8bb83e8327857",
    "file SHA-256 3c4b4680ebdf427d0255845b8a90f061aeb2f23a39f344bbada408367ca4c634",
    "selecting I1",
    "deterministic alignment of all nine candidate bindings to the immutable formal assets and formal catalog difficulties",
    "approved_by=ZYF",
)


E3_AUTHORIZATION_DECLARATIONS = (
    "The prior E2H campaign is a pre-action technical failure with zero scientific records.",
    "E3 uses a new source, namespace, assignments, seal, and authorization.",
    "Every E3 task is bound to the immutable formal 50-task catalog and asset.",
    "Proxy-only items are never represented as natural or observed action coverage.",
    "The iron-ingot task uses the immutable formal asset; no formal task asset was modified.",
    "Track-E uses JSON-object mode, the strict parser, one Planner call, and same-generation confidence.",
    "Plain-text fallback, field alias repair, fence stripping, and hidden Planner retry are forbidden.",
    "Controller, Evaluator, Memory, CHRM, CDT, and the scientific method are unchanged.",
    "Candidate B and the three exact Gamma decimal strings are unchanged.",
    "Every Smoke record is engineering-only and excluded from all fitting and calibration.",
    "Scientific failures receive no retry; technical failures follow only the frozen pre-action policy.",
    "Formal Development, Holdout, Final Evaluation, and Round 6 remain closed.",
)


@dataclass(frozen=True)
class Round513E3AuthorBoundaryAReceipt(_Hashed):
    source_commit: str
    proxy_decision_input_id: str
    proxy_decision_input_file_sha256: str
    proxy_choice: str
    iron_decision_input_id: str
    iron_decision_input_file_sha256: str
    iron_choice: str
    approval_statement_sha256: str
    deterministic_formal_alignment_authorized: bool
    approved_by: str
    schema_version: int = E3F_SCHEMA_VERSION
    receipt_id: str = ""

    _id_field = "receipt_id"

    def __post_init__(self) -> None:
        if self.proxy_choice != "P1" or self.iron_choice != "I1":
            raise ValueError("Boundary-A choices do not match the approval")
        if not self.deterministic_formal_alignment_authorized or self.approved_by != "ZYF":
            raise ValueError("Boundary-A approval is incomplete")
        if self.receipt_id and self.receipt_id != self.compute_id():
            raise ValueError("Boundary-A receipt hash mismatch")


def validate_boundary_a_approval(statement: str) -> None:
    normalized = " ".join(statement.split())
    missing = [item for item in BOUNDARY_A_APPROVAL_REQUIRED_LITERALS if item not in normalized]
    if missing:
        raise ValueError(f"Boundary-A approval is incomplete: {missing}")


@dataclass(frozen=True)
class SmokeAssignmentV4_1_2_E3(_Hashed):
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
    schema_version: int = E3F_SCHEMA_VERSION
    assignment_id: str = ""

    _id_field = "assignment_id"

    def __post_init__(self) -> None:
        if self.coverage_naturalness not in {"natural", "proxy_only"}:
            raise ValueError("Unknown action coverage naturalness")
        if self.coverage_naturalness == "proxy_only" and self.natural_action_coverage_eligible:
            raise ValueError("Proxy-only assignment claims natural coverage")
        if self.observed_runtime_coverage != "not_observed_before_execution":
            raise ValueError("Prospective assignment fabricated observed coverage")
        eligibility = (
            self.formal_fitting_eligible, self.channel_calibration_eligible,
            self.CHRM_fitting_eligible, self.CDT_identification_eligible,
            self.holdout_eligible, self.final_evaluation_eligible,
        )
        if not self.engineering_only or any(eligibility):
            raise ValueError("E3 assignment entered a protected scientific split")
        if self.assignment_id and self.assignment_id != self.compute_id():
            raise ValueError("E3 assignment hash mismatch")


def derive_authorized_e3_assignments(
    *, source_commit: str, formal_root: Path, namespace_label: str,
) -> tuple[str, tuple[SmokeAssignmentV4_1_2_E3, ...]]:
    namespace_id = canonical_sha256({"namespace_label": namespace_label})
    catalog_path = formal_root / "schema_v2" / "final_tasks.csv"
    with catalog_path.open(encoding="utf-8", newline="") as handle:
        catalog = {row["task"]: row for row in csv.DictReader(handle)}
    assignments = []
    for order, (terminal, formal_task, _, action, feasibility, _, formal_name) in enumerate(FORMAL_SMOKE_ROWS):
        row = catalog[formal_task]
        asset = formal_root / "creative_task_jsons" / formal_name
        seed_commitment = canonical_sha256({
            "namespace_id": namespace_id,
            "terminal_task": terminal,
            "replicate_index": order,
        })
        coverage = "proxy_only" if feasibility == "proxy_only" else "natural"
        item = SmokeAssignmentV4_1_2_E3(
            source_commit=source_commit,
            namespace_id=namespace_id,
            terminal_task=terminal,
            formal_task_name=formal_task,
            formal_catalog_row_id=canonical_sha256(row),
            task_path_label=f"creative_task_jsons/{formal_name}",
            task_file_sha256=file_sha256(asset),
            difficulty=row["difficulty"],
            target_action_family=action,
            coverage_naturalness=coverage,
            natural_action_coverage_eligible=coverage == "natural",
            instrumentation_target_eligible=True,
            observed_runtime_coverage="not_observed_before_execution",
            seed_commitment=seed_commitment,
            seed=int(seed_commitment[:8], 16) & 0x7FFFFFFF,
            order=order,
        ).with_id()
        assignments.append(item)
    return namespace_id, tuple(assignments)


@dataclass(frozen=True)
class Round513E3ResolvedTaskAssetAudit(_Hashed):
    source_commit: str
    boundary_a_receipt_id: str
    original_blocked_asset_audit_id: str
    formal_taskset_release_id: str
    formal_catalog_file_sha256: str
    assignment_count: int
    catalog_match_count: int
    difficulty_match_count: int
    immutable_asset_binding_count: int
    formal_assets_modified: bool
    status: str
    schema_version: int = E3F_SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        eligible = (
            self.assignment_count == self.catalog_match_count
            == self.difficulty_match_count == self.immutable_asset_binding_count == 9
            and not self.formal_assets_modified
        )
        if self.status != ("PASS" if eligible else "BLOCKED"):
            raise ValueError("Resolved task asset audit conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Resolved task asset audit hash mismatch")


@dataclass(frozen=True)
class Round513E3ExternalManifestGateAudit(_Hashed):
    source_commit: str
    round511_assignment_manifest_id: str
    round511_assignment_manifest_file_sha256: str
    relevant_tests_passed: int
    relevant_tests_failed: int
    relevant_tests_skipped: int
    snapshot_guard_passed: bool
    memory_write_probe_rejected: bool
    minedojo_launch_count: int
    schema_version: int = E3F_SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.relevant_tests_passed < 1 or self.relevant_tests_failed or self.relevant_tests_skipped:
            raise ValueError("External manifest gate is not clean")
        if not self.snapshot_guard_passed or not self.memory_write_probe_rejected:
            raise ValueError("Frozen Memory integrity gate failed")
        if self.minedojo_launch_count:
            raise ValueError("E3F gate launched MineDojo")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("External manifest gate hash mismatch")


@dataclass(frozen=True)
class Round513E3SourceFreezeAudit(_Hashed):
    source_commit: str
    source_change_audit_id: str
    boundary_a_receipt_id: str
    external_manifest_gate_audit_id: str
    github_actions_run_id: str
    github_actions_url: str
    github_actions_conclusion: str
    remote_branch_contains_source: bool
    worktree_clean: bool
    diff_check_passed: bool
    schema_version: int = E3F_SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.github_actions_conclusion != "success" or not self.github_actions_url:
            raise ValueError("GitHub Actions is not green")
        if not all((self.remote_branch_contains_source, self.worktree_clean, self.diff_check_passed)):
            raise ValueError("Source is not eligible for freeze")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Source freeze audit hash mismatch")


@dataclass(frozen=True)
class Round513E3ContractCompatibilityRelease(_Hashed):
    source_commit: str
    source_freeze_audit_id: str
    historical_compatibility_release_id: str
    provider_request_policy_id: str
    planner_runtime_request_contract_id: str
    planner_schema_id: str
    parser_id: str
    historical_e1r_e2h_reconstructable: bool
    old_authorization_accepted: bool = False
    exact_source_and_contract_match_required: bool = True
    schema_version: int = E3F_SCHEMA_VERSION
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        if not self.historical_e1r_e2h_reconstructable or self.old_authorization_accepted:
            raise ValueError("E3 compatibility release weakens version isolation")
        if not self.exact_source_and_contract_match_required:
            raise ValueError("E3 compatibility release permits silent downgrade")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("Compatibility release hash mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeRuntimeReleaseV4_1_2_E3(_Hashed):
    source_commit: str
    source_freeze_audit_id: str
    compatibility_release_id: str
    provider_request_policy_id: str
    planner_runtime_request_contract_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    controller_id: str
    evaluator_id: str
    budget_profile_id: str
    memory_no_write: bool
    evaluation_chain_changed: bool
    minedojo_started: bool
    schema_version: int = E3F_SCHEMA_VERSION
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        if not self.memory_no_write or self.evaluation_chain_changed or self.minedojo_started:
            raise ValueError("E3 runtime release changed frozen behavior")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("Runtime release hash mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeAssignmentsV4_1_2_E3(_Hashed):
    source_commit: str
    namespace_id: str
    runtime_release_id: str
    assignments: tuple[SmokeAssignmentV4_1_2_E3, ...]
    fixed_before_outcomes: bool = True
    observed_coverage_can_expand_set: bool = False
    schema_version: int = E3F_SCHEMA_VERSION
    assignments_id: str = ""

    _id_field = "assignments_id"

    def __post_init__(self) -> None:
        if len(self.assignments) != 9 or len({item.assignment_id for item in self.assignments}) != 9:
            raise ValueError("E3 requires nine unique P1 assignments")
        if not self.fixed_before_outcomes or self.observed_coverage_can_expand_set:
            raise ValueError("E3 assignments are adaptive")
        if self.assignments_id and self.assignments_id != self.compute_id():
            raise ValueError("E3 assignments hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["assignments"] = [item.to_dict() for item in self.assignments]
        return payload


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokePoolV4_1_2_E3(_Hashed):
    source_commit: str
    namespace_id: str
    task_asset_audit_id: str
    proxy_policy: str
    assignment_count: int
    engineering_only: bool = True
    fitting_eligible: bool = False
    outcome_selected: bool = False
    schema_version: int = E3F_SCHEMA_VERSION
    pool_id: str = ""

    _id_field = "pool_id"

    def __post_init__(self) -> None:
        if self.proxy_policy != "P1" or self.assignment_count != 9:
            raise ValueError("E3 pool does not match author policy")
        if not self.engineering_only or self.fitting_eligible or self.outcome_selected:
            raise ValueError("E3 pool entered fitting or selected outcomes")
        if self.pool_id and self.pool_id != self.compute_id():
            raise ValueError("E3 pool hash mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeExclusionAuditV4_1_2_E3(_Hashed):
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
    schema_version: int = E3F_SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        counts = (
            self.acquisition_overlap_count, self.historical_development_overlap_count,
            self.previous_smoke_overlap_count, self.future_formal_v412_overlap_count,
            self.holdout_overlap_count, self.final_overlap_count,
        )
        if any(counts) or not self.eligible:
            raise ValueError("E3 assignments overlap a protected split")
        if self.proof_method != "cryptographic_namespace_and_assignment_id_domain_separation":
            raise ValueError("Unknown E3 exclusion proof")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("E3 exclusion audit hash mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeSealV4_1_2_E3(_Hashed):
    source_commit: str
    pool_id: str
    assignments_id: str
    assignments_root_sha256: str
    exclusion_audit_id: str
    compatibility_release_id: str
    runtime_release_id: str
    assignment_count: int
    proxy_policy: str
    permanently_engineering_only: bool = True
    fitting_ineligible: bool = True
    sealed: bool = True
    schema_version: int = E3F_SCHEMA_VERSION
    seal_id: str = ""

    _id_field = "seal_id"

    def __post_init__(self) -> None:
        if self.assignment_count != 9 or self.proxy_policy != "P1":
            raise ValueError("E3 seal does not match approved assignment policy")
        if not all((self.permanently_engineering_only, self.fitting_ineligible, self.sealed)):
            raise ValueError("E3 seal is incomplete")
        if self.seal_id and self.seal_id != self.compute_id():
            raise ValueError("E3 seal hash mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2_E3(_Hashed):
    source_commit: str
    source_freeze_audit_id: str
    e2_closeout_id: str
    boundary_a_receipt_id: str
    runtime_release_id: str
    compatibility_release_id: str
    provider_request_policy_id: str
    planner_runtime_request_contract_id: str
    planner_schema_id: str
    planner_prompt_id: str
    planner_parser_id: str
    formal_taskset_release_id: str
    formal_catalog_sha256: str
    task_asset_audit_id: str
    proxy_policy: str
    pool_id: str
    assignments_id: str
    exclusion_audit_id: str
    seal_id: str
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
    process_cleanup_policy_id: str
    gamma_candidate: str
    gamma_cov_text: str
    gamma_minus_text: str
    gamma_plus_text: str
    declarations: tuple[str, ...]
    authorization_status: str = "pending_ZYF_boundary_B"
    minedojo_execution_permitted: bool = False
    formal_development_permitted: bool = False
    holdout_final_round6_permitted: bool = False
    approved_by: str | None = None
    schema_version: int = E3F_SCHEMA_VERSION
    authorization_input_id: str = ""

    _id_field = "authorization_input_id"

    def __post_init__(self) -> None:
        if self.declarations != E3_AUTHORIZATION_DECLARATIONS:
            raise ValueError("E3 authorization declarations changed")
        if self.proxy_policy != "P1" or self.gamma_candidate != GAMMA_CANDIDATE_B:
            raise ValueError("E3 authorization changed approved policy or Gamma candidate")
        if (self.gamma_cov_text, self.gamma_minus_text, self.gamma_plus_text) != GAMMA_TEXT:
            raise ValueError("E3 authorization changed exact Gamma strings")
        if self.authorization_status != "pending_ZYF_boundary_B" or self.approved_by is not None:
            raise ValueError("E3 authorization fabricated Boundary-B approval")
        if any((self.minedojo_execution_permitted, self.formal_development_permitted, self.holdout_final_round6_permitted)):
            raise ValueError("Pending E3 authorization opened execution")
        if self.authorization_input_id and self.authorization_input_id != self.compute_id():
            raise ValueError("E3 authorization input hash mismatch")
