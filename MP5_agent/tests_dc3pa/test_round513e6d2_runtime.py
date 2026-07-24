import json
from dataclasses import replace
from pathlib import Path

import pytest

from dc3pa.experiments.round513e5d1 import ScientificContractReferenceD1
from dc3pa.experiments.round513e6d2 import (
    D1_TASK_ORDER,
    D2PairedAssignment,
    D2PairedDiagnosticAssignments,
    D2PairedDiagnosticSeal,
    Round513E6D2DiagnosticAuthorizationInput,
    Round513E6D2DiagnosticAuthorizationReceiptR1,
    Round513E6D2DiagnosticExecutionManifestR1,
    Round513E6D2DiagnosticRunBindingR1,
    Round513E6D2RuntimeRelease,
    canonical_sha256,
    file_sha256,
    load_d2_contract,
    seed_from_commitment,
    validate_d2_execution_closure,
)


SOURCE = "1" * 40
SHA = "2" * 64


def _closure(tmp_path: Path):
    task_paths = []
    rows = []
    names = (("mine sapling", "sapling"), ("mine iron ore", "iron ore"), ("mine log", "log"))
    for order, (formal, runtime_task) in enumerate(names):
        task_path = tmp_path / f"task-{order}.json"
        task_path.write_text(json.dumps([{"task": runtime_task}]) + "\n", encoding="utf-8")
        task_paths.append(task_path)
        rows.append(D2PairedAssignment(
            order=order,
            formal_task=formal,
            runtime_task=runtime_task,
            terminal_task=runtime_task,
            task_asset=task_path.name,
            task_asset_sha256=file_sha256(task_path),
            seed_commitment=f"{order + 1:08x}" + "a" * 56,
            d1_origin_assignment_id=f"{order + 3:x}" * 64,
        ).with_id())
    assignments = D2PairedDiagnosticAssignments(
        source_commit=SOURCE,
        d1_assignments_id="6" * 64,
        rows=tuple(rows),
    ).with_id()
    ordered_root = canonical_sha256([row.assignment_id for row in rows])
    seal = D2PairedDiagnosticSeal(
        source_commit=SOURCE,
        assignments_id=assignments.assignments_id,
        ordered_assignment_root=ordered_root,
        d1_ordered_assignment_root="7" * 64,
    ).with_id()
    references = tuple(
        ScientificContractReferenceD1(kind, f"{kind}.json", digest, digest)
        for kind, digest in (
            ("planner_schema", "8" * 64),
            ("rule_registry", "9" * 64),
            ("bilateral_retrieval_policy", "a" * 64),
            ("support_policy", "b" * 64),
        )
    )
    runtime = Round513E6D2RuntimeRelease(
        source_commit=SOURCE,
        source_hardening_audit_id="c" * 64,
        d1_closeout_release_id="d" * 64,
        outcome_schema_id="e" * 64,
        find_contract_id="f" * 64,
        safety_semantics_audit_id="0" * 64,
        safety_policy_id="1" * 64,
        signature_registry_id="2" * 64,
        scene_compatibility_audit_id="3" * 64,
        planner_schema_id="8" * 64,
        planner_prompt_id="4" * 64,
        planner_parser_id="5" * 64,
        rule_registry_id="9" * 64,
        dependency_schema_id="6" * 64,
        budget_profile_id="7" * 64,
        technical_retry_policy_id="8" * 64,
        technical_retry_policy_file_sha256="9" * 64,
        process_cleanup_policy_id="a" * 64,
        process_cleanup_policy_file_sha256="b" * 64,
        paper_memory_release_id="c" * 64,
        scene_exemplar_release_id="d" * 64,
        mineclip_policy_id="e" * 64,
        controller_id="f" * 64,
        evaluator_id="0" * 64,
        scientific_contracts=references,
    ).with_id()
    authorization = Round513E6D2DiagnosticAuthorizationInput(
        source_commit=SOURCE,
        runtime_release_id=runtime.release_id,
        d1_closeout_release_id=runtime.d1_closeout_release_id,
        action_goal_outcome_schema_id=runtime.outcome_schema_id,
        find_observation_contract_id=runtime.find_contract_id,
        safety_termination_policy_id=runtime.safety_policy_id,
        signature_registry_id=runtime.signature_registry_id,
        scene_compatibility_audit_id=runtime.scene_compatibility_audit_id,
        assignments_id=assignments.assignments_id,
        assignment_seal_id=seal.seal_id,
        ordered_assignment_root=ordered_root,
        pending_binding_root="1" * 64,
        pending_execution_manifest_root="2" * 64,
        exclusion_audit_id="3" * 64,
        equivalence_audit_id="4" * 64,
        technical_retry_policy_id=runtime.technical_retry_policy_id,
        process_cleanup_policy_id=runtime.process_cleanup_policy_id,
        planner_schema_id=runtime.planner_schema_id,
        planner_prompt_id=runtime.planner_prompt_id,
        planner_parser_id=runtime.planner_parser_id,
        controller_id=runtime.controller_id,
        evaluator_id=runtime.evaluator_id,
        paper_memory_release_id=runtime.paper_memory_release_id,
        scene_exemplar_release_id=runtime.scene_exemplar_release_id,
        mineclip_policy_id=runtime.mineclip_policy_id,
    ).with_id()
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(json.dumps(authorization.to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    receipt = Round513E6D2DiagnosticAuthorizationReceiptR1(
        source_commit=SOURCE,
        authorization_input_id=authorization.authorization_input_id,
        authorization_input_file_sha256=file_sha256(authorization_path),
        runtime_release_id=runtime.release_id,
        assignment_seal_id=seal.seal_id,
        authorized_task_order=D1_TASK_ORDER,
        approved_by="ZYF",
        approval_statement_sha256="5" * 64,
    ).with_id()
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt.to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    selected = rows[0]
    output_root = tmp_path / "records"
    binding = Round513E6D2DiagnosticRunBindingR1(
        execution_source_commit=SOURCE,
        campaign_id="campaign",
        run_id="run",
        episode_id="episode",
        assignment_id=selected.assignment_id,
        assignment_order=selected.order,
        task=selected.runtime_task,
        terminal_task=selected.terminal_task,
        task_asset_sha256=selected.task_asset_sha256,
        seed=seed_from_commitment(selected.seed_commitment),
        seed_commitment=selected.seed_commitment,
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
    manifest = Round513E6D2DiagnosticExecutionManifestR1(
        execution_source_commit=SOURCE,
        binding_id=binding.binding_id,
        authorization_receipt_id=receipt.receipt_id,
        runtime_release_id=runtime.release_id,
        assignment_seal_id=seal.seal_id,
        assignment_id=selected.assignment_id,
        assignment_order=selected.order,
        task=selected.runtime_task,
        task_asset_sha256=selected.task_asset_sha256,
        seed_commitment=selected.seed_commitment,
        output_root=str(output_root),
    ).with_id()
    return task_paths[0], output_root, binding, authorization, receipt, assignments, seal, runtime, manifest, authorization_path, receipt_path


def _validate(values):
    return validate_d2_execution_closure(
        current_source=SOURCE, task_path=values[0], output_root=values[1],
        binding=values[2], authorization=values[3], receipt=values[4],
        assignments=values[5], seal=values[6], runtime=values[7], manifest=values[8],
        authorization_input_file_sha256=file_sha256(values[9]),
        authorization_receipt_file_sha256=file_sha256(values[10]),
    )


def test_d2_execution_closure_accepts_exact_paired_assignment(tmp_path: Path):
    selected = _validate(_closure(tmp_path))
    assert selected.formal_task == "mine sapling"
    assert selected.independent_sample is False


def test_d2_execution_closure_rejects_manifest_drift(tmp_path: Path):
    values = list(_closure(tmp_path))
    values[8] = replace(values[8], task="log", manifest_id="").with_id()
    with pytest.raises(ValueError, match="manifest mismatch"):
        _validate(values)


def test_d2_execution_closure_rejects_receipt_raw_sha_drift(tmp_path: Path):
    values = _closure(tmp_path)
    with pytest.raises(ValueError, match="receipt raw file SHA"):
        validate_d2_execution_closure(
            current_source=SOURCE, task_path=values[0], output_root=values[1],
            binding=values[2], authorization=values[3], receipt=values[4],
            assignments=values[5], seal=values[6], runtime=values[7], manifest=values[8],
            authorization_input_file_sha256=file_sha256(values[9]),
            authorization_receipt_file_sha256=SHA,
        )


def test_d2_execution_closure_rejects_authorization_lineage_drift(tmp_path: Path):
    values = list(_closure(tmp_path))
    values[3] = replace(values[3], controller_id="9" * 64, authorization_input_id="").with_id()
    values[9].write_text(json.dumps(values[3].to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    values[4] = replace(
        values[4], authorization_input_id=values[3].authorization_input_id,
        authorization_input_file_sha256=file_sha256(values[9]),
        receipt_id="",
    ).with_id()
    values[10].write_text(json.dumps(values[4].to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    values[2] = replace(
        values[2], authorization_input_id=values[3].authorization_input_id,
        authorization_receipt_id=values[4].receipt_id,
        authorization_receipt_file_sha256=file_sha256(values[10]), binding_id="",
    ).with_id()
    values[8] = replace(
        values[8], binding_id=values[2].binding_id,
        authorization_receipt_id=values[4].receipt_id, manifest_id="",
    ).with_id()
    with pytest.raises(ValueError, match="scientific lineage"):
        _validate(values)


def test_d2_raw_loader_rejects_tampering(tmp_path: Path):
    values = _closure(tmp_path)
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(values[7].to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    loaded = load_d2_contract(
        path, contract_kind="runtime", expected_file_sha256=file_sha256(path),
        expected_contract_id=values[7].release_id,
    )
    assert loaded == values[7]
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="raw file SHA"):
        load_d2_contract(
            path, contract_kind="runtime", expected_file_sha256="0" * 64,
            expected_contract_id=values[7].release_id,
        )


def test_stage6_exposes_d2_fail_closed_arguments():
    from scripts_dc3pa.stage6_run_minecraft import build_parser

    destinations = {item.dest for item in build_parser()._actions}
    assert {
        "round513e6_d2_contracts",
        "round513e6_d2_authorization_input",
        "round513e6_d2_authorization_receipt",
        "round513e6_d2_assignments",
        "round513e6_d2_assignment_seal",
        "round513e6_d2_binding_sha256",
        "round513e6_d2_runtime_sha256",
        "round513e6_d2_execution_manifest_sha256",
    }.issubset(destinations)
