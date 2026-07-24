#!/usr/bin/env python3
"""Freeze Round 5.13E6-D2 closeout and pending paired authorization artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round513e6d2 import (  # noqa: E402
    ActionGoalOutcomeSchemaV2,
    ActionObjectSignatureRegistryV2,
    D1D2ScientificPayloadEquivalenceAudit,
    D2PairedAssignment,
    D2PairedDiagnosticAssignments,
    D2PairedDiagnosticExclusionAudit,
    D2PairedDiagnosticSeal,
    FindObservationEvidenceContractV2,
    Round513E6D2DiagnosticAuthorizationInput,
    Round513E6D2RuntimeRelease,
    Round513E6D2SourceHardeningAudit,
    SafetyTerminationPolicyV2,
    SafetyTerminationSemanticsAudit,
    build_label_free_scene_audit,
    canonical_sha256,
    file_sha256,
    load_d1_closeout,
)
from dc3pa.experiments.round513e5d1 import (  # noqa: E402
    ScientificContractReferenceD1,
    seed_from_commitment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT.parent)
    parser.add_argument("--d1-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--execution-output-root-base", type=Path, required=True)
    parser.add_argument("--tests-dc3pa-passed", type=int, required=True)
    parser.add_argument("--minedojo-marked-passed", type=int, required=True)
    parser.add_argument("--relevant-skips", type=int, default=0)
    parser.add_argument("--github-actions-url", required=True)
    parser.add_argument("--github-actions-conclusion", choices=("success",), required=True)
    parser.add_argument("--snapshot-guard-passed", action="store_true")
    parser.add_argument("--memory-write-probe-rejected", action="store_true")
    parser.add_argument("--historical-gates-passed", action="store_true")
    return parser.parse_args()


def write_exclusive(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite frozen artifact: {path}")
    path.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def pending_binding(
    *, assignment: D2PairedAssignment, runtime: Round513E6D2RuntimeRelease,
    seal: D2PairedDiagnosticSeal, output_root_base: Path,
) -> dict[str, Any]:
    payload = {
        "contract_kind": "Round513E6D2PendingRunBindingR1",
        "execution_source_commit": runtime.source_commit,
        "assignment_id": assignment.assignment_id,
        "assignment_order": assignment.order,
        "task": assignment.runtime_task,
        "terminal_task": assignment.terminal_task,
        "task_asset_sha256": assignment.task_asset_sha256,
        "seed": seed_from_commitment(assignment.seed_commitment),
        "seed_commitment": assignment.seed_commitment,
        "runtime_release_id": runtime.release_id,
        "assignment_seal_id": seal.seal_id,
        "outcome_schema_id": runtime.outcome_schema_id,
        "find_contract_id": runtime.find_contract_id,
        "safety_policy_id": runtime.safety_policy_id,
        "signature_registry_id": runtime.signature_registry_id,
        "scene_compatibility_audit_id": runtime.scene_compatibility_audit_id,
        "planner_schema_id": runtime.planner_schema_id,
        "planner_prompt_id": runtime.planner_prompt_id,
        "planner_parser_id": runtime.planner_parser_id,
        "rule_registry_id": runtime.rule_registry_id,
        "dependency_schema_id": runtime.dependency_schema_id,
        "paper_memory_release_id": runtime.paper_memory_release_id,
        "scene_exemplar_release_id": runtime.scene_exemplar_release_id,
        "mineclip_policy_id": runtime.mineclip_policy_id,
        "controller_id": runtime.controller_id,
        "evaluator_id": runtime.evaluator_id,
        "budget_profile_id": runtime.budget_profile_id,
        "technical_retry_policy_id": runtime.technical_retry_policy_id,
        "process_cleanup_policy_id": runtime.process_cleanup_policy_id,
        "output_root": str((output_root_base / f"{assignment.order:02d}-{assignment.runtime_task.replace(' ', '_')}").resolve()),
        "candidate_b_id": runtime.candidate_b_id,
        "gamma_text": list(runtime.gamma_text),
        "paired_replay_only": True,
        "independent_sample": False,
        "execution_authorized": False,
        "authorization_receipt_id": "PENDING_EXACT_ZYF_AUTHORIZATION",
    }
    payload["pending_binding_id"] = canonical_sha256(payload)
    return payload


def pending_manifest(binding: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "contract_kind": "Round513E6D2PendingExecutionManifestR1",
        "execution_source_commit": binding["execution_source_commit"],
        "pending_binding_id": binding["pending_binding_id"],
        "assignment_id": binding["assignment_id"],
        "assignment_order": binding["assignment_order"],
        "task": binding["task"],
        "task_asset_sha256": binding["task_asset_sha256"],
        "seed_commitment": binding["seed_commitment"],
        "runtime_release_id": binding["runtime_release_id"],
        "assignment_seal_id": binding["assignment_seal_id"],
        "output_root": binding["output_root"],
        "paired_replay_only": True,
        "independent_sample": False,
        "minedojo_execution_permitted": False,
        "scientific_success_retries": 0,
        "scientific_failure_retries": 0,
    }
    payload["pending_manifest_id"] = canonical_sha256(payload)
    return payload


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    if dirty:
        raise RuntimeError("D2 freeze requires a clean worktree")
    if not all((
        args.snapshot_guard_passed,
        args.memory_write_probe_rejected,
        args.historical_gates_passed,
    )):
        raise RuntimeError("D2 freeze requires explicit successful local integrity gates")

    raw, gap, technical, closeout, records, d1_assignments = load_d1_closeout(
        args.d1_root.resolve()
    )
    schema = ActionGoalOutcomeSchemaV2().with_id()
    find_contract = FindObservationEvidenceContractV2().with_id()
    signature_registry = ActionObjectSignatureRegistryV2().with_id()
    safety_audit = SafetyTerminationSemanticsAudit(
        controller_source_sha256=file_sha256(repo / "MP5_agent" / "agent" / "controller.py"),
        structured_actions_source_sha256=file_sha256(repo / "MP5_agent" / "agent" / "structured_actions.py"),
    ).with_id()
    safety_policy = SafetyTerminationPolicyV2(
        semantics_audit_id=safety_audit.audit_id
    ).with_id()
    scene_audit = build_label_free_scene_audit(
        records, closeout_id=closeout.release_id, registry=signature_registry
    )

    d2_rows = tuple(
        D2PairedAssignment(
            order=int(row["order"]),
            formal_task=str(row["formal_task"]),
            runtime_task=str(row["runtime_task"]),
            terminal_task=str(row["terminal_task"]),
            task_asset=str(row["asset"]),
            task_asset_sha256=str(row["asset_sha256"]),
            seed_commitment=str(row["seed_commitment"]),
            d1_origin_assignment_id=str(row["assignment_id"]),
        ).with_id()
        for row in d1_assignments["rows"]
    )
    assignments = D2PairedDiagnosticAssignments(
        source_commit=head,
        d1_assignments_id=str(d1_assignments["assignments_id"]),
        rows=d2_rows,
    ).with_id()
    d2_ordered_root = canonical_sha256([row.assignment_id for row in d2_rows])
    seal = D2PairedDiagnosticSeal(
        source_commit=head,
        assignments_id=assignments.assignments_id,
        ordered_assignment_root=d2_ordered_root,
        d1_ordered_assignment_root=canonical_sha256(
            [row["assignment_id"] for row in d1_assignments["rows"]]
        ),
    ).with_id()
    exclusion = D2PairedDiagnosticExclusionAudit(
        assignments_id=assignments.assignments_id
    ).with_id()
    equivalence = D1D2ScientificPayloadEquivalenceAudit(
        d1_assignments_id=str(d1_assignments["assignments_id"]),
        d2_assignments_id=assignments.assignments_id,
        same_tasks=True,
        same_task_assets=True,
        same_seed_commitments=True,
        same_order=True,
        only_instrumentation_changed=True,
    ).with_id()

    source_audit = Round513E6D2SourceHardeningAudit(
        source_commit=head,
        d1_closeout_release_id=closeout.release_id,
        outcome_schema_id=schema.schema_id,
        find_contract_id=find_contract.contract_id,
        safety_policy_id=safety_policy.policy_id,
        signature_registry_id=signature_registry.registry_id,
        tests_dc3pa_passed=args.tests_dc3pa_passed,
        minedojo_marked_passed=args.minedojo_marked_passed,
        relevant_skips=args.relevant_skips,
        snapshot_guard_passed=args.snapshot_guard_passed,
        memory_write_probe_rejected=args.memory_write_probe_rejected,
        historical_gates_passed=args.historical_gates_passed,
        github_actions_conclusion=args.github_actions_conclusion,
    ).with_id()

    d1_runtime = json.loads(
        (args.d1_root / "source-hardening" / "freeze" / "d1_runtime_release_r1.json").read_text(encoding="utf-8")
    )
    references = tuple(
        ScientificContractReferenceD1(**entry)
        for entry in d1_runtime["scientific_contracts"]
    )
    runtime = Round513E6D2RuntimeRelease(
        source_commit=head,
        source_hardening_audit_id=source_audit.audit_id,
        d1_closeout_release_id=closeout.release_id,
        outcome_schema_id=schema.schema_id,
        find_contract_id=find_contract.contract_id,
        safety_semantics_audit_id=safety_audit.audit_id,
        safety_policy_id=safety_policy.policy_id,
        signature_registry_id=signature_registry.registry_id,
        scene_compatibility_audit_id=scene_audit.audit_id,
        planner_schema_id=str(d1_runtime["planner_schema_id"]),
        planner_prompt_id=str(d1_runtime["planner_prompt_id"]),
        planner_parser_id=str(d1_runtime["planner_parser_id"]),
        rule_registry_id=str(d1_runtime["rule_registry_id"]),
        dependency_schema_id=str(d1_runtime["dependency_schema_id"]),
        budget_profile_id=str(d1_runtime["budget_profile_id"]),
        technical_retry_policy_id=str(d1_runtime["technical_retry_policy_id"]),
        technical_retry_policy_file_sha256=str(d1_runtime["technical_retry_policy_file_sha256"]),
        process_cleanup_policy_id=str(d1_runtime["process_cleanup_policy_id"]),
        process_cleanup_policy_file_sha256=str(d1_runtime["process_cleanup_policy_file_sha256"]),
        paper_memory_release_id=str(d1_runtime["paper_memory_release_id"]),
        scene_exemplar_release_id=str(d1_runtime["scene_exemplar_release_id"]),
        mineclip_policy_id=str(d1_runtime["mineclip_policy_id"]),
        controller_id=str(d1_runtime["controller_id"]),
        evaluator_id=str(d1_runtime["evaluator_id"]),
        scientific_contracts=references,
    ).with_id()
    pending_bindings = tuple(
        pending_binding(
            assignment=row, runtime=runtime, seal=seal,
            output_root_base=args.execution_output_root_base,
        )
        for row in d2_rows
    )
    pending_manifests = tuple(pending_manifest(item) for item in pending_bindings)
    pending_binding_root = canonical_sha256(
        [item["pending_binding_id"] for item in pending_bindings]
    )
    pending_manifest_root = canonical_sha256(
        [item["pending_manifest_id"] for item in pending_manifests]
    )
    authorization = Round513E6D2DiagnosticAuthorizationInput(
        source_commit=head,
        runtime_release_id=runtime.release_id,
        d1_closeout_release_id=closeout.release_id,
        action_goal_outcome_schema_id=schema.schema_id,
        find_observation_contract_id=find_contract.contract_id,
        safety_termination_policy_id=safety_policy.policy_id,
        signature_registry_id=signature_registry.registry_id,
        scene_compatibility_audit_id=scene_audit.audit_id,
        assignments_id=assignments.assignments_id,
        assignment_seal_id=seal.seal_id,
        ordered_assignment_root=d2_ordered_root,
        pending_binding_root=pending_binding_root,
        pending_execution_manifest_root=pending_manifest_root,
        exclusion_audit_id=exclusion.audit_id,
        equivalence_audit_id=equivalence.audit_id,
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

    artifacts = {
        "d1_raw_complete_audit.json": raw.to_dict(),
        "d1_label_gap_audit.json": gap.to_dict(),
        "d1_technical_attempt_audit.json": technical.to_dict(),
        "d1_closeout_release.json": closeout.to_dict(),
        "action_goal_outcome_schema_v2.json": schema.to_dict(),
        "find_observation_evidence_contract_v2.json": find_contract.to_dict(),
        "safety_termination_semantics_audit.json": safety_audit.to_dict(),
        "safety_termination_policy_v2.json": safety_policy.to_dict(),
        "action_object_signature_registry_v2.json": signature_registry.to_dict(),
        "d1_label_free_scene_compatibility_audit.json": scene_audit.to_dict(),
        "d2_paired_assignments.json": assignments.to_dict(),
        "d2_paired_assignment_seal.json": seal.to_dict(),
        "d2_paired_exclusion_audit.json": exclusion.to_dict(),
        "d1_d2_payload_equivalence_audit.json": equivalence.to_dict(),
        "round513e6d2_source_hardening_audit.json": source_audit.to_dict(),
        "round513e6d2_runtime_release.json": runtime.to_dict(),
        "round513e6d2_diagnostic_authorization_input.json": authorization.to_dict(),
    }
    for row, binding, manifest_item in zip(d2_rows, pending_bindings, pending_manifests):
        stem = f"{row.order:02d}-{row.runtime_task.replace(' ', '_')}"
        artifacts[f"pending_bindings/{stem}.json"] = binding
        artifacts[f"pending_manifests/{stem}.json"] = manifest_item
    output = args.output_root.resolve()
    for filename, payload in artifacts.items():
        write_exclusive(output / filename, payload)
    manifest_rows = []
    for filename in sorted(artifacts):
        path = output / filename
        manifest_rows.append({"filename": filename, "file_sha256": file_sha256(path)})
    manifest = {
        "contract_type": "Round513E6D2FreezeManifest",
        "source_commit": head,
        "github_actions_url": args.github_actions_url,
        "github_actions_conclusion": args.github_actions_conclusion,
        "d2_execution_permitted": False,
        "minedojo_launch_count": 0,
        "rows": manifest_rows,
    }
    manifest["manifest_id"] = canonical_sha256(manifest)
    write_exclusive(output / "manifest.json", manifest)
    print(json.dumps({
        "source_commit": head,
        "authorization_input_id": authorization.authorization_input_id,
        "authorization_input_file_sha256": file_sha256(output / "round513e6d2_diagnostic_authorization_input.json"),
        "assignment_seal_id": seal.seal_id,
        "safety_policy_id": safety_policy.policy_id,
        "manifest_id": manifest["manifest_id"],
        "minedojo_launch_count": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
