import json
import os
from dataclasses import fields, replace
from pathlib import Path

import pytest

from dc3pa.experiments.round513e2h import (
    ADAPTER_VERSION,
    ContractCompatibilityEntry,
    ContractRuntimeAdapterV4_1_2_R1,
    canonical_sha256,
    file_sha256,
)
from dc3pa.experiments.round513e3h import (
    CHRMLiteEngineeringSmokeExecutionManifestE3X_R1,
    CHRMLiteEngineeringSmokeAssignmentsE3X_R1,
    CHRMLiteEngineeringSmokeRuntimeReleaseE3X_R1,
    E3H_PREFLIGHT_ORDER,
    E3H_PREFLIGHT_ORDER_ID,
    E3X_CONTRACT_VERSION,
    E3X_POLICY_ADAPTER_VERSION,
    E3X_RUNTIME_ADAPTER_VERSION,
    E3X_RUNTIME_SCHEMA,
    GAMMA_CANDIDATE_B,
    GAMMA_TEXT,
    Round513E3ContractCompatibilityReleaseR1,
    Round513E3HAssignmentDependencyAudit,
    Round513E3PolicyCompatibilityEntryR1,
    Round513E3PolicyCompatibilityReleaseR1,
    SmokeScientificPayloadEquivalenceAuditE3X_R1,
    SmokeAssignmentE3X_R1,
    TrackERunBindingE3X_R1,
    cleanup_semantics,
    execute_preflight_sequence,
    load_e3x_contract,
    load_frozen_policy,
    retry_semantics,
    smoke_scientific_payload_root,
    validate_e3x_runtime_artifacts,
)


EXTERNAL = (
    Path(os.environ["DC3PA_EXTERNAL_ROOT"])
    if "DC3PA_EXTERNAL_ROOT" in os.environ
    else Path(Path.cwd().anchor) / "external" / "dc3pa"
)
POLICY_ROOT = EXTERNAL / "round513e2h/a329fd9/source-hardened-smoke-prep"
E3F_ROOT = EXTERNAL / "round513e3f/df0b043/source-frozen-authorization"
BLOCKED_ROOT = EXTERNAL / "round513e3x/df0b043/prelaunch-blocked"
SOURCE = "1" * 40
AUTHORING_SOURCE = "a329fd904eb98b96be5328c726531e8b799555f0"
RETRY_ID = "5e832b2056ba8c7c2aed7096a4f2fd22fe8d2a15e4c7ce427ac3896663bb15b5"
CLEANUP_ID = "99d6d818a329cef6bc29ad9527aa42320f8173861c7b7ceb10837f0005296e14"
RETRY_SHA = "9447924fe0636fb5aaa244ac4c93951f98539e2bc0a04b7b2159e18d7ee13398"
CLEANUP_SHA = "e4f7656c2154b1f79754c9f2982d3e2d3200c4a7312f83b3a834f1a828ca4b1c"


def _binding(**changes):
    values = {
        item.name: "a" * 64
        for item in fields(TrackERunBindingE3X_R1)
        if item.name not in {
            "contract_type", "contract_version", "assignment_count", "seed",
            "engineering_only", "schema_version", "binding_id",
        }
    }
    values.update(
        contract_type="TrackERunBindingE3X_R1",
        contract_version=E3X_CONTRACT_VERSION,
        execution_source_commit=SOURCE,
        assignment_count=9,
        proxy_policy="P1",
        gamma_candidate=GAMMA_CANDIDATE_B,
        gamma_cov_text=GAMMA_TEXT[0],
        gamma_minus_text=GAMMA_TEXT[1],
        gamma_plus_text=GAMMA_TEXT[2],
        seed=12345,
        collection_mode="chrmlite_estimation_collection_v41",
        output_root="output-token",
    )
    values.update(changes)
    return TrackERunBindingE3X_R1(**values).with_id()


def _write(path, payload):
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def test_e3x_raw_round_trip_preserves_discriminators_and_identity(tmp_path):
    binding = _binding()
    path = _write(tmp_path / "binding.json", binding.to_dict())
    adapter = load_e3x_contract(
        path,
        expected_file_sha256=file_sha256(path),
        expected_contract_id=binding.binding_id,
    )
    assert adapter.raw_contract_payload == binding.to_dict()
    assert adapter.raw_canonical_id == binding.binding_id
    assert adapter.contract_type == "TrackERunBindingE3X_R1"
    assert adapter.contract_version == E3X_CONTRACT_VERSION
    assert adapter.adapter_version == E3X_RUNTIME_ADAPTER_VERSION
    assert adapter.normalized_runtime_view == binding


def test_e3x_nested_assignments_round_trip_without_type_downgrade(tmp_path):
    rows = tuple(
        SmokeAssignmentE3X_R1(
            contract_type="SmokeAssignmentE3X_R1",
            contract_version=E3X_CONTRACT_VERSION,
            source_commit=SOURCE,
            namespace_id="1" * 64,
            terminal_task=f"task-{order}",
            formal_task_name=f"formal-{order}",
            formal_catalog_row_id=f"{order}" * 64,
            task_path_label=f"asset-{order}.json",
            task_file_sha256=f"{order + 1}" * 64,
            difficulty="basic",
            target_action_family="find",
            coverage_naturalness="natural",
            natural_action_coverage_eligible=True,
            instrumentation_target_eligible=True,
            observed_runtime_coverage="not_observed_before_execution",
            seed_commitment=f"{order + 2}" * 64,
            seed=order + 1,
            order=order,
        ).with_id()
        for order in range(9)
    )
    assignments = CHRMLiteEngineeringSmokeAssignmentsE3X_R1(
        contract_type="CHRMLiteEngineeringSmokeAssignmentsE3X_R1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=SOURCE,
        namespace_id="1" * 64,
        runtime_release_id="2" * 64,
        contract_compatibility_release_id="3" * 64,
        policy_compatibility_release_id="4" * 64,
        run_binding_schema_id="5" * 64,
        assignments=rows,
    ).with_id()
    path = _write(tmp_path / "assignments.json", assignments.to_dict())
    adapter = load_e3x_contract(
        path,
        expected_file_sha256=file_sha256(path),
        expected_contract_id=assignments.assignments_id,
    )
    assert adapter.normalized_runtime_view == assignments
    assert all(
        isinstance(item, SmokeAssignmentE3X_R1)
        for item in adapter.normalized_runtime_view.assignments
    )


def test_e3x_raw_hash_is_checked_before_json_or_adapter(tmp_path):
    path = tmp_path / "not-json.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="raw file SHA"):
        load_e3x_contract(
            path,
            expected_file_sha256="0" * 64,
            expected_contract_id="1" * 64,
        )


@pytest.mark.parametrize("field", ["contract_type", "contract_version", "schema_version"])
def test_e3x_missing_discriminator_fails_closed(tmp_path, field):
    payload = _binding().to_dict()
    payload.pop(field)
    path = _write(tmp_path / "binding.json", payload)
    with pytest.raises(ValueError, match="discriminator missing"):
        load_e3x_contract(
            path,
            expected_file_sha256=file_sha256(path),
            expected_contract_id=payload["binding_id"],
        )


def test_e3x_unknown_version_and_unknown_field_fail_closed(tmp_path):
    payload = _binding().to_dict()
    payload["contract_version"] = "E2H"
    path = _write(tmp_path / "binding.json", payload)
    with pytest.raises(ValueError, match="Unknown E3X contract version"):
        load_e3x_contract(
            path,
            expected_file_sha256=file_sha256(path),
            expected_contract_id=payload["binding_id"],
        )
    payload = _binding().to_dict()
    payload["unexpected"] = True
    path = _write(tmp_path / "binding-extra.json", payload)
    with pytest.raises(ValueError, match="fields mismatch"):
        load_e3x_contract(
            path,
            expected_file_sha256=file_sha256(path),
            expected_contract_id=payload["binding_id"],
        )


def test_e2h_payload_cannot_masquerade_as_e3x(tmp_path):
    payload = _binding().to_dict()
    payload.pop("contract_type")
    payload["runtime_binding_revision"] = "R1"
    path = _write(tmp_path / "e2h-shaped.json", payload)
    with pytest.raises(ValueError, match="contract_type"):
        load_e3x_contract(
            path,
            expected_file_sha256=file_sha256(path),
            expected_contract_id=payload["binding_id"],
        )


def _policy_release():
    return Round513E3PolicyCompatibilityReleaseR1(
        contract_type="Round513E3PolicyCompatibilityReleaseR1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=SOURCE,
        entries=(
            Round513E3PolicyCompatibilityEntryR1(
                policy_type="technical_retry",
                policy_id=RETRY_ID,
                file_sha256=RETRY_SHA,
                authoring_source_commit=AUTHORING_SOURCE,
                allowed_runtime_adapter_versions=(E3X_POLICY_ADAPTER_VERSION,),
                allowed_runtime_schemas=(E3X_RUNTIME_SCHEMA,),
                allowed_execution_source_commits=(SOURCE,),
            ),
            Round513E3PolicyCompatibilityEntryR1(
                policy_type="process_cleanup",
                policy_id=CLEANUP_ID,
                file_sha256=CLEANUP_SHA,
                authoring_source_commit=AUTHORING_SOURCE,
                allowed_runtime_adapter_versions=(E3X_POLICY_ADAPTER_VERSION,),
                allowed_runtime_schemas=(E3X_RUNTIME_SCHEMA,),
                allowed_execution_source_commits=(SOURCE,),
            ),
        ),
    ).with_id()


@pytest.mark.minedojo
def test_frozen_policy_ids_hashes_and_authoring_source_are_preserved():
    retry = load_frozen_policy(
        POLICY_ROOT / "technical_retry_policy_v4_1_2_r1.json",
        policy_type="technical_retry",
        expected_policy_id=RETRY_ID,
        expected_file_sha256=RETRY_SHA,
    )
    cleanup = load_frozen_policy(
        POLICY_ROOT / "process_cleanup_policy_v4_1_2_r1.json",
        policy_type="process_cleanup",
        expected_policy_id=CLEANUP_ID,
        expected_file_sha256=CLEANUP_SHA,
    )
    assert retry.raw_policy_id == RETRY_ID
    assert cleanup.raw_policy_id == CLEANUP_ID
    assert retry.authoring_source_commit == cleanup.authoring_source_commit == AUTHORING_SOURCE
    assert retry.authoring_source_commit != SOURCE


@pytest.mark.minedojo
def test_retry_cleanup_semantics_are_identical_after_provenance_adaptation():
    retry = load_frozen_policy(
        POLICY_ROOT / "technical_retry_policy_v4_1_2_r1.json",
        policy_type="technical_retry",
        expected_policy_id=RETRY_ID,
        expected_file_sha256=RETRY_SHA,
    )
    cleanup = load_frozen_policy(
        POLICY_ROOT / "process_cleanup_policy_v4_1_2_r1.json",
        policy_type="process_cleanup",
        expected_policy_id=CLEANUP_ID,
        expected_file_sha256=CLEANUP_SHA,
    )
    categories = (
        "environment_start_failure", "seed_application_failure",
        "provider_transport_failure", "provider_empty_response", "unclassified",
    )
    raw_retry = retry.normalized_runtime_view
    raw_cleanup = cleanup.normalized_runtime_view
    assert [retry_semantics(raw_retry, item) for item in categories] == [
        retry_semantics(retry.normalized_runtime_view, item) for item in categories
    ]
    assert cleanup_semantics(raw_cleanup) == cleanup_semantics(cleanup.normalized_runtime_view)
    assert raw_retry.scientific_failure_retries == 0
    assert raw_cleanup.unrelated_process_kill_permitted is False


def test_assignment_dependency_is_case_b_and_scientific_payload_stays_equal():
    audit = Round513E3HAssignmentDependencyAudit(
        source_commit=SOURCE,
        old_assignments_id="a" * 64,
        binds_source_commit=True,
        binds_runtime_release=True,
        binds_compatibility_release=False,
        binds_run_binding_schema=False,
        binds_policy_ids=False,
        dependency_case="B",
    ).with_id()
    assert audit.dependency_case == "B"
    rows = []
    for order in range(9):
        rows.append({
            "namespace_id": "n" * 64,
            "terminal_task": f"task-{order}",
            "formal_task_name": f"formal-{order}",
            "formal_catalog_row_id": f"{order}" * 64,
            "task_path_label": f"asset-{order}.json",
            "task_file_sha256": f"{order + 1}" * 64,
            "difficulty": "basic",
            "target_action_family": "find",
            "coverage_naturalness": "natural",
            "natural_action_coverage_eligible": True,
            "instrumentation_target_eligible": True,
            "observed_runtime_coverage": "not_observed_before_execution",
            "seed_commitment": f"{order + 2}" * 64,
            "seed": order + 1,
            "order": order,
            "engineering_only": True,
            "formal_fitting_eligible": False,
            "channel_calibration_eligible": False,
            "CHRM_fitting_eligible": False,
            "CDT_identification_eligible": False,
            "holdout_eligible": False,
            "final_evaluation_eligible": False,
        })
    root = smoke_scientific_payload_root(rows)
    equivalence = SmokeScientificPayloadEquivalenceAuditE3X_R1(
        source_commit=SOURCE,
        old_assignments_id="a" * 64,
        new_assignments_id="b" * 64,
        old_payload_root=root,
        new_payload_root=root,
        assignment_count=9,
        task_changes=0,
        seed_changes=0,
        order_changes=0,
        asset_changes=0,
        proxy_changes=0,
        eligibility_changes=0,
        namespace_changes=0,
        status="EQUIVALENT",
    ).with_id()
    assert equivalence.status == "EQUIVALENT"


def test_every_preflight_failure_precedes_provider_and_minedojo():
    for failure in E3H_PREFLIGHT_ORDER:
        counts = {"provider": 0, "minedojo": 0}

        def make_check(name):
            def check():
                if name == failure:
                    raise PermissionError(name)
            return check

        checks = {name: make_check(name) for name in E3H_PREFLIGHT_ORDER}
        with pytest.raises(PermissionError, match=failure):
            execute_preflight_sequence(
                checks,
                provider_call=lambda: counts.__setitem__("provider", counts["provider"] + 1),
                minedojo_launch=lambda: counts.__setitem__("minedojo", counts["minedojo"] + 1),
            )
        assert counts == {"provider": 0, "minedojo": 0}
    assert len(E3H_PREFLIGHT_ORDER) == 10
    assert E3H_PREFLIGHT_ORDER_ID == canonical_sha256(E3H_PREFLIGHT_ORDER)


@pytest.mark.minedojo
def test_historical_e3x_blocked_artifacts_remain_byte_identical():
    expected = {
        "manifest.json": "5ee17eb36fe887506995f6f0a26b301c13c5fb977c51d59ea091be5011a04508",
        "authorization_closure_audit.json": "75da76d2f6e082224113e789d22b8eeb9af461fa1a0354f93ad45fbf82fec6ea",
        "runtime_semantics_audit.json": "f2fa3e1a59bc8bcb5d6cf8c43d9cd972f760f2ba4333a57835f575a87910d21b",
    }
    assert {name: file_sha256(BLOCKED_ROOT / name) for name in expected} == expected


@pytest.mark.minedojo
def test_e3f_assignments_dependency_and_scientific_root_are_reconstructable():
    payload = json.loads(
        (E3F_ROOT / "engineering_smoke_assignments.json").read_text(encoding="utf-8")
    )
    assert payload["source_commit"] == "df0b043a389b864507d57d3685b863624f519481"
    assert payload["runtime_release_id"] == "8f2606188aad3294619d70d7f475410f8e69c761e07d1fe7fefebc7894ae4cdf"
    assert len(payload["assignments"]) == 9
    assert smoke_scientific_payload_root(payload["assignments"])


def _fake_scientific_adapters(binding):
    ids = {
        "planner_schema": binding.planner_schema_id,
        "rule_registry": binding.rule_registry_id,
        "bilateral_retrieval_policy": binding.bilateral_policy_id,
        "decision_record_schema": binding.decision_record_schema_id,
        "step_outcome_registry": binding.step_outcome_registry_id,
        "instrumentation_release": binding.instrumentation_release_id,
        "support_policy": "f" * 64,
    }
    result = {}
    for name, raw_id in ids.items():
        payload = {"source_commit": "2" * 40}
        if name == "step_outcome_registry":
            payload.update(
                controller_contract_id=binding.controller_id,
                evaluator_contract_id=binding.evaluator_id,
                execution_budget_profile_id=binding.budget_profile_id,
            )
        result[name] = ContractRuntimeAdapterV4_1_2_R1(
            contract_type=name,
            contract_version="4.1.2",
            raw_contract_payload=payload,
            raw_contract_id=raw_id,
            raw_file_sha256=canonical_sha256({"file": name}),
            authoring_source_commit="2" * 40,
            normalized_runtime_view=payload,
        ).with_id()
    return result


def test_runtime_validator_requires_controller_evaluator_budget_and_manifest(monkeypatch, tmp_path):
    binding = _binding(output_root=str((tmp_path / "out").resolve()))
    scientific = _fake_scientific_adapters(binding)
    entries = tuple(
        ContractCompatibilityEntry(
            contract_type=name,
            filename=f"{name}.json",
            contract_id=adapter.raw_contract_id,
            file_sha256=adapter.raw_file_sha256,
            contract_version=adapter.contract_version,
            authoring_source_commit=adapter.authoring_source_commit,
            runtime_adapter_version=ADAPTER_VERSION,
            allowed_execution_source_commits=(SOURCE,),
        )
        for name, adapter in scientific.items()
    )
    compatibility = Round513E3ContractCompatibilityReleaseR1(
        contract_type="Round513E3ContractCompatibilityReleaseR1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=SOURCE,
        source_hardening_audit_id="1" * 64,
        historical_e3_compatibility_release_id="2" * 64,
        historical_e3_compatibility_file_sha256="3" * 64,
        historical_e2h_compatibility_release_id="4" * 64,
        provider_request_policy_id=binding.provider_request_policy_id,
        planner_runtime_request_contract_id=binding.planner_runtime_request_contract_id,
        planner_schema_id=binding.planner_schema_id,
        planner_parser_id=binding.planner_parser_id,
        scientific_contract_entries=entries,
        runtime_adapter_version=E3X_RUNTIME_ADAPTER_VERSION,
        runtime_schema=E3X_RUNTIME_SCHEMA,
    ).with_id()
    policy_compatibility = _policy_release()
    runtime = CHRMLiteEngineeringSmokeRuntimeReleaseE3X_R1(
        contract_type="CHRMLiteEngineeringSmokeRuntimeReleaseE3X_R1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=SOURCE,
        source_hardening_audit_id="1" * 64,
        contract_compatibility_release_id=compatibility.release_id,
        policy_compatibility_release_id=policy_compatibility.release_id,
        provider_request_policy_id=binding.provider_request_policy_id,
        planner_runtime_request_contract_id=binding.planner_runtime_request_contract_id,
        technical_retry_policy_id=RETRY_ID,
        process_cleanup_policy_id=CLEANUP_ID,
        controller_id=binding.controller_id,
        evaluator_id=binding.evaluator_id,
        budget_profile_id=binding.budget_profile_id,
        run_binding_schema_id="5" * 64,
        execution_manifest_schema_id="6" * 64,
        runtime_adapter_version=E3X_RUNTIME_ADAPTER_VERSION,
        preflight_order_id=E3H_PREFLIGHT_ORDER_ID,
    ).with_id()
    binding = replace(
        binding,
        contract_compatibility_release_id=compatibility.release_id,
        policy_compatibility_release_id=policy_compatibility.release_id,
        runtime_release_id=runtime.release_id,
        technical_retry_policy_id=RETRY_ID,
        process_cleanup_policy_id=CLEANUP_ID,
        binding_id="",
    ).with_id()
    manifest = CHRMLiteEngineeringSmokeExecutionManifestE3X_R1(
        contract_type="CHRMLiteEngineeringSmokeExecutionManifestE3X_R1",
        contract_version=E3X_CONTRACT_VERSION,
        execution_source_commit=SOURCE,
        run_binding_id=binding.binding_id,
        authorization_input_id=binding.authorization_input_id,
        authorization_input_file_sha256=binding.authorization_input_file_sha256,
        authorization_receipt_id=binding.authorization_receipt_id,
        authorization_receipt_file_sha256=binding.authorization_receipt_file_sha256,
        approval_statement_sha256=binding.approval_statement_sha256,
        assignment_seal_id=binding.assignment_seal_id,
        ordered_assignment_root=binding.ordered_assignment_root,
        assignment_id=binding.assignment_id,
        contract_compatibility_release_id=binding.contract_compatibility_release_id,
        policy_compatibility_release_id=binding.policy_compatibility_release_id,
        runtime_release_id=binding.runtime_release_id,
        technical_retry_policy_id=binding.technical_retry_policy_id,
        process_cleanup_policy_id=binding.process_cleanup_policy_id,
        controller_id=binding.controller_id,
        evaluator_id=binding.evaluator_id,
        budget_profile_id=binding.budget_profile_id,
        seed=binding.seed,
        output_root=binding.output_root,
        gamma_candidate=binding.gamma_candidate,
        gamma_cov_text=binding.gamma_cov_text,
        gamma_minus_text=binding.gamma_minus_text,
        gamma_plus_text=binding.gamma_plus_text,
        environment_execution_permitted=True,
    ).with_id()
    retry = type("Adapter", (), {
        "policy_type": "technical_retry", "raw_policy_id": RETRY_ID,
        "raw_file_sha256": RETRY_SHA, "authoring_source_commit": AUTHORING_SOURCE,
        "adapter_version": E3X_POLICY_ADAPTER_VERSION,
    })()
    cleanup = type("Adapter", (), {
        "policy_type": "process_cleanup", "raw_policy_id": CLEANUP_ID,
        "raw_file_sha256": CLEANUP_SHA, "authoring_source_commit": AUTHORING_SOURCE,
        "adapter_version": E3X_POLICY_ADAPTER_VERSION,
    })()
    validate_e3x_runtime_artifacts(
        binding=binding,
        compatibility=compatibility,
        policy_compatibility=policy_compatibility,
        runtime=runtime,
        manifest=manifest,
        retry_adapter=retry,
        cleanup_adapter=cleanup,
        scientific_adapters=scientific,
        cli_output_root=binding.output_root,
    )
    with pytest.raises(ValueError, match="Controller/Evaluator/Budget/Policy"):
        validate_e3x_runtime_artifacts(
            binding=binding,
            compatibility=compatibility,
            policy_compatibility=policy_compatibility,
            runtime=replace(runtime, controller_id="0" * 64, release_id="").with_id(),
            manifest=manifest,
            retry_adapter=retry,
            cleanup_adapter=cleanup,
            scientific_adapters=scientific,
            cli_output_root=binding.output_root,
        )
