import json
from dataclasses import replace
from pathlib import Path

import pytest

from dc3pa.experiments.round513e5d1 import ScientificContractReferenceD1
from dc3pa.experiments.round513e7d3 import (
    D3_TASK_ORDER,
    D3TreeDiagnosticAssignment,
    D3TreeDiagnosticAssignments,
    D3TreeDiagnosticAuthorizationInput,
    D3TreeDiagnosticAuthorizationReceiptR1,
    D3TreeDiagnosticExecutionManifestR1,
    D3TreeDiagnosticRunBindingR1,
    D3TreeDiagnosticRuntimeRelease,
    D3TreeDiagnosticSeal,
    canonical_sha256,
    file_sha256,
    load_d3_contract,
    seed_from_commitment,
    validate_d3_execution_closure,
)


SOURCE = "a" * 40


def _runtime() -> D3TreeDiagnosticRuntimeRelease:
    references = tuple(
        ScientificContractReferenceD1(kind, f"{kind}.json", digest, digest)
        for kind, digest in (
            ("planner_schema", "1" * 64),
            ("rule_registry", "2" * 64),
            ("bilateral_retrieval_policy", "3" * 64),
            ("support_policy", "4" * 64),
        )
    )
    return D3TreeDiagnosticRuntimeRelease(
        source_commit=SOURCE,
        parent_e7_manifest_id="5" * 64,
        semantic_decision_receipt_id="6" * 64,
        d3_blueprint_id="7" * 64,
        outcome_schema_id="8" * 64,
        find_contract_id="9" * 64,
        safety_semantics_audit_id="b" * 64,
        safety_policy_id="c" * 64,
        signature_registry_id="d" * 64,
        scene_compatibility_audit_id="e" * 64,
        planner_schema_id="1" * 64,
        planner_prompt_id="f" * 64,
        planner_parser_id="0" * 64,
        rule_registry_id="2" * 64,
        dependency_schema_id="a" * 64,
        budget_profile_id="b" * 64,
        technical_retry_policy_id="c" * 64,
        technical_retry_policy_file_sha256="d" * 64,
        process_cleanup_policy_id="e" * 64,
        process_cleanup_policy_file_sha256="f" * 64,
        paper_memory_release_id="1" * 64,
        scene_exemplar_release_id="2" * 64,
        mineclip_policy_id="3" * 64,
        controller_id="4" * 64,
        evaluator_id="5" * 64,
        scientific_contracts=references,
    ).with_id()


def _assignment(tmp_path: Path, order: int, task: str, path_id: str) -> tuple[Path, D3TreeDiagnosticAssignment]:
    task_path = tmp_path / f"{task}.json"
    task_path.write_text(json.dumps([{"task": task}]) + "\n", encoding="utf-8")
    row = D3TreeDiagnosticAssignment(
        order=order,
        formal_task=f"mine {task}",
        runtime_task=task,
        terminal_task=task,
        task_asset=task_path.name,
        task_asset_sha256=file_sha256(task_path),
        seed_commitment=f"{order + 1:08x}" + "a" * 56,
        d2_origin_assignment_id=f"{order + 2:x}" * 64,
        d2_origin_record_hash=f"{order + 4:x}" * 64,
        diagnostic_path_id=path_id,
    ).with_id()
    return task_path, row


def _closure(tmp_path: Path):
    sapling_task, sapling = _assignment(tmp_path, 0, "sapling", "d3_tree_sapling_boundary")
    _, log = _assignment(tmp_path, 1, "log", "d3_tree_log_positive_control")
    assignments = D3TreeDiagnosticAssignments(
        source_commit=SOURCE,
        semantic_decision_receipt_id="6" * 64,
        d3_blueprint_id="7" * 64,
        d2_execution_source_commit="9" * 40,
        rows=(sapling, log),
    ).with_id()
    ordered_root = canonical_sha256([row.assignment_id for row in assignments.rows])
    seal = D3TreeDiagnosticSeal(
        source_commit=SOURCE,
        assignments_id=assignments.assignments_id,
        ordered_assignment_root=ordered_root,
    ).with_id()
    runtime = _runtime()
    authorization = D3TreeDiagnosticAuthorizationInput(
        source_commit=SOURCE,
        runtime_release_id=runtime.release_id,
        semantic_decision_receipt_id="6" * 64,
        d3_blueprint_id="7" * 64,
        assignments_id=assignments.assignments_id,
        assignment_seal_id=seal.seal_id,
        ordered_assignment_root=ordered_root,
        pending_binding_root="8" * 64,
        pending_execution_manifest_root="9" * 64,
        planner_schema_id=runtime.planner_schema_id,
        planner_prompt_id=runtime.planner_prompt_id,
        planner_parser_id=runtime.planner_parser_id,
        controller_id=runtime.controller_id,
        evaluator_id=runtime.evaluator_id,
        paper_memory_release_id=runtime.paper_memory_release_id,
        scene_exemplar_release_id=runtime.scene_exemplar_release_id,
        mineclip_policy_id=runtime.mineclip_policy_id,
        technical_retry_policy_id=runtime.technical_retry_policy_id,
        process_cleanup_policy_id=runtime.process_cleanup_policy_id,
    ).with_id()
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(json.dumps(authorization.to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    receipt = D3TreeDiagnosticAuthorizationReceiptR1(
        source_commit=SOURCE,
        authorization_input_id=authorization.authorization_input_id,
        authorization_input_file_sha256=file_sha256(authorization_path),
        runtime_release_id=runtime.release_id,
        assignment_seal_id=seal.seal_id,
        authorized_task_order=D3_TASK_ORDER,
        approved_by="ZYF",
        approval_statement_sha256="0" * 64,
    ).with_id()
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt.to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    output_root = tmp_path / "records"
    binding = D3TreeDiagnosticRunBindingR1(
        execution_source_commit=SOURCE,
        campaign_id="campaign",
        run_id="run",
        episode_id="episode",
        assignment_id=sapling.assignment_id,
        assignment_order=sapling.order,
        task=sapling.runtime_task,
        terminal_task=sapling.terminal_task,
        task_asset_sha256=sapling.task_asset_sha256,
        seed=seed_from_commitment(sapling.seed_commitment),
        seed_commitment=sapling.seed_commitment,
        authorization_input_id=authorization.authorization_input_id,
        authorization_receipt_id=receipt.receipt_id,
        authorization_receipt_file_sha256=file_sha256(receipt_path),
        runtime_release_id=runtime.release_id,
        assignment_seal_id=seal.seal_id,
        outcome_schema_id=runtime.outcome_schema_id,
        find_contract_id=runtime.find_contract_id,
        safety_policy_id=runtime.safety_policy_id,
        signature_registry_id=runtime.signature_registry_id,
        scene_compatibility_audit_id=runtime.scene_compatibility_audit_id,
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
    manifest = D3TreeDiagnosticExecutionManifestR1(
        execution_source_commit=SOURCE,
        binding_id=binding.binding_id,
        authorization_receipt_id=receipt.receipt_id,
        runtime_release_id=runtime.release_id,
        assignment_seal_id=seal.seal_id,
        assignment_id=sapling.assignment_id,
        assignment_order=sapling.order,
        task=sapling.runtime_task,
        task_asset_sha256=sapling.task_asset_sha256,
        seed_commitment=sapling.seed_commitment,
        output_root=str(output_root),
    ).with_id()
    return sapling_task, output_root, binding, authorization, receipt, assignments, seal, runtime, manifest, authorization_path, receipt_path


def test_d3_tree_only_closure_accepts_sapling_assignment(tmp_path: Path):
    values = _closure(tmp_path)
    selected = validate_d3_execution_closure(
        current_source=SOURCE,
        task_path=values[0],
        output_root=values[1],
        binding=values[2],
        authorization=values[3],
        receipt=values[4],
        assignments=values[5],
        seal=values[6],
        runtime=values[7],
        manifest=values[8],
        authorization_input_file_sha256=file_sha256(values[9]),
        authorization_receipt_file_sha256=file_sha256(values[10]),
    )
    assert selected.runtime_task == "sapling"
    assert selected.independent_sample is False


def test_d3_tree_only_rejects_iron_ore_assignment(tmp_path: Path):
    task_path = tmp_path / "iron.json"
    task_path.write_text(json.dumps([{"task": "iron ore"}]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-tree tasks"):
        D3TreeDiagnosticAssignment(
            order=1,
            formal_task="mine iron ore",
            runtime_task="iron ore",
            terminal_task="iron ore",
            task_asset=task_path.name,
            task_asset_sha256=file_sha256(task_path),
            seed_commitment="1" * 64,
            d2_origin_assignment_id="2" * 64,
            d2_origin_record_hash="3" * 64,
            diagnostic_path_id="d3_tree_iron",
        )


def test_d3_tree_only_rejects_order_drift(tmp_path: Path):
    _, sapling = _assignment(tmp_path, 0, "sapling", "d3_tree_sapling_boundary")
    _, log = _assignment(tmp_path, 1, "log", "d3_tree_log_positive_control")
    with pytest.raises(ValueError, match="sapling then log"):
        D3TreeDiagnosticAssignments(
            source_commit=SOURCE,
            semantic_decision_receipt_id="6" * 64,
            d3_blueprint_id="7" * 64,
            d2_execution_source_commit="9" * 40,
            rows=(log, sapling),
        )


def test_d3_loader_round_trips_runtime(tmp_path: Path):
    runtime = _runtime()
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(runtime.to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    loaded = load_d3_contract(
        path,
        contract_kind="runtime",
        expected_file_sha256=file_sha256(path),
        expected_contract_id=runtime.release_id,
    )
    assert loaded == runtime


def test_d3_loader_round_trips_authorization_without_gamma_text(tmp_path: Path):
    values = _closure(tmp_path)
    loaded = load_d3_contract(
        values[9],
        contract_kind="authorization_input",
        expected_file_sha256=file_sha256(values[9]),
        expected_contract_id=values[3].authorization_input_id,
    )
    assert loaded == values[3]
    assert isinstance(loaded.declarations, tuple)


def test_d3_closure_rejects_manifest_task_drift(tmp_path: Path):
    values = list(_closure(tmp_path))
    values[8] = replace(values[8], task="log", manifest_id="").with_id()
    with pytest.raises(ValueError, match="manifest mismatch"):
        validate_d3_execution_closure(
            current_source=SOURCE,
            task_path=values[0],
            output_root=values[1],
            binding=values[2],
            authorization=values[3],
            receipt=values[4],
            assignments=values[5],
            seal=values[6],
            runtime=values[7],
            manifest=values[8],
            authorization_input_file_sha256=file_sha256(values[9]),
            authorization_receipt_file_sha256=file_sha256(values[10]),
        )


def test_stage6_exposes_d3_fail_closed_arguments():
    from scripts_dc3pa.stage6_run_minecraft import build_parser

    destinations = {item.dest for item in build_parser()._actions}
    assert {
        "round513e7_d3_contracts",
        "round513e7_d3_authorization_input",
        "round513e7_d3_authorization_receipt",
        "round513e7_d3_assignments",
        "round513e7_d3_assignment_seal",
        "round513e7_d3_binding_sha256",
        "round513e7_d3_runtime_sha256",
        "round513e7_d3_execution_manifest_sha256",
    }.issubset(destinations)
