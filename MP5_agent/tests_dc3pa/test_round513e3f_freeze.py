import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from dc3pa.experiments.round513_collection import CHRMLitePlannerOutputSchemaV4_1
from dc3pa.experiments.round513_instrumentation import OneCallPlannerV4_1, PlannerOutputError
from dc3pa.experiments.round513e2h import canonical_sha256, file_sha256
from dc3pa.experiments.round513e3f import (
    BOUNDARY_A_APPROVAL_REQUIRED_LITERALS,
    CHRMLiteEngineeringSmokeAssignmentsV4_1_2_E3,
    CHRMLiteEngineeringSmokePoolV4_1_2_E3,
    CONTROLLER_ACTION_ARGUMENTS,
    FORMAL_CATALOG_CANONICAL_SHA256,
    FORMAL_TASKSET_RELEASE_ID,
    HISTORICAL_E2H_ASSIGNMENTS_ID,
    HISTORICAL_E2H_AUTHORIZATION_INPUT_ID,
    HISTORICAL_E2H_SEAL_ID,
    Round513E2TechnicalCampaignCloseout,
    Round513E3ContractCompatibilityRelease,
    build_decision_inputs,
    build_provider_contracts,
    build_task_asset_audit,
    derive_authorized_e3_assignments,
    validate_boundary_a_approval,
    validate_action_schema,
)
from dc3pa.experiments.round513e_authoritative import (
    derive_formal_50_task_smoke_assignments,
)
from dc3pa.integration.providers import (
    TRACK_E_MAX_OUTPUT_TOKENS,
    TRACK_E_TIMEOUT_SECONDS,
    ChatModelTextAdapter,
    configure_track_e_chat_model,
)
from dc3pa.contracts import AgentState


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
EXTERNAL = (
    Path(os.environ["DC3PA_EXTERNAL_ROOT"])
    if "DC3PA_EXTERNAL_ROOT" in os.environ
    else Path(Path.cwd().anchor) / "external" / "dc3pa"
)
FORMAL = EXTERNAL / "round5101_active_taskset_final"
E2H = EXTERNAL / "round513e2h/a329fd9"
SOURCE = "01cba8dc66e6caf10b378f9be9ca0907b9dc4f25"


def _verify_hashed_file(path, id_field, expected):
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload[id_field] == expected
    canonical = dict(payload)
    canonical.pop(id_field)
    assert canonical_sha256(canonical) == expected


def test_historical_e2h_objects_remain_reconstructable_and_immutable():
    root = E2H / "source-hardened-smoke-prep"
    _verify_hashed_file(
        root / "engineering_smoke_assignments_v4_1_2_r1.json",
        "assignments_id",
        HISTORICAL_E2H_ASSIGNMENTS_ID,
    )
    _verify_hashed_file(
        root / "engineering_smoke_seal_v4_1_2_r1.json",
        "seal_id",
        HISTORICAL_E2H_SEAL_ID,
    )
    _verify_hashed_file(
        root / "engineering_smoke_authorization_input_v4_1_2_r1.json",
        "authorization_input_id",
        HISTORICAL_E2H_AUTHORIZATION_INPUT_ID,
    )


def test_e2_campaign_closeout_cannot_become_scientific_data():
    summary = E2H / "campaigns/e45d2cc6a1ab/final_campaign_summary.json"
    report = E2H / "campaigns/e45d2cc6a1ab/FINAL_CAMPAIGN_REPORT.md"
    closeout = Round513E2TechnicalCampaignCloseout(
        source_commit=SOURCE,
        campaign_id="e45d2cc6a1ab811863a88093a5d7d28cbf86e4e3285f13f0fa402d5c169e7368",
        campaign_summary_file_sha256=file_sha256(summary),
        campaign_report_file_sha256=file_sha256(report),
    ).with_id()
    assert closeout.campaign_class == "pre_action_technical_failure"
    assert closeout.scientific_records == 0
    with pytest.raises(ValueError, match="scientific data"):
        replace(closeout, closeout_id="", reusable_as_scientific_data=True)


def test_planner_runtime_contract_binds_schema_parser_policy_and_all_actions():
    schema, policy, contract, receipt = build_provider_contracts(SOURCE)
    validate_action_schema(schema.output_schema)
    assert set(contract.controller_action_arguments) == set(CONTROLLER_ACTION_ARGUMENTS)
    assert contract.planner_schema_id == schema.schema_id
    assert contract.prompt_template_id == schema.prompt_id
    assert contract.parser_id == schema.parser_id
    assert contract.provider_request_policy_id == policy.policy_id
    assert policy.response_format == {"type": "json_object"}
    assert policy.scope == "track_e_planner_only"
    assert not policy.plain_text_fallback_permitted
    assert not policy.hidden_planner_retry_permitted
    assert receipt.planner_call_count == 1
    assert receipt.probe_source_commit == SOURCE
    assert not receipt.raw_provider_response_persisted
    assert not receipt.api_key_persisted


def test_one_call_planner_uses_bound_schema_and_has_no_malformed_retry():
    class Provider:
        def __init__(self, response):
            self.response = response
            self.calls = 0

        def complete(self, prompt):
            self.calls += 1
            assert '"obj"' in prompt
            return self.response

    valid = json.dumps({
        "subgoal": "find a tree",
        "action": {"name": "find", "arguments": {"obj": "log"}},
        "confidence": "very_likely",
        "failure_mode": "none",
    })
    schema = CHRMLitePlannerOutputSchemaV4_1(source_commit=SOURCE).with_computed_id()
    provider = Provider(valid)
    planner = OneCallPlannerV4_1(provider, schema)
    state = AgentState(task="mine log", inventory={})
    planner.plan("mine log", state)
    assert provider.calls == planner.call_count == 1

    malformed = Provider("```json\n{}\n```")
    planner = OneCallPlannerV4_1(malformed, schema)
    with pytest.raises(PlannerOutputError, match="response_is_not_strict_json"):
        planner.plan("mine log", state)
    assert malformed.calls == planner.call_count == 1


def test_track_e_model_configuration_disables_hidden_sdk_retries():
    class Model:
        temperature = 1
        max_tokens = None
        request_timeout = 10
        max_retries = 6

    model = Model()
    configured = configure_track_e_chat_model(model)
    assert configured is not model
    assert configured.temperature == 0
    assert configured.max_tokens == TRACK_E_MAX_OUTPUT_TOKENS
    assert configured.request_timeout == TRACK_E_TIMEOUT_SECONDS
    assert configured.max_retries == 0
    assert model.temperature == 1
    assert model.max_retries == 6

    class PlainModel:
        pass

    with pytest.raises(TypeError, match="does not expose"):
        configure_track_e_chat_model(PlainModel())


def test_json_request_kwargs_are_adapter_local_not_inherited():
    calls = []

    class Model:
        def predict(self, prompt, **kwargs):
            calls.append(kwargs)
            return "ok"

    model = Model()
    ChatModelTextAdapter(model, {"response_format": {"type": "json_object"}}).complete("track-e")
    ChatModelTextAdapter(model).complete("legacy")
    assert calls == [{"response_format": {"type": "json_object"}}, {}]


@pytest.mark.minedojo
def test_formal_catalog_and_asset_audit_exposes_every_current_conflict():
    audit = build_task_asset_audit(source_commit=SOURCE, agent_root=ROOT, formal_root=FORMAL)
    assert audit.formal_taskset_release_id == FORMAL_TASKSET_RELEASE_ID
    assert audit.catalog_canonical_sha256 == FORMAL_CATALOG_CANONICAL_SHA256
    assert audit.candidate_count == audit.catalog_match_count == 9
    assert audit.difficulty_match_count == 7
    assert audit.repository_asset_exists_count == audit.authoritative_asset_exists_count == 9
    assert audit.exact_asset_sha_match_count == 0
    assert audit.semantic_asset_match_count == 4
    assert audit.status == "BLOCKED"
    assert all(row["formal_task"] not in {"pig", "creature"} for row in audit.rows)


@pytest.mark.minedojo
def test_iron_ingot_and_proxy_decisions_fail_closed_at_author_boundary():
    audit = build_task_asset_audit(source_commit=SOURCE, agent_root=ROOT, formal_root=FORMAL)
    iron, proxy_audit, proxy = build_decision_inputs(source_commit=SOURCE, task_audit=audit)
    assert iron.repository_iron_ore_requirement == 8
    assert iron.authoritative_iron_ore_requirement == 1
    assert iron.runtime_material_semantics == "required_inventory_quantity_checked_then_consumed_by_legacy_craft_mapping"
    assert iron.semantic_process_family == "smelt"
    assert iron.controller_action_family == "craft"
    assert not iron.source_freeze_permitted and not iron.assignment_seal_permitted
    assert proxy_audit.proxy_count == 3
    assert proxy_audit.natural_coverage_claim_count == 0
    assert proxy_audit.observed_coverage_claim_count == 0
    assert tuple(choice["id"] for choice in proxy.choices) == ("P1", "P2", "P3")
    assert not proxy.source_freeze_permitted and not proxy.assignment_seal_permitted


def test_new_pipeline_is_independent_and_cannot_overwrite_historical_paths():
    script = ROOT / "scripts_dc3pa/freeze_round513e3_authorization.py"
    text = script.read_text(encoding="utf-8")
    assert "freeze_round513e2h_reauthorization" not in text
    assert "O_EXCL" in text
    assert "stage6_run_minecraft" not in text
    assert '"minedojo_execution_permitted": False' in text


@pytest.mark.minedojo
def test_authorized_alignment_preserves_task_seed_order_and_binds_formal_assets():
    namespace_label = "dc3pa-round513e3-formal50-engineering-smoke-v4.1.2"
    old_namespace, old = derive_formal_50_task_smoke_assignments(
        source_commit=SOURCE, namespace_label=namespace_label,
    )
    namespace, aligned = derive_authorized_e3_assignments(
        source_commit=SOURCE, formal_root=FORMAL, namespace_label=namespace_label,
    )
    assert namespace == old_namespace
    assert [item.terminal_task for item in aligned] == [item.terminal_task for item in old]
    assert [item.seed for item in aligned] == [item.seed for item in old]
    assert [item.order for item in aligned] == list(range(9))
    assert [item.target_action_family for item in aligned] == [item.target_action_family for item in old]
    assert {item.formal_task_name: item.difficulty for item in aligned}["mine cobblestone"] == "medium"
    assert {item.formal_task_name: item.difficulty for item in aligned}["mine sapling"] == "basic"
    for item in aligned:
        asset = FORMAL / item.task_path_label
        assert asset.is_file()
        assert file_sha256(asset) == item.task_file_sha256
    proxies = [item for item in aligned if item.coverage_naturalness == "proxy_only"]
    assert len(proxies) == 3
    assert all(not item.natural_action_coverage_eligible for item in proxies)
    assert all(item.observed_runtime_coverage == "not_observed_before_execution" for item in aligned)


def test_boundary_a_approval_validation_is_exact_and_fail_closed():
    validate_boundary_a_approval(" ".join(BOUNDARY_A_APPROVAL_REQUIRED_LITERALS))
    with pytest.raises(ValueError, match="incomplete"):
        validate_boundary_a_approval("selecting P1; approved_by=ZYF")


@pytest.mark.minedojo
def test_e3_pool_and_assignments_remain_engineering_only():
    namespace, rows = derive_authorized_e3_assignments(
        source_commit=SOURCE,
        formal_root=FORMAL,
        namespace_label="dc3pa-round513e3-formal50-engineering-smoke-v4.1.2",
    )
    pool = CHRMLiteEngineeringSmokePoolV4_1_2_E3(
        source_commit=SOURCE, namespace_id=namespace,
        task_asset_audit_id="a" * 64, proxy_policy="P1", assignment_count=9,
    ).with_id()
    assignments = CHRMLiteEngineeringSmokeAssignmentsV4_1_2_E3(
        source_commit=SOURCE, namespace_id=namespace,
        runtime_release_id="b" * 64, assignments=rows,
    ).with_id()
    assert pool.engineering_only and not pool.fitting_eligible
    assert all(item.engineering_only for item in assignments.assignments)
    assert all(not item.formal_fitting_eligible for item in assignments.assignments)


def test_e3_compatibility_rejects_old_authorization_and_silent_downgrade():
    release = Round513E3ContractCompatibilityRelease(
        source_commit=SOURCE, source_freeze_audit_id="a" * 64,
        historical_compatibility_release_id="b" * 64,
        provider_request_policy_id="c" * 64,
        planner_runtime_request_contract_id="d" * 64,
        planner_schema_id="e" * 64, parser_id="f" * 64,
        historical_e1r_e2h_reconstructable=True,
    ).with_id()
    assert not release.old_authorization_accepted
    with pytest.raises(ValueError, match="weakens version isolation"):
        replace(release, release_id="", old_authorization_accepted=True)


def test_final_freeze_script_stops_at_boundary_b_without_launching_runner():
    text = (ROOT / "scripts_dc3pa/freeze_round513e3_final_authorization.py").read_text(
        encoding="utf-8"
    )
    assert "stage6_run_minecraft" not in text
    assert '"minedojo_started": False' in text
    assert '"authorization_status": "pending_ZYF_boundary_B"' in text
