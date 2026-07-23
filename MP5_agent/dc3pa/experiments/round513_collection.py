"""Prospective Round 5.13C collection contracts.

The contracts in this module are outcome-free. They do not generate formal
assignments, authorize an engineering smoke, fit a model, or access holdout
data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping, Sequence

from ..contracts import ALLOWED_ACTIONS
from .round513_method import CONFIDENCE_LEVELS


SCHEMA_VERSION = 1
FAILURE_MODES = (
    "missing_prerequisite",
    "model_reasoning_error",
    "environment_mismatch",
    "controller_execution_failure",
    "resource_search_failure",
    "action_infeasible",
    "none",
)
LABEL_STATES = (
    "success",
    "scientific_failure",
    "technical_failure",
    "ambiguous_unobservable",
)
TRACK_E_MODE = "chrmlite_estimation_collection_v41"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


class _Hashed:
    _id_field: str

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop(self._id_field, None)
        return payload

    def compute_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_computed_id(self):
        return replace(self, **{self._id_field: self.compute_id()})

    def to_dict(self) -> dict[str, Any]:
        item = self if getattr(self, self._id_field) else self.with_computed_id()
        payload = item.payload_without_id()
        payload[self._id_field] = getattr(item, self._id_field)
        return payload


@dataclass(frozen=True)
class CHRMLiteDevelopmentCollectionAuthorization(_Hashed):
    source_commit: str
    method_contract_id: str
    historical_data_decision_id: str
    status: str = "pending_author_approval"
    author_approved: bool = False
    engineering_smoke_approved: bool = False
    formal_collection_approved: bool = False
    formal_assignments_generated: bool = False
    holdout_access_permitted: bool = False
    final_evaluation_permitted: bool = False
    round6_permitted: bool = False
    schema_version: int = SCHEMA_VERSION
    authorization_id: str = ""

    _id_field = "authorization_id"

    def __post_init__(self) -> None:
        if not self.source_commit or not self.method_contract_id:
            raise ValueError("Collection authorization lineage is incomplete")
        if self.status != "pending_author_approval" or any(
            (
                self.author_approved,
                self.engineering_smoke_approved,
                self.formal_collection_approved,
                self.formal_assignments_generated,
                self.holdout_access_permitted,
                self.final_evaluation_permitted,
                self.round6_permitted,
            )
        ):
            raise ValueError("Draft authorization opened an unapproved phase")
        if self.authorization_id and self.authorization_id != self.compute_id():
            raise ValueError("Collection authorization hash mismatch")


@dataclass(frozen=True)
class CHRMLiteDevelopmentSeedNamespace(_Hashed):
    source_commit: str
    authorization_id: str
    namespace_label: str = "dc3pa-round513-track-e-v41"
    derivation: str = "sha256(namespace_id,terminal_task,split,replicate_index)"
    excluded_namespace_ids: tuple[str, ...] = ()
    formal_seed_count: int = 0
    formal_assignments_generated: bool = False
    plaintext_seeds_stored: bool = False
    schema_version: int = SCHEMA_VERSION
    namespace_id: str = ""

    _id_field = "namespace_id"

    def __post_init__(self) -> None:
        if not self.source_commit or not self.authorization_id:
            raise ValueError("Seed namespace lineage is incomplete")
        if len(set(self.excluded_namespace_ids)) != len(self.excluded_namespace_ids):
            raise ValueError("Duplicate excluded seed namespace")
        if self.formal_seed_count or self.formal_assignments_generated or self.plaintext_seeds_stored:
            raise ValueError("Round 5.13C must not generate formal seeds")
        if self.namespace_id and self.namespace_id != self.compute_id():
            raise ValueError("Seed namespace hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["excluded_namespace_ids"] = list(self.excluded_namespace_ids)
        return payload


@dataclass(frozen=True)
class RuleTypeDefinition:
    rule_id: str
    predicate_family: str
    rule_type: str
    action_families: tuple[str, ...]
    source: str
    eligibility: str

    def __post_init__(self) -> None:
        if self.rule_type not in {"hard", "soft", "excluded_ambiguous"}:
            raise ValueError("Unknown rule type")
        if not self.rule_id or not self.predicate_family or not self.source:
            raise ValueError("Rule definition is incomplete")
        if not self.action_families or not set(self.action_families) <= ALLOWED_ACTIONS:
            raise ValueError("Rule references unsupported action families")


@dataclass(frozen=True)
class CHRMLiteRuleTypeRegistryV4_1(_Hashed):
    source_commit: str
    dependency_schema_id: str
    rules: tuple[RuleTypeDefinition, ...]
    labels_available_to_classifier: bool = False
    support_controls_eligibility_only: bool = True
    hard_rules_enter_soft_coverage: bool = False
    ambiguous_necessity_excluded: bool = True
    schema_version: int = SCHEMA_VERSION
    registry_id: str = ""

    _id_field = "registry_id"

    def __post_init__(self) -> None:
        if not self.source_commit or not self.dependency_schema_id or not self.rules:
            raise ValueError("Rule registry is incomplete")
        if self.labels_available_to_classifier or self.hard_rules_enter_soft_coverage:
            raise ValueError("Rule registry permits outcome leakage")
        if not self.support_controls_eligibility_only or not self.ambiguous_necessity_excluded:
            raise ValueError("Rule registry safety policy changed")
        ids = [item.rule_id for item in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate rule ID")
        if self.registry_id and self.registry_id != self.compute_id():
            raise ValueError("Rule registry hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["rules"] = [asdict(item) for item in self.rules]
        return payload

    def counts_by_action_family(self) -> dict[str, dict[str, int]]:
        result = {
            action: {"hard": 0, "soft": 0, "excluded_ambiguous": 0}
            for action in sorted(ALLOWED_ACTIONS)
        }
        for rule in self.rules:
            for action in rule.action_families:
                result[action][rule.rule_type] += 1
        return result


PLANNER_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["subgoal", "action", "confidence", "failure_mode"],
    "additionalProperties": False,
    "properties": {
        "subgoal": {"type": "string", "minLength": 1},
        "action": {
            "type": "object",
            "required": ["name", "arguments"],
            "additionalProperties": False,
            "properties": {
                "name": {"enum": sorted(ALLOWED_ACTIONS)},
                "arguments": {"type": "object"},
            },
        },
        "confidence": {"enum": list(CONFIDENCE_LEVELS)},
        "failure_mode": {"enum": list(FAILURE_MODES)},
    },
}

PLANNER_PROMPT_TEMPLATE = """You are the frozen DC3PA V4.1 Planner.
Given TASK and PRE_EXECUTION_STATE, propose exactly one original high-level action.
Return only one JSON object matching SCHEMA. Do not include a probability.
TASK={task_json}
PRE_EXECUTION_STATE={state_json}
SCHEMA={schema_json}
"""


@dataclass(frozen=True)
class CHRMLitePlannerOutputSchemaV4_1(_Hashed):
    source_commit: str
    output_schema: Mapping[str, Any] = field(default_factory=lambda: PLANNER_OUTPUT_SCHEMA)
    prompt_template: str = PLANNER_PROMPT_TEMPLATE
    parser_policy: str = "strict_json_single_object_map_arguments_to_legacy_args"
    malformed_policy: str = "audit_and_stop_without_retry"
    calls_per_decision: int = 1
    confidence_required: bool = True
    extra_confidence_call_permitted: bool = False
    raw_probability_permitted: bool = False
    same_schema_for_all_baselines: bool = True
    schema_version: int = SCHEMA_VERSION
    schema_id: str = ""

    _id_field = "schema_id"

    def __post_init__(self) -> None:
        if self.calls_per_decision != 1 or self.extra_confidence_call_permitted:
            raise ValueError("Planner schema permits an extra call")
        if self.raw_probability_permitted or not self.confidence_required:
            raise ValueError("Planner confidence contract changed")
        if self.malformed_policy != "audit_and_stop_without_retry":
            raise ValueError("Malformed output policy can violate one-call collection")
        if self.schema_id and self.schema_id != self.compute_id():
            raise ValueError("Planner schema hash mismatch")

    @property
    def prompt_id(self) -> str:
        return _sha({"prompt_template": self.prompt_template})

    @property
    def parser_id(self) -> str:
        return _sha(
            {
                "parser_policy": self.parser_policy,
                "malformed_policy": self.malformed_policy,
                "output_schema": self.output_schema,
            }
        )


@dataclass(frozen=True)
class CHRMLiteBilateralRetrievalPolicyV4_1(_Hashed):
    source_commit: str
    paper_memory_v5_release_id: str
    scene_exemplar_release_id: str
    mineclip_policy_id: str
    top_k_per_side: int = 3
    minimum_count_per_side: int = 3
    compatible_rule: str = "canonical_action_signature_exact_match"
    incompatible_rule: str = "different_signature_with_known_action_family"
    tie_break: str = "similarity_desc_exemplar_id_asc"
    undercovered_state: str = "unknown"
    full_library_max_shortcut_permitted: bool = False
    online_llm_calls: int = 0
    gamma_policy: str = "dev_train_cross_fitted_candidate_quantiles"
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        if (self.top_k_per_side, self.minimum_count_per_side) != (3, 3):
            raise ValueError("Bilateral top-k contract changed")
        if self.full_library_max_shortcut_permitted or self.online_llm_calls:
            raise ValueError("Bilateral retrieval permits a forbidden shortcut")
        if self.undercovered_state != "unknown":
            raise ValueError("Under-covered retrieval must be unknown")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("Bilateral retrieval policy hash mismatch")


@dataclass(frozen=True)
class StepOutcomeDefinition:
    action_family: str
    required_pre_state: tuple[str, ...]
    expected_post_state: tuple[str, ...]
    budget_field: str
    success_predicate: str
    scientific_failure_predicate: str
    technical_failure_predicate: str
    ambiguous_predicate: str

    def __post_init__(self) -> None:
        if self.action_family not in ALLOWED_ACTIONS:
            raise ValueError("Outcome definition references an unsupported action")
        if not self.required_pre_state or not self.expected_post_state:
            raise ValueError("Outcome definition lacks state evidence")


@dataclass(frozen=True)
class CHRMLiteStepOutcomeRegistryV4_1(_Hashed):
    source_commit: str
    controller_contract_id: str
    evaluator_contract_id: str
    execution_budget_profile_id: str
    definitions: tuple[StepOutcomeDefinition, ...]
    controller_boolean_alone_sufficient: bool = False
    scientific_states: tuple[str, ...] = ("success", "scientific_failure")
    excluded_states: tuple[str, ...] = ("technical_failure", "ambiguous_unobservable")
    schema_version: int = SCHEMA_VERSION
    registry_id: str = ""

    _id_field = "registry_id"

    def __post_init__(self) -> None:
        families = [item.action_family for item in self.definitions]
        if set(families) != ALLOWED_ACTIONS or len(families) != len(set(families)):
            raise ValueError("Step outcome registry must cover every supported action family once")
        if self.controller_boolean_alone_sufficient:
            raise ValueError("Controller Boolean cannot be the sole step label")
        if self.registry_id and self.registry_id != self.compute_id():
            raise ValueError("Step outcome registry hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["definitions"] = [asdict(item) for item in self.definitions]
        payload["scientific_states"] = list(self.scientific_states)
        payload["excluded_states"] = list(self.excluded_states)
        return payload


REQUIRED_RECORD_SECTIONS = (
    "identity",
    "frozen_artifacts",
    "pre_execution",
    "post_execution",
    "label",
    "safety",
)


@dataclass(frozen=True)
class CHRMLiteDecisionRecordSchemaV4_1(_Hashed):
    source_commit: str
    planner_schema_id: str
    rule_registry_id: str
    retrieval_policy_id: str
    outcome_registry_id: str
    required_sections: tuple[str, ...] = REQUIRED_RECORD_SECTIONS
    pre_record_persisted_before_action: bool = True
    post_join_atomic: bool = True
    deterministic_duplicate_safe_ids: bool = True
    accepted_label_states: tuple[str, ...] = ("success", "scientific_failure")
    required_field_coverage: float = 1.0
    schema_version: int = SCHEMA_VERSION
    schema_id: str = ""

    _id_field = "schema_id"

    def __post_init__(self) -> None:
        if self.required_sections != REQUIRED_RECORD_SECTIONS:
            raise ValueError("Decision record sections changed")
        if not all(
            (
                self.pre_record_persisted_before_action,
                self.post_join_atomic,
                self.deterministic_duplicate_safe_ids,
            )
        ):
            raise ValueError("Decision record atomicity guard changed")
        if self.required_field_coverage != 1.0:
            raise ValueError("Formal Track E requires complete records")
        if self.schema_id and self.schema_id != self.compute_id():
            raise ValueError("Decision record schema hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["required_sections"] = list(self.required_sections)
        payload["accepted_label_states"] = list(self.accepted_label_states)
        return payload


@dataclass(frozen=True)
class CHRMLiteCollectionExclusionRegistry(_Hashed):
    source_commit: str
    class_policy: Mapping[str, Mapping[str, bool]]
    outcome_based_exclusions_permitted: bool = False
    historical_baseline_only: bool = True
    historical_v4_1_training_eligible: bool = False
    schema_version: int = SCHEMA_VERSION
    registry_id: str = ""

    _id_field = "registry_id"

    def __post_init__(self) -> None:
        expected = {
            "historical_rows",
            "engineering_smoke",
            "technical_failures",
            "ambiguous_labels",
            "holdout_final_rows",
            "failed_attempt_partial_records",
        }
        if set(self.class_policy) != expected:
            raise ValueError("Exclusion registry classes are incomplete")
        if self.outcome_based_exclusions_permitted or self.historical_v4_1_training_eligible:
            raise ValueError("Exclusion registry permits leakage")
        if self.registry_id and self.registry_id != self.compute_id():
            raise ValueError("Exclusion registry hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["class_policy"] = {
            key: dict(sorted(value.items()))
            for key, value in sorted(self.class_policy.items())
        }
        return payload


@dataclass(frozen=True)
class CHRMLiteSupportAndDegradationPolicy(_Hashed):
    source_commit: str
    parameter_provenance_policy_id: str
    dependency_support_threshold: int
    dependency_support_threshold_source: str
    formal_required_field_coverage: float = 1.0
    sparse_confidence_rule: str = "weighted_pav_adjacent_pooling"
    sparse_environment_rule: str = "undercovered_side_maps_to_unknown"
    sparse_horizon_rule: str = "shrink_to_global_development_l_fail"
    insufficient_revision_rule: str = "cdt_shadow_or_fixed_period"
    ambiguous_rule_policy: str = "excluded_from_knowledge_features"
    silent_imputation_permitted: bool = False
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        if self.dependency_support_threshold < 1:
            raise ValueError("Dependency support threshold must come from frozen Memory")
        if self.formal_required_field_coverage != 1.0 or self.silent_imputation_permitted:
            raise ValueError("Support policy permits incomplete formal rows")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("Support/degradation policy hash mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeDesign(_Hashed):
    source_commit: str
    authorization_id: str
    status: str = "draft_author_approval_required"
    approved_pool_id: str = ""
    assignments_fixed: bool = False
    assignment_count: int = 0
    engineering_only: bool = True
    formal_fitting_eligible: bool = False
    outcome_selected: bool = False
    required_dimensions: tuple[str, ...] = (
        "supported_action_families",
        "five_difficulties",
        "hard_rule_present",
        "soft_rule_present",
        "knowledge_unknown",
        "environment_matched_unknown_mismatch",
        "success_and_scientific_failure",
    )
    schema_version: int = SCHEMA_VERSION
    design_id: str = ""

    _id_field = "design_id"

    def __post_init__(self) -> None:
        if self.status != "draft_author_approval_required":
            raise ValueError("Unapproved smoke design cannot be activated")
        if self.approved_pool_id or self.assignments_fixed or self.assignment_count:
            raise ValueError("Smoke assignments require author approval")
        if not self.engineering_only or self.formal_fitting_eligible or self.outcome_selected:
            raise ValueError("Engineering smoke isolation changed")
        if self.design_id and self.design_id != self.compute_id():
            raise ValueError("Engineering smoke design hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["required_dimensions"] = list(self.required_dimensions)
        return payload


@dataclass(frozen=True)
class CDTReplayFeasibilityBlueprint(_Hashed):
    source_commit: str
    track_e_campaign_shared: bool = False
    separate_track_c_campaign_required: bool = True
    path_selected: str = "unselected"
    state_proof_fields: tuple[str, ...] = (
        "world_state_hash",
        "inventory",
        "position_orientation",
        "nearby_objects_blocks",
        "random_state_when_exposed",
        "controller_internal_state",
    )
    allowed_later_results: tuple[str, ...] = (
        "path_a_feasible",
        "path_a_infeasible_use_path_b",
        "unresolved",
    )
    rho_defined: bool = False
    rho_estimated: bool = False
    schema_version: int = SCHEMA_VERSION
    blueprint_id: str = ""

    _id_field = "blueprint_id"

    def __post_init__(self) -> None:
        if self.track_e_campaign_shared or not self.separate_track_c_campaign_required:
            raise ValueError("Track E and Track C must remain separate")
        if self.path_selected != "unselected" or self.rho_defined or self.rho_estimated:
            raise ValueError("Round 5.13C must not choose or estimate rho")
        if self.blueprint_id and self.blueprint_id != self.compute_id():
            raise ValueError("CDT replay blueprint hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["state_proof_fields"] = list(self.state_proof_fields)
        payload["allowed_later_results"] = list(self.allowed_later_results)
        return payload


@dataclass(frozen=True)
class CHRMLiteDevelopmentCollectionBlueprint(_Hashed):
    source_commit: str
    authorization_id: str
    seed_namespace_id: str
    rule_registry_id: str
    planner_schema_id: str
    retrieval_policy_id: str
    outcome_registry_id: str
    record_schema_id: str
    exclusion_registry_id: str
    support_policy_id: str
    smoke_design_id: str
    cdt_replay_blueprint_id: str
    track_e_mode: str = TRACK_E_MODE
    dev_train_terminal_tasks: int = 15
    dev_tune_terminal_tasks: int = 5
    dev_train_future_groups: int = 45
    dev_tune_future_groups: int = 15
    formal_assignments_generated: bool = False
    formal_campaign_started: bool = False
    historical_rows_used_for_fitting: bool = False
    evaluation_before_action_calls: int = 0
    memory_read_only: bool = True
    acquisition_writes_permitted: bool = False
    schema_version: int = SCHEMA_VERSION
    blueprint_id: str = ""

    _id_field = "blueprint_id"

    def __post_init__(self) -> None:
        if self.track_e_mode != TRACK_E_MODE:
            raise ValueError("Unexpected Track E runtime mode")
        if (
            self.dev_train_terminal_tasks,
            self.dev_tune_terminal_tasks,
            self.dev_train_future_groups,
            self.dev_tune_future_groups,
        ) != (15, 5, 45, 15):
            raise ValueError("Frozen terminal-task split or future group design changed")
        if any(
            (
                self.formal_assignments_generated,
                self.formal_campaign_started,
                self.historical_rows_used_for_fitting,
                self.evaluation_before_action_calls,
                self.acquisition_writes_permitted,
            )
        ) or not self.memory_read_only:
            raise ValueError("Collection blueprint opened a forbidden phase")
        if self.blueprint_id and self.blueprint_id != self.compute_id():
            raise ValueError("Collection blueprint hash mismatch")


def default_rule_definitions() -> tuple[RuleTypeDefinition, ...]:
    all_actions = tuple(sorted(ALLOWED_ACTIONS))
    return (
        RuleTypeDefinition(
            "mechanics.action_schema",
            "required_action_arguments",
            "hard",
            all_actions,
            "dc3pa.contracts.Action",
            "always",
        ),
        RuleTypeDefinition(
            "controller.required_tool",
            "required_inventory_tool",
            "hard",
            ("mine", "fight", "dig_down", "dig_up", "apply"),
            "legacy_controller.check_action_preparation",
            "when_tool_is_declared_or_frozen_mechanics_requires_it",
        ),
        RuleTypeDefinition(
            "controller.equip_inventory",
            "equipped_item_available",
            "hard",
            ("equip",),
            "legacy_controller.check_action_preparation",
            "always",
        ),
        RuleTypeDefinition(
            "controller.craft_material_quantity",
            "craft_material_quantity",
            "hard",
            ("craft",),
            "legacy_controller.check_action_preparation",
            "always",
        ),
        RuleTypeDefinition(
            "controller.craft_platform_access",
            "craft_platform_inventory_or_nearby",
            "hard",
            ("craft",),
            "legacy_controller.check_action_preparation",
            "when_platform_is_declared",
        ),
        RuleTypeDefinition(
            "memory.verified_dependency",
            "verified_progress_dependency",
            "soft",
            ("mine", "craft", "fight", "equip", "dig_down", "dig_up", "apply"),
            "paper_memory_v5.dependency_edges",
            "success_count_at_least_frozen_min_dependency_support",
        ),
        RuleTypeDefinition(
            "environment.target_visibility",
            "target_visible_or_recently_observed",
            "soft",
            ("find", "move_to", "mine", "fight", "apply"),
            "minedojo_structured_observation",
            "when_target_observation_is_available",
        ),
        RuleTypeDefinition(
            "ambiguous.recipe_necessity",
            "unverified_recipe_or_strategy_necessity",
            "excluded_ambiguous",
            ("craft", "mine", "fight", "equip", "dig_down", "dig_up", "apply"),
            "unverified_or_strategy_dependent_rule",
            "never",
        ),
    )


def default_outcome_definitions() -> tuple[StepOutcomeDefinition, ...]:
    common_technical = "controller_exception_or_environment_infrastructure_failure"
    common_ambiguous = "required_structured_pre_or_post_evidence_missing"
    return (
        StepOutcomeDefinition("find", ("target", "observation"), ("target_visibility", "distance"), "find_action_budget", "target_becomes_visible_or_localized", "budget_exhausted_and_target_observably_absent", common_technical, common_ambiguous),
        StepOutcomeDefinition("move_to", ("target", "position_or_distance"), ("target_distance",), "move_action_budget", "target_distance_reaches_interaction_threshold", "budget_exhausted_with_observed_distance_above_threshold", common_technical, common_ambiguous),
        StepOutcomeDefinition("mine", ("target", "inventory", "target_block_state"), ("inventory_delta", "target_block_state"), "mine_action_budget", "target_item_inventory_increases_or_target_block_is_removed", "budget_exhausted_with_observed_no_transition", common_technical, common_ambiguous),
        StepOutcomeDefinition("craft", ("recipe_output", "inventory", "platform_state"), ("inventory_delta",), "craft_action_budget", "crafted_output_inventory_increases", "budget_exhausted_with_observed_no_output", common_technical, common_ambiguous),
        StepOutcomeDefinition("fight", ("target_entity", "entity_state"), ("target_entity_state",), "fight_action_budget", "target_entity_is_defeated_or_removed", "budget_exhausted_with_target_observably_active", common_technical, common_ambiguous),
        StepOutcomeDefinition("equip", ("item", "inventory", "held_item"), ("held_item",), "equip_action_budget", "held_item_matches_requested_item", "budget_exhausted_with_observed_held_item_mismatch", common_technical, common_ambiguous),
        StepOutcomeDefinition("dig_down", ("position", "target_y"), ("position", "underground_state"), "dig_action_budget", "post_y_reaches_target_or_decreases_as_required", "budget_exhausted_with_observed_y_transition_absent", common_technical, common_ambiguous),
        StepOutcomeDefinition("dig_up", ("position", "underground_state"), ("position", "underground_state"), "dig_action_budget", "post_y_increases_and_surface_state_is_reached", "budget_exhausted_with_observed_upward_transition_absent", common_technical, common_ambiguous),
        StepOutcomeDefinition("apply", ("target", "tool", "object_state"), ("object_state", "inventory_or_durability_delta"), "apply_action_budget", "target_object_state_changes_as_requested", "budget_exhausted_with_observed_no_target_transition", common_technical, common_ambiguous),
    )


def default_exclusion_policy() -> dict[str, dict[str, bool]]:
    def item(audit: bool, channel: bool, chrm: bool, cdt: bool) -> dict[str, bool]:
        return {
            "retained_for_audit": audit,
            "eligible_for_channel_calibration": channel,
            "eligible_for_chrm_fitting": chrm,
            "eligible_for_cdt_identification": cdt,
        }

    return {
        "historical_rows": item(True, False, False, False),
        "engineering_smoke": item(True, False, False, False),
        "technical_failures": item(True, False, False, False),
        "ambiguous_labels": item(True, False, False, False),
        "holdout_final_rows": item(True, False, False, False),
        "failed_attempt_partial_records": item(True, False, False, False),
    }


def build_collection_contracts(
    *,
    source_commit: str,
    method_contract_id: str,
    historical_data_decision_id: str,
    dependency_schema_id: str,
    paper_memory_v5_release_id: str,
    scene_exemplar_release_id: str,
    mineclip_policy_id: str,
    parameter_provenance_policy_id: str,
    controller_contract_id: str,
    evaluator_contract_id: str,
    execution_budget_profile_id: str,
    excluded_seed_namespace_ids: Sequence[str],
    dependency_support_threshold: int,
) -> tuple[Any, ...]:
    authorization = CHRMLiteDevelopmentCollectionAuthorization(
        source_commit=source_commit,
        method_contract_id=method_contract_id,
        historical_data_decision_id=historical_data_decision_id,
    ).with_computed_id()
    namespace = CHRMLiteDevelopmentSeedNamespace(
        source_commit=source_commit,
        authorization_id=authorization.authorization_id,
        excluded_namespace_ids=tuple(sorted(set(excluded_seed_namespace_ids))),
    ).with_computed_id()
    rules = CHRMLiteRuleTypeRegistryV4_1(
        source_commit=source_commit,
        dependency_schema_id=dependency_schema_id,
        rules=default_rule_definitions(),
    ).with_computed_id()
    planner = CHRMLitePlannerOutputSchemaV4_1(source_commit=source_commit).with_computed_id()
    retrieval = CHRMLiteBilateralRetrievalPolicyV4_1(
        source_commit=source_commit,
        paper_memory_v5_release_id=paper_memory_v5_release_id,
        scene_exemplar_release_id=scene_exemplar_release_id,
        mineclip_policy_id=mineclip_policy_id,
    ).with_computed_id()
    outcomes = CHRMLiteStepOutcomeRegistryV4_1(
        source_commit=source_commit,
        controller_contract_id=controller_contract_id,
        evaluator_contract_id=evaluator_contract_id,
        execution_budget_profile_id=execution_budget_profile_id,
        definitions=default_outcome_definitions(),
    ).with_computed_id()
    records = CHRMLiteDecisionRecordSchemaV4_1(
        source_commit=source_commit,
        planner_schema_id=planner.schema_id,
        rule_registry_id=rules.registry_id,
        retrieval_policy_id=retrieval.policy_id,
        outcome_registry_id=outcomes.registry_id,
    ).with_computed_id()
    exclusion = CHRMLiteCollectionExclusionRegistry(
        source_commit=source_commit,
        class_policy=default_exclusion_policy(),
    ).with_computed_id()
    support = CHRMLiteSupportAndDegradationPolicy(
        source_commit=source_commit,
        parameter_provenance_policy_id=parameter_provenance_policy_id,
        dependency_support_threshold=dependency_support_threshold,
        dependency_support_threshold_source="paper_memory_v5.min_dependency_support",
    ).with_computed_id()
    smoke = CHRMLiteEngineeringSmokeDesign(
        source_commit=source_commit,
        authorization_id=authorization.authorization_id,
    ).with_computed_id()
    replay = CDTReplayFeasibilityBlueprint(source_commit=source_commit).with_computed_id()
    blueprint = CHRMLiteDevelopmentCollectionBlueprint(
        source_commit=source_commit,
        authorization_id=authorization.authorization_id,
        seed_namespace_id=namespace.namespace_id,
        rule_registry_id=rules.registry_id,
        planner_schema_id=planner.schema_id,
        retrieval_policy_id=retrieval.policy_id,
        outcome_registry_id=outcomes.registry_id,
        record_schema_id=records.schema_id,
        exclusion_registry_id=exclusion.registry_id,
        support_policy_id=support.policy_id,
        smoke_design_id=smoke.design_id,
        cdt_replay_blueprint_id=replay.blueprint_id,
    ).with_computed_id()
    return (
        authorization,
        blueprint,
        namespace,
        rules,
        planner,
        retrieval,
        outcomes,
        records,
        exclusion,
        support,
        smoke,
        replay,
    )
