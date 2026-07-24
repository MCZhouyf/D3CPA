#!/usr/bin/env python3
"""Finalize an exactly authorized D2 closure without starting MineDojo."""

from __future__ import annotations

import argparse
import hashlib
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

from dc3pa.experiments.round513e6d2 import (  # noqa: E402
    D1_TASK_ORDER,
    D2PairedDiagnosticAssignments,
    D2PairedDiagnosticSeal,
    Round513E6D2DiagnosticAuthorizationInput,
    Round513E6D2DiagnosticAuthorizationReceiptR1,
    Round513E6D2DiagnosticExecutionManifestR1,
    Round513E6D2DiagnosticRunBindingR1,
    Round513E6D2RuntimeRelease,
    canonical_sha256,
    d2_contract_from_mapping,
    file_sha256,
    seed_from_commitment,
    validate_d2_execution_closure,
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout.strip()


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected an object in {path}")
    return payload


def write_exclusive(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--approval-statement-file", type=Path, required=True)
    args = parser.parse_args()

    source = git("rev-parse", "HEAD")
    if git("status", "--porcelain"):
        raise ValueError("D2 finalization requires a clean worktree")
    args.output.mkdir(parents=True, mode=0o700)
    if any(args.output.iterdir()):
        raise ValueError("D2 finalization output must be empty")
    freeze_manifest = load(args.freeze_root / "manifest.json")
    if freeze_manifest.get("source_commit") != source:
        raise ValueError("D2 finalization source does not match HEAD")
    manifest_rows = {row["filename"]: row for row in freeze_manifest["rows"]}

    def frozen(filename: str, kind: str):
        path = args.freeze_root / filename
        row = manifest_rows[filename]
        if file_sha256(path) != row["file_sha256"]:
            raise ValueError(f"Frozen D2 artifact changed: {filename}")
        return d2_contract_from_mapping(kind, load(path)), path

    assignments, _ = frozen("d2_paired_assignments.json", "assignments")
    seal, _ = frozen("d2_paired_assignment_seal.json", "assignment_seal")
    runtime, _ = frozen("round513e6d2_runtime_release.json", "runtime")
    authorization, authorization_path = frozen(
        "round513e6d2_diagnostic_authorization_input.json", "authorization_input"
    )
    if not isinstance(assignments, D2PairedDiagnosticAssignments):
        raise TypeError("D2 assignments type mismatch")
    if not isinstance(seal, D2PairedDiagnosticSeal):
        raise TypeError("D2 seal type mismatch")
    if not isinstance(runtime, Round513E6D2RuntimeRelease):
        raise TypeError("D2 runtime type mismatch")
    if not isinstance(authorization, Round513E6D2DiagnosticAuthorizationInput):
        raise TypeError("D2 authorization input type mismatch")

    statement = args.approval_statement_file.read_text(encoding="utf-8").strip()
    required_tokens = (
        "approved_by=ZYF", source, authorization.authorization_input_id,
        runtime.release_id, seal.seal_id, authorization.pending_binding_root,
        authorization.pending_execution_manifest_root,
    )
    if any(token not in statement for token in required_tokens):
        raise PermissionError("Exact D2 authorization statement is missing a frozen token")
    receipt = Round513E6D2DiagnosticAuthorizationReceiptR1(
        source_commit=source,
        authorization_input_id=authorization.authorization_input_id,
        authorization_input_file_sha256=file_sha256(authorization_path),
        runtime_release_id=runtime.release_id,
        assignment_seal_id=seal.seal_id,
        authorized_task_order=D1_TASK_ORDER,
        approved_by="ZYF",
        approval_statement_sha256=hashlib.sha256(statement.encode("utf-8")).hexdigest(),
    ).with_id()
    receipt_path = args.output / "d2_authorization_receipt_r1.json"
    write_exclusive(receipt_path, receipt.to_dict())
    receipt_file_sha = file_sha256(receipt_path)
    campaign_id = canonical_sha256({
        "source": source,
        "authorization_receipt_id": receipt.receipt_id,
        "assignment_seal_id": seal.seal_id,
        "paired_replay_only": True,
    })

    pending_binding_ids = []
    pending_manifest_ids = []
    rows = []
    for assignment in assignments.rows:
        stem = f"{assignment.order:02d}-{assignment.runtime_task.replace(' ', '_')}"
        pending_binding = load(args.freeze_root / "pending_bindings" / f"{stem}.json")
        pending_manifest = load(args.freeze_root / "pending_manifests" / f"{stem}.json")
        if canonical_sha256({k: v for k, v in pending_binding.items() if k != "pending_binding_id"}) != pending_binding["pending_binding_id"]:
            raise ValueError("D2 pending binding ID mismatch")
        if canonical_sha256({k: v for k, v in pending_manifest.items() if k != "pending_manifest_id"}) != pending_manifest["pending_manifest_id"]:
            raise ValueError("D2 pending manifest ID mismatch")
        pending_binding_ids.append(pending_binding["pending_binding_id"])
        pending_manifest_ids.append(pending_manifest["pending_manifest_id"])
        run_id = canonical_sha256({"campaign_id": campaign_id, "assignment_id": assignment.assignment_id})
        episode_id = canonical_sha256({"run_id": run_id, "seed_commitment": assignment.seed_commitment})
        binding = Round513E6D2DiagnosticRunBindingR1(
            execution_source_commit=source,
            campaign_id=campaign_id,
            run_id=run_id,
            episode_id=episode_id,
            assignment_id=assignment.assignment_id,
            assignment_order=assignment.order,
            task=assignment.runtime_task,
            terminal_task=assignment.terminal_task,
            task_asset_sha256=assignment.task_asset_sha256,
            seed=seed_from_commitment(assignment.seed_commitment),
            seed_commitment=assignment.seed_commitment,
            authorization_input_id=authorization.authorization_input_id,
            authorization_receipt_id=receipt.receipt_id,
            authorization_receipt_file_sha256=receipt_file_sha,
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
            output_root=pending_binding["output_root"],
        ).with_id()
        manifest = Round513E6D2DiagnosticExecutionManifestR1(
            execution_source_commit=source,
            binding_id=binding.binding_id,
            authorization_receipt_id=receipt.receipt_id,
            runtime_release_id=runtime.release_id,
            assignment_seal_id=seal.seal_id,
            assignment_id=assignment.assignment_id,
            assignment_order=assignment.order,
            task=assignment.runtime_task,
            task_asset_sha256=assignment.task_asset_sha256,
            seed_commitment=assignment.seed_commitment,
            output_root=binding.output_root,
        ).with_id()
        task_path = args.task_root / assignment.task_asset
        validate_d2_execution_closure(
            current_source=source, task_path=task_path, output_root=Path(binding.output_root),
            binding=binding, authorization=authorization, receipt=receipt,
            assignments=assignments, seal=seal, runtime=runtime, manifest=manifest,
            authorization_input_file_sha256=file_sha256(authorization_path),
            authorization_receipt_file_sha256=receipt_file_sha,
        )
        binding_path = args.output / "bindings" / f"{stem}.json"
        manifest_path = args.output / "execution_manifests" / f"{stem}.json"
        write_exclusive(binding_path, binding.to_dict())
        write_exclusive(manifest_path, manifest.to_dict())
        rows.append({
            "order": assignment.order,
            "task": assignment.formal_task,
            "binding": str(binding_path.relative_to(args.output)),
            "binding_id": binding.binding_id,
            "binding_sha256": file_sha256(binding_path),
            "execution_manifest": str(manifest_path.relative_to(args.output)),
            "execution_manifest_id": manifest.manifest_id,
            "execution_manifest_sha256": file_sha256(manifest_path),
        })

    if canonical_sha256(pending_binding_ids) != authorization.pending_binding_root:
        raise ValueError("D2 pending binding root changed")
    if canonical_sha256(pending_manifest_ids) != authorization.pending_execution_manifest_root:
        raise ValueError("D2 pending execution manifest root changed")
    closure = {
        "contract_kind": "Round513E6D2ExecutionClosureR1",
        "source_commit": source,
        "authorization_input_id": authorization.authorization_input_id,
        "authorization_receipt_id": receipt.receipt_id,
        "authorization_receipt_sha256": receipt_file_sha,
        "runtime_release_id": runtime.release_id,
        "assignment_seal_id": seal.seal_id,
        "campaign_id": campaign_id,
        "task_order": list(D1_TASK_ORDER),
        "paired_replay_only": True,
        "independent_sample": False,
        "minedojo_started": False,
        "rows": rows,
    }
    closure["manifest_id"] = canonical_sha256(closure)
    write_exclusive(args.output / "execution_closure_manifest.json", closure)
    print(json.dumps({
        "authorization_receipt_id": receipt.receipt_id,
        "execution_closure_manifest_id": closure["manifest_id"],
        "assignment_count": len(rows),
        "minedojo_started": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
