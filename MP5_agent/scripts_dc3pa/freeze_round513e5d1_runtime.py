#!/usr/bin/env python3
"""Freeze the amended E5 D1 source closure without starting MineDojo."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round513e2h import file_sha256  # noqa: E402
from dc3pa.experiments.round513e5d1 import (  # noqa: E402
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
    DiagnosticRuntimeReleaseD1,
    ScientificContractReferenceD1,
    canonical_sha256,
    seed_from_commitment,
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout.strip()


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected an object in {path}")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _pending_binding(
    *, source: str, assignment: DiagnosticAssignmentD1, origin: dict[str, Any],
    runtime: DiagnosticRuntimeReleaseD1, seal: DiagnosticAssignmentSealD1,
    output_root: Path,
) -> dict[str, Any]:
    payload = {
        "contract_type": "Round513E5DiagnosticPendingRunBindingD1R1",
        "contract_version": CONTRACT_VERSION,
        "schema_version": 1,
        "execution_source_commit": source,
        "assignment_id": assignment.assignment_id,
        "assignment_order": assignment.order,
        "task": assignment.runtime_task,
        "terminal_task": assignment.terminal_task,
        "task_asset_sha256": assignment.asset_sha256,
        "seed": seed_from_commitment(assignment.seed_commitment),
        "seed_commitment": assignment.seed_commitment,
        "runtime_release_id": runtime.release_id,
        "assignment_seal_id": seal.seal_id,
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
        "candidate_b_id": CANDIDATE_B_ID,
        "gamma_text": list(GAMMA_TEXT),
        "e4_origin_binding_id": origin["binding_id"],
        "output_root": str((output_root / f"{assignment.order:02d}-{assignment.runtime_task.replace(' ', '_')}").resolve()),
        "diagnostic_only": True,
        "execution_authorized": False,
        "authorization_receipt_id": "PENDING_EXACT_ZYF_AUTHORIZATION",
    }
    payload["pending_binding_id"] = canonical_sha256(payload)
    return payload


def _pending_manifest(binding: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "contract_type": "Round513E5DiagnosticPendingExecutionManifestD1R1",
        "contract_version": CONTRACT_VERSION,
        "schema_version": 1,
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
        "diagnostic_only": True,
        "minedojo_execution_permitted": False,
        "scientific_success_retries": 0,
        "scientific_failure_retries": 0,
    }
    payload["pending_manifest_id"] = canonical_sha256(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-root-base", type=Path, required=True)
    parser.add_argument("--prior-d1-root", type=Path, required=True)
    parser.add_argument("--amendment-receipt", type=Path, required=True)
    parser.add_argument("--scientific-contract-root", type=Path, required=True)
    parser.add_argument("--compatibility-release", type=Path, required=True)
    parser.add_argument("--technical-retry-policy", type=Path, required=True)
    parser.add_argument("--process-cleanup-policy", type=Path, required=True)
    parser.add_argument("--e4-origin-binding", type=Path, action="append", required=True)
    args = parser.parse_args()

    source = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise ValueError("E5 D1 source freeze requires a clean worktree")
    if len(args.e4_origin_binding) != 3:
        raise ValueError("E5 D1 requires exactly three E4 origin bindings")
    args.output.mkdir(parents=True, mode=0o700)
    if any(args.output.iterdir()):
        raise ValueError("E5 D1 freeze output must be empty")

    prior_assignments = _load(args.prior_d1_root / "d1_diagnostic_assignments.json")
    prior_authorization = _load(args.prior_d1_root / "d1_diagnostic_authorization_input.json")
    prior_receipt = _load(args.prior_d1_root / "d1_diagnostic_authorization_receipt.json")
    amendment = _load(args.amendment_receipt)
    if amendment.get("approved_by") != "ZYF" or not amendment.get("source_hardening_permitted"):
        raise PermissionError("E5 D1 source-hardening amendment is not author-approved")
    if amendment.get("parent_source_commit") != prior_authorization.get("source_commit"):
        raise ValueError("E5 D1 amendment parent source mismatch")
    if amendment.get("prior_authorization_input_id") != prior_authorization.get("authorization_input_id"):
        raise ValueError("E5 D1 amendment authorization lineage mismatch")
    if prior_receipt.get("authorization_input_id") != prior_authorization.get("authorization_input_id"):
        raise ValueError("Prior E5 D1 authorization input/receipt mismatch")

    origins = {_load(path)["binding_id"]: _load(path) for path in args.e4_origin_binding}
    rows = []
    for prior in prior_assignments["rows"]:
        origin = origins.get(prior["e4_origin_binding_id"])
        if origin is None:
            raise ValueError("Missing exact E4 origin binding")
        if origin["seed_commitment"] != prior["seed_commitment"]:
            raise ValueError("D1 seed commitment differs from its E4 origin")
        if origin["seed"] != seed_from_commitment(prior["seed_commitment"]):
            raise ValueError("E4 origin seed does not match the D1 strategy")
        item = dict(prior)
        item.update(
            contract_type="Round513E5DiagnosticAssignmentD1R1",
            source_commit=source,
            assignment_id="",
        )
        rows.append(DiagnosticAssignmentD1(**item).with_id())
    assignments = DiagnosticAssignmentsD1(
        contract_type="Round513E5DiagnosticAssignmentsD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        source_commit=source,
        namespace="dc3pa-round513e5-diagnostic-only-d1-r1",
        seed_strategy_receipt_id=str(prior_assignments["seed_strategy_receipt_id"]),
        rows=tuple(rows),
    ).with_id()
    ordered_root = canonical_sha256([row.assignment_id for row in rows])
    seal = DiagnosticAssignmentSealD1(
        contract_type="Round513E5DiagnosticAssignmentSealD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        source_commit=source,
        assignments_id=assignments.assignments_id,
        seed_strategy_receipt_id=assignments.seed_strategy_receipt_id,
        ordered_assignment_root=ordered_root,
    ).with_id()

    compatibility = _load(args.compatibility_release)
    references = []
    for entry in compatibility["scientific_contract_entries"]:
        path = args.scientific_contract_root / entry["filename"]
        if file_sha256(path) != entry["file_sha256"]:
            raise ValueError("Scientific contract raw SHA mismatch")
        references.append(ScientificContractReferenceD1(
            contract_type=entry["contract_type"], filename=entry["filename"],
            contract_id=entry["contract_id"], file_sha256=entry["file_sha256"],
        ))
    reference = origins[rows[0].e4_origin_binding_id]
    rule_payload = _load(args.scientific_contract_root / next(
        item.filename for item in references if item.contract_type == "rule_registry"
    ))
    runtime = DiagnosticRuntimeReleaseD1(
        contract_type="Round513E5DiagnosticRuntimeReleaseD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        source_commit=source,
        prior_e5_runtime_release_id=str(prior_authorization["runtime_release_id"]),
        amendment_receipt_id=str(amendment["receipt_id"]),
        planner_schema_id=E3_PLANNER_SCHEMA_ID,
        planner_prompt_id=E3_PLANNER_PROMPT_ID,
        planner_parser_id=E3_PLANNER_PARSER_ID,
        rule_registry_id=str(reference["rule_registry_id"]),
        dependency_schema_id=str(rule_payload["dependency_schema_id"]),
        paper_memory_release_id=str(prior_authorization["paper_memory_release_id"]),
        scene_exemplar_release_id=str(prior_authorization["scene_exemplar_release_id"]),
        mineclip_policy_id=str(prior_authorization["mineclip_policy_id"]),
        controller_id=str(prior_authorization["controller_contract_id"]),
        evaluator_id=str(prior_authorization["evaluator_contract_id"]),
        budget_profile_id=str(reference["budget_profile_id"]),
        technical_retry_policy_id=str(prior_authorization["technical_retry_policy_id"]),
        technical_retry_policy_file_sha256=file_sha256(args.technical_retry_policy),
        process_cleanup_policy_id=str(prior_authorization["process_cleanup_policy_id"]),
        process_cleanup_policy_file_sha256=file_sha256(args.process_cleanup_policy),
        scientific_contracts=tuple(references),
    ).with_id()

    pending_bindings = [
        _pending_binding(
            source=source, assignment=row, origin=origins[row.e4_origin_binding_id],
            runtime=runtime, seal=seal, output_root=args.output_root_base,
        )
        for row in rows
    ]
    pending_manifests = [_pending_manifest(item) for item in pending_bindings]
    pending_binding_root = canonical_sha256([item["pending_binding_id"] for item in pending_bindings])
    pending_manifest_root = canonical_sha256([item["pending_manifest_id"] for item in pending_manifests])
    authorization = DiagnosticAuthorizationInputD1(
        contract_type="Round513E5DiagnosticAuthorizationInputD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        source_commit=source,
        runtime_release_id=runtime.release_id,
        assignments_id=assignments.assignments_id,
        assignment_seal_id=seal.seal_id,
        ordered_assignment_root=ordered_root,
        pending_binding_root=pending_binding_root,
        pending_execution_manifest_root=pending_manifest_root,
        amendment_receipt_id=str(amendment["receipt_id"]),
        prior_authorization_input_id=str(prior_authorization["authorization_input_id"]),
        prior_authorization_receipt_id=str(prior_receipt["receipt_id"]),
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

    artifacts: list[tuple[str, dict[str, Any], str]] = [
        ("d1_assignments_r1.json", assignments.to_dict(), assignments.assignments_id),
        ("d1_assignment_seal_r1.json", seal.to_dict(), seal.seal_id),
        ("d1_runtime_release_r1.json", runtime.to_dict(), runtime.release_id),
        ("d1_authorization_input_r1.json", authorization.to_dict(), authorization.authorization_input_id),
    ]
    for row, binding, manifest in zip(rows, pending_bindings, pending_manifests):
        stem = f"{row.order:02d}-{row.runtime_task.replace(' ', '_')}"
        artifacts.append((f"pending_bindings/{stem}.json", binding, binding["pending_binding_id"]))
        artifacts.append((f"pending_manifests/{stem}.json", manifest, manifest["pending_manifest_id"]))
    manifest_rows = []
    for filename, payload, item_id in artifacts:
        path = args.output / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, payload)
        manifest_rows.append({"filename": filename, "id": item_id, "sha256": file_sha256(path)})
    freeze_manifest = {
        "contract_type": "Round513E5D1SourceFreezeManifestR1",
        "source_commit": source,
        "runtime_release_id": runtime.release_id,
        "authorization_input_id": authorization.authorization_input_id,
        "assignment_seal_id": seal.seal_id,
        "ordered_task_root": ordered_root,
        "pending_binding_root": pending_binding_root,
        "pending_execution_manifest_root": pending_manifest_root,
        "task_order": list(DIAGNOSTIC_TASKS),
        "candidate_b_id": CANDIDATE_B_ID,
        "gamma_text": list(GAMMA_TEXT),
        "minedojo_execution_permitted": False,
        "artifacts": manifest_rows,
    }
    freeze_manifest["manifest_id"] = canonical_sha256(freeze_manifest)
    _write(args.output / "manifest.json", freeze_manifest)
    print(json.dumps({
        "source_commit": source,
        "runtime_release_id": runtime.release_id,
        "authorization_input_id": authorization.authorization_input_id,
        "assignment_seal_id": seal.seal_id,
        "manifest_id": freeze_manifest["manifest_id"],
        "minedojo_started": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
