import json
from dataclasses import replace
from pathlib import Path

import pytest

from dc3pa.experiments.round513e2h import file_sha256, load_versioned_contract
from dc3pa.experiments.round513e3f import build_provider_contracts
from dc3pa.experiments.round513e5d1 import (
    CANDIDATE_B_ID,
    CONTRACT_VERSION,
    DIAGNOSTIC_TASKS,
    E3_PLANNER_PARSER_ID,
    E3_PLANNER_PROMPT_ID,
    E3_PLANNER_SCHEMA_ID,
    GAMMA_TEXT,
    DiagnosticAssignmentD1,
    DiagnosticAssignmentSealD1,
    DiagnosticAssignmentsD1,
    DiagnosticAuthorizationInputD1,
    DiagnosticAuthorizationReceiptD1,
    DiagnosticExecutionManifestD1,
    DiagnosticRunBindingD1,
    DiagnosticRuntimeReleaseD1,
    ScientificContractReferenceD1,
    adapt_e3_canonical_planner,
    canonical_sha256,
    load_d1_contract,
    seed_from_commitment,
    validate_d1_execution_closure,
)


SOURCE = "1" * 40
SHA = "2" * 64


def _assignment(order: int, formal: str, runtime: str, path: Path) -> DiagnosticAssignmentD1:
    commitment = f"{order + 1:08x}" + "a" * 56
    return DiagnosticAssignmentD1(
        contract_type="Round513E5DiagnosticAssignmentD1R1",
        source_commit=SOURCE,
        order=order,
        formal_task=formal,
        runtime_task=runtime,
        terminal_task=runtime,
        difficulty="basic",
        asset=path.name,
        asset_sha256=file_sha256(path),
        seed_commitment=commitment,
        seed_strategy_receipt_id="3" * 64,
        e4_origin_assignment_id="4" * 64,
        e4_origin_binding_id=(f"{order + 5:x}" * 64)[:64],
        e4_origin_execution_source="6" * 40,
    ).with_id()


def _closure(tmp_path: Path):
    task_paths = []
    for name in ("sapling", "iron_ore", "log"):
        path = tmp_path / f"{name}.json"
        path.write_text('[{"task":"%s"}]\n' % name, encoding="utf-8")
        task_paths.append(path)
    rows = (
        _assignment(0, "mine sapling", "sapling", task_paths[0]),
        _assignment(1, "mine iron ore", "iron ore", task_paths[1]),
        _assignment(2, "mine log", "log", task_paths[2]),
    )
    assignments = DiagnosticAssignmentsD1(
        contract_type="Round513E5DiagnosticAssignmentsD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        source_commit=SOURCE,
        namespace="test",
        seed_strategy_receipt_id="3" * 64,
        rows=rows,
    ).with_id()
    ordered_root = canonical_sha256([row.assignment_id for row in rows])
    seal = DiagnosticAssignmentSealD1(
        contract_type="Round513E5DiagnosticAssignmentSealD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        source_commit=SOURCE,
        assignments_id=assignments.assignments_id,
        seed_strategy_receipt_id=assignments.seed_strategy_receipt_id,
        ordered_assignment_root=ordered_root,
    ).with_id()
    runtime = DiagnosticRuntimeReleaseD1(
        contract_type="Round513E5DiagnosticRuntimeReleaseD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        source_commit=SOURCE,
        prior_e5_runtime_release_id="7" * 64,
        amendment_receipt_id="8" * 64,
        planner_schema_id=E3_PLANNER_SCHEMA_ID,
        planner_prompt_id=E3_PLANNER_PROMPT_ID,
        planner_parser_id=E3_PLANNER_PARSER_ID,
        rule_registry_id="9" * 64,
        dependency_schema_id="a" * 64,
        paper_memory_release_id="b" * 64,
        scene_exemplar_release_id="c" * 64,
        mineclip_policy_id="d" * 64,
        controller_id="e" * 64,
        evaluator_id="f" * 64,
        budget_profile_id="1" * 64,
        technical_retry_policy_id="2" * 64,
        technical_retry_policy_file_sha256="3" * 64,
        process_cleanup_policy_id="4" * 64,
        process_cleanup_policy_file_sha256="5" * 64,
        scientific_contracts=(
            ScientificContractReferenceD1("planner_schema", "planner.json", E3_PLANNER_SCHEMA_ID, "6" * 64),
            ScientificContractReferenceD1("rule_registry", "rules.json", "9" * 64, "7" * 64),
            ScientificContractReferenceD1("bilateral_retrieval_policy", "retrieval.json", "8" * 64, "8" * 64),
            ScientificContractReferenceD1("support_policy", "support.json", "9" * 64, "9" * 64),
        ),
    ).with_id()
    authorization = DiagnosticAuthorizationInputD1(
        contract_type="Round513E5DiagnosticAuthorizationInputD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        source_commit=SOURCE,
        runtime_release_id=runtime.release_id,
        assignments_id=assignments.assignments_id,
        assignment_seal_id=seal.seal_id,
        ordered_assignment_root=ordered_root,
        pending_binding_root="a" * 64,
        pending_execution_manifest_root="b" * 64,
        amendment_receipt_id="8" * 64,
        prior_authorization_input_id="c" * 64,
        prior_authorization_receipt_id="d" * 64,
        planner_schema_id=runtime.planner_schema_id,
        planner_prompt_id=runtime.planner_prompt_id,
        planner_parser_id=runtime.planner_parser_id,
        technical_retry_policy_id=runtime.technical_retry_policy_id,
        process_cleanup_policy_id=runtime.process_cleanup_policy_id,
        paper_memory_release_id=runtime.paper_memory_release_id,
        scene_exemplar_release_id=runtime.scene_exemplar_release_id,
        mineclip_policy_id=runtime.mineclip_policy_id,
        controller_id=runtime.controller_id,
        evaluator_id=runtime.evaluator_id,
    ).with_id()
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(
        json.dumps(authorization.to_dict(), sort_keys=True) + "\n", encoding="utf-8"
    )
    receipt = DiagnosticAuthorizationReceiptD1(
        contract_type="Round513E5DiagnosticAuthorizationReceiptD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        source_commit=SOURCE,
        authorization_input_id=authorization.authorization_input_id,
        authorization_input_file_sha256=file_sha256(authorization_path),
        runtime_release_id=runtime.release_id,
        assignment_seal_id=seal.seal_id,
        authorized_task_order=DIAGNOSTIC_TASKS,
        approved_by="ZYF",
        approval_statement_sha256="e" * 64,
    ).with_id()
    output_root = tmp_path / "output"
    selected = rows[0]
    binding = DiagnosticRunBindingD1(
        contract_type="Round513E5DiagnosticRunBindingD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        execution_source_commit=SOURCE,
        campaign_id="campaign",
        run_id="run",
        episode_id="episode",
        assignment_id=selected.assignment_id,
        assignment_order=selected.order,
        task=selected.runtime_task,
        terminal_task=selected.terminal_task,
        task_asset_sha256=selected.asset_sha256,
        seed=seed_from_commitment(selected.seed_commitment),
        seed_commitment=selected.seed_commitment,
        authorization_input_id=authorization.authorization_input_id,
        authorization_receipt_id=receipt.receipt_id,
        authorization_receipt_file_sha256="f" * 64,
        runtime_release_id=runtime.release_id,
        assignment_seal_id=seal.seal_id,
        planner_schema_id=runtime.planner_schema_id,
        planner_prompt_id=runtime.planner_prompt_id,
        planner_parser_id=runtime.planner_parser_id,
        rule_registry_id=runtime.rule_registry_id,
        dependency_schema_id=runtime.dependency_schema_id,
        paper_memory_release_id=runtime.paper_memory_release_id,
        scene_exemplar_release_id=runtime.scene_exemplar_release_id,
        mineclip_policy_id=runtime.mineclip_policy_id,
        controller_id=runtime.controller_id,
        evaluator_id=runtime.evaluator_id,
        budget_profile_id=runtime.budget_profile_id,
        technical_retry_policy_id=runtime.technical_retry_policy_id,
        process_cleanup_policy_id=runtime.process_cleanup_policy_id,
        output_root=str(output_root),
    ).with_id()
    manifest = DiagnosticExecutionManifestD1(
        contract_type="Round513E5DiagnosticExecutionManifestD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        execution_source_commit=SOURCE,
        binding_id=binding.binding_id,
        authorization_receipt_id=receipt.receipt_id,
        runtime_release_id=runtime.release_id,
        assignment_seal_id=seal.seal_id,
        assignment_id=selected.assignment_id,
        assignment_order=selected.order,
        task=selected.runtime_task,
        task_asset_sha256=selected.asset_sha256,
        seed_commitment=selected.seed_commitment,
        output_root=str(output_root),
    ).with_id()
    return task_paths[0], output_root, binding, authorization, receipt, assignments, seal, runtime, manifest, authorization_path


def test_e3_canonical_planner_adapter_preserves_exact_ids(tmp_path: Path):
    schema, _, _, _ = build_provider_contracts("df0b043a389b864507d57d3685b863624f519481")
    path = tmp_path / "planner.json"
    path.write_text(json.dumps(schema.to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    adapter = load_versioned_contract(
        path, contract_type="planner_schema", expected_contract_id=E3_PLANNER_SCHEMA_ID,
        expected_file_sha256=file_sha256(path),
    )
    adapted = adapt_e3_canonical_planner(adapter)
    assert (adapted.schema_id, adapted.prompt_id, adapted.parser_id) == (
        E3_PLANNER_SCHEMA_ID, E3_PLANNER_PROMPT_ID, E3_PLANNER_PARSER_ID
    )


def test_d1_execution_closure_accepts_only_exact_three_task_binding(tmp_path: Path):
    values = _closure(tmp_path)
    selected = validate_d1_execution_closure(
        current_source=SOURCE, task_path=values[0], output_root=values[1],
        binding=values[2], authorization=values[3], receipt=values[4],
        assignments=values[5], seal=values[6], runtime=values[7], manifest=values[8],
        authorization_input_file_sha256=file_sha256(values[9]),
    )
    assert selected.formal_task == "mine sapling"
    assert selected.seed_value_published is False
    assert values[7].candidate_b_id == CANDIDATE_B_ID
    assert values[7].gamma_text == GAMMA_TEXT


def test_d1_execution_closure_fails_closed_on_authorization_sha(tmp_path: Path):
    values = _closure(tmp_path)
    with pytest.raises(ValueError, match="authorization raw file SHA"):
        validate_d1_execution_closure(
            current_source=SOURCE, task_path=values[0], output_root=values[1],
            binding=values[2], authorization=values[3], receipt=values[4],
            assignments=values[5], seal=values[6], runtime=values[7], manifest=values[8],
            authorization_input_file_sha256=SHA,
        )


def test_d1_raw_loader_rejects_tampering(tmp_path: Path):
    values = _closure(tmp_path)
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(values[7].to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    loaded = load_d1_contract(
        path, expected_file_sha256=file_sha256(path), expected_contract_id=values[7].release_id
    )
    assert loaded == values[7]
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="raw file SHA"):
        load_d1_contract(
            path, expected_file_sha256="0" * 64, expected_contract_id=values[7].release_id
        )


def test_d1_task_order_and_scientific_phase_are_immutable(tmp_path: Path):
    values = _closure(tmp_path)
    with pytest.raises(ValueError, match="task order"):
        replace(values[5], rows=tuple(reversed(values[5].rows)), assignments_id="")
    with pytest.raises(ValueError, match="protected scientific phase"):
        replace(values[5].rows[0], chrm_fitting_eligible=True, assignment_id="")


def test_stage6_exposes_explicit_d1_fail_closed_arguments():
    from scripts_dc3pa.stage6_run_minecraft import build_parser

    destinations = {item.dest for item in build_parser()._actions}
    assert {
        "round513e5_d1_authorization_input",
        "round513e5_d1_authorization_receipt",
        "round513e5_d1_assignments",
        "round513e5_d1_assignment_seal",
        "round513e5_d1_binding_sha256",
        "round513e5_d1_runtime_sha256",
        "round513e5_d1_execution_manifest_sha256",
    }.issubset(destinations)
