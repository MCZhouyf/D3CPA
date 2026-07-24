from dc3pa.contracts import ALLOWED_ACTIONS
from dc3pa.experiments.round513_collection import (
    PLANNER_OUTPUT_SCHEMA,
    build_collection_contracts,
)


def _contracts():
    return build_collection_contracts(
        source_commit="a" * 40,
        method_contract_id="m" * 64,
        historical_data_decision_id=(
            "82de675a8f9b37cfdb06f7d74f75b2b6e9b55561bf5299a7b1f6c2da9f429e89"
        ),
        dependency_schema_id="d" * 64,
        paper_memory_v5_release_id="p" * 64,
        scene_exemplar_release_id="s" * 64,
        mineclip_policy_id="i" * 64,
        parameter_provenance_policy_id="v" * 64,
        controller_contract_id="c" * 64,
        evaluator_contract_id="e" * 64,
        execution_budget_profile_id="b" * 64,
        excluded_seed_namespace_ids=("acquisition", "historical", "holdout", "final"),
        dependency_support_threshold=2,
    )


def test_round513c_is_pending_and_generates_no_formal_seed_or_assignment():
    authorization, blueprint, namespace, *_ = _contracts()
    assert authorization.status == "pending_author_approval"
    assert not authorization.author_approved
    assert not authorization.engineering_smoke_approved
    assert not blueprint.formal_assignments_generated
    assert not blueprint.formal_campaign_started
    assert namespace.formal_seed_count == 0
    assert not namespace.plaintext_seeds_stored


def test_terminal_task_split_and_future_group_design_are_frozen():
    _authorization, blueprint, *_ = _contracts()
    assert (
        blueprint.dev_train_terminal_tasks,
        blueprint.dev_tune_terminal_tasks,
        blueprint.dev_train_future_groups,
        blueprint.dev_tune_future_groups,
    ) == (15, 5, 45, 15)


def test_historical_decision_d_is_enforced_and_old_rows_are_ineligible():
    authorization, blueprint, *_rest = _contracts()
    exclusion = _rest[6]
    assert authorization.historical_data_decision_id.startswith("82de675a")
    assert not blueprint.historical_rows_used_for_fitting
    assert exclusion.historical_baseline_only
    assert not exclusion.historical_v4_1_training_eligible
    assert not exclusion.class_policy["historical_rows"]["eligible_for_chrm_fitting"]


def test_rule_registry_is_outcome_free_and_covers_supported_actions():
    contracts = _contracts()
    rules = contracts[3]
    assert not rules.labels_available_to_classifier
    assert not rules.hard_rules_enter_soft_coverage
    counts = rules.counts_by_action_family()
    assert set(counts) == ALLOWED_ACTIONS
    assert all(sum(value.values()) >= 1 for value in counts.values())


def test_planner_and_bilateral_contracts_forbid_extra_online_calls():
    contracts = _contracts()
    planner = contracts[4]
    retrieval = contracts[5]
    assert planner.calls_per_decision == 1
    assert not planner.extra_confidence_call_permitted
    assert planner.prompt_id and planner.parser_id
    assert retrieval.top_k_per_side == 3
    assert retrieval.minimum_count_per_side == 3
    assert retrieval.online_llm_calls == 0
    assert not retrieval.full_library_max_shortcut_permitted


def test_planner_schema_names_exact_controller_arguments_for_every_action():
    variants = PLANNER_OUTPUT_SCHEMA["properties"]["action"]["oneOf"]
    required_by_action = {
        variant["properties"]["name"]["enum"][0]: set(
            variant["properties"]["arguments"]["required"]
        )
        for variant in variants
    }
    assert required_by_action == {
        "find": {"obj"},
        "move_to": {"obj"},
        "mine": {"obj", "tool"},
        "craft": {"obj", "materials", "platform"},
        "fight": {"obj", "tool"},
        "equip": {"obj"},
        "dig_down": {"y_level", "tool"},
        "dig_up": {"tool"},
        "apply": {"obj", "tool"},
    }
    assert set(required_by_action) == ALLOWED_ACTIONS


def test_step_registry_and_exclusion_registry_are_complete():
    contracts = _contracts()
    outcomes = contracts[6]
    exclusion = contracts[8]
    assert {item.action_family for item in outcomes.definitions} == ALLOWED_ACTIONS
    assert not outcomes.controller_boolean_alone_sufficient
    assert all(
        item["retained_for_audit"] for item in exclusion.class_policy.values()
    )
    assert not any(
        item["eligible_for_chrm_fitting"]
        for item in exclusion.class_policy.values()
    )


def test_smoke_and_cdt_blueprints_remain_unapproved_and_unestimated():
    contracts = _contracts()
    smoke = contracts[10]
    replay = contracts[11]
    assert smoke.status == "draft_author_approval_required"
    assert not smoke.assignments_fixed
    assert smoke.assignment_count == 0
    assert replay.path_selected == "unselected"
    assert not replay.rho_defined
    assert not replay.rho_estimated
