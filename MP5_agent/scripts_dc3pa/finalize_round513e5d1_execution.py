#!/usr/bin/env python3
"""Finalize author-approved E5 D1 manifests without starting MineDojo."""

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

from dc3pa.experiments.round513e2h import file_sha256  # noqa: E402
from dc3pa.experiments.round513e5d1 import (  # noqa: E402
    CONTRACT_VERSION,
    DiagnosticAssignmentSealD1,
    DiagnosticAssignmentsD1,
    DiagnosticAuthorizationInputD1,
    DiagnosticAuthorizationReceiptD1,
    DiagnosticExecutionManifestD1,
    DiagnosticRunBindingD1,
    DiagnosticRuntimeReleaseD1,
    canonical_sha256,
    contract_from_mapping,
    seed_from_commitment,
    validate_d1_execution_closure,
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

    source = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise ValueError("E5 D1 finalization requires a clean worktree")
    args.output.mkdir(parents=True, mode=0o700)
    if any(args.output.iterdir()):
        raise ValueError("E5 D1 finalization output must be empty")
    freeze_manifest = _load(args.freeze_root / "manifest.json")
    if freeze_manifest.get("source_commit") != source:
        raise ValueError("E5 D1 finalization source does not match HEAD")
    by_name = {row["filename"]: row for row in freeze_manifest["artifacts"]}

    def frozen(name: str):
        row = by_name[name]
        path = args.freeze_root / name
        if file_sha256(path) != row["sha256"]:
            raise ValueError(f"Frozen E5 D1 artifact changed: {name}")
        contract = contract_from_mapping(_load(path))
        if row["id"] not in contract.to_dict().values():
            raise ValueError(f"Frozen E5 D1 artifact ID changed: {name}")
        return contract, path

    assignments, _ = frozen("d1_assignments_r1.json")
    seal, _ = frozen("d1_assignment_seal_r1.json")
    runtime, _ = frozen("d1_runtime_release_r1.json")
    authorization, authorization_path = frozen("d1_authorization_input_r1.json")
    if not isinstance(assignments, DiagnosticAssignmentsD1):
        raise TypeError("E5 D1 assignments type mismatch")
    if not isinstance(seal, DiagnosticAssignmentSealD1):
        raise TypeError("E5 D1 seal type mismatch")
    if not isinstance(runtime, DiagnosticRuntimeReleaseD1):
        raise TypeError("E5 D1 runtime type mismatch")
    if not isinstance(authorization, DiagnosticAuthorizationInputD1):
        raise TypeError("E5 D1 authorization input type mismatch")

    statement = args.approval_statement_file.read_text(encoding="utf-8").strip()
    if "approved_by=ZYF" not in statement and "approved_by = ZYF" not in statement:
        raise PermissionError("Exact E5 D1 authorization statement lacks approved_by=ZYF")
    required_tokens = (
        source, authorization.authorization_input_id, runtime.release_id,
        seal.seal_id, authorization.pending_binding_root,
        authorization.pending_execution_manifest_root,
    )
    if any(token not in statement for token in required_tokens):
        raise PermissionError("Exact E5 D1 authorization statement is missing a frozen ID")
    receipt = DiagnosticAuthorizationReceiptD1(
        contract_type="Round513E5DiagnosticAuthorizationReceiptD1R1",
        contract_version=CONTRACT_VERSION,
        schema_version=1,
        source_commit=source,
        authorization_input_id=authorization.authorization_input_id,
        authorization_input_file_sha256=file_sha256(authorization_path),
        runtime_release_id=runtime.release_id,
        assignment_seal_id=seal.seal_id,
        authorized_task_order=authorization.authorized_task_order,
        approved_by="ZYF",
        approval_statement_sha256=hashlib.sha256(statement.encode("utf-8")).hexdigest(),
    ).with_id()
    receipt_path = args.output / "d1_authorization_receipt_r1.json"
    _write(receipt_path, receipt.to_dict())
    receipt_file_sha = file_sha256(receipt_path)

    campaign_id = canonical_sha256({
        "source": source, "authorization_receipt_id": receipt.receipt_id,
        "assignment_seal_id": seal.seal_id,
    })
    rows = []
    for assignment in assignments.rows:
        stem = f"{assignment.order:02d}-{assignment.runtime_task.replace(' ', '_')}"
        pending_binding_path = args.freeze_root / "pending_bindings" / f"{stem}.json"
        pending_manifest_path = args.freeze_root / "pending_manifests" / f"{stem}.json"
        pending_binding = _load(pending_binding_path)
        pending_manifest = _load(pending_manifest_path)
        if canonical_sha256({k: v for k, v in pending_binding.items() if k != "pending_binding_id"}) != pending_binding["pending_binding_id"]:
            raise ValueError("E5 D1 pending binding canonical ID mismatch")
        if canonical_sha256({k: v for k, v in pending_manifest.items() if k != "pending_manifest_id"}) != pending_manifest["pending_manifest_id"]:
            raise ValueError("E5 D1 pending manifest canonical ID mismatch")
        run_id = canonical_sha256({"campaign_id": campaign_id, "assignment_id": assignment.assignment_id})
        episode_id = canonical_sha256({"run_id": run_id, "seed_commitment": assignment.seed_commitment})
        binding = DiagnosticRunBindingD1(
            contract_type="Round513E5DiagnosticRunBindingD1R1",
            contract_version=CONTRACT_VERSION,
            schema_version=1,
            execution_source_commit=source,
            campaign_id=campaign_id,
            run_id=run_id,
            episode_id=episode_id,
            assignment_id=assignment.assignment_id,
            assignment_order=assignment.order,
            task=assignment.runtime_task,
            terminal_task=assignment.terminal_task,
            task_asset_sha256=assignment.asset_sha256,
            seed=seed_from_commitment(assignment.seed_commitment),
            seed_commitment=assignment.seed_commitment,
            authorization_input_id=authorization.authorization_input_id,
            authorization_receipt_id=receipt.receipt_id,
            authorization_receipt_file_sha256=receipt_file_sha,
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
            output_root=pending_binding["output_root"],
        ).with_id()
        manifest = DiagnosticExecutionManifestD1(
            contract_type="Round513E5DiagnosticExecutionManifestD1R1",
            contract_version=CONTRACT_VERSION,
            schema_version=1,
            execution_source_commit=source,
            binding_id=binding.binding_id,
            authorization_receipt_id=receipt.receipt_id,
            runtime_release_id=runtime.release_id,
            assignment_seal_id=seal.seal_id,
            assignment_id=assignment.assignment_id,
            assignment_order=assignment.order,
            task=assignment.runtime_task,
            task_asset_sha256=assignment.asset_sha256,
            seed_commitment=assignment.seed_commitment,
            output_root=binding.output_root,
        ).with_id()
        task_path = args.task_root / assignment.asset
        validate_d1_execution_closure(
            current_source=source, task_path=task_path, output_root=Path(binding.output_root),
            binding=binding, authorization=authorization, receipt=receipt,
            assignments=assignments, seal=seal, runtime=runtime, manifest=manifest,
            authorization_input_file_sha256=file_sha256(authorization_path),
        )
        binding_path = args.output / "bindings" / f"{stem}.json"
        manifest_path = args.output / "execution_manifests" / f"{stem}.json"
        _write(binding_path, binding.to_dict())
        _write(manifest_path, manifest.to_dict())
        rows.append({
            "order": assignment.order, "task": assignment.formal_task,
            "binding": str(binding_path.relative_to(args.output)),
            "binding_id": binding.binding_id, "binding_sha256": file_sha256(binding_path),
            "execution_manifest": str(manifest_path.relative_to(args.output)),
            "execution_manifest_id": manifest.manifest_id,
            "execution_manifest_sha256": file_sha256(manifest_path),
        })
    result = {
        "contract_type": "Round513E5D1ExecutionClosureManifestR1",
        "source_commit": source,
        "authorization_input_id": authorization.authorization_input_id,
        "authorization_receipt_id": receipt.receipt_id,
        "authorization_receipt_sha256": receipt_file_sha,
        "runtime_release_id": runtime.release_id,
        "assignment_seal_id": seal.seal_id,
        "campaign_id": campaign_id,
        "task_order": list(authorization.authorized_task_order),
        "diagnostic_only": True,
        "minedojo_started": False,
        "rows": rows,
    }
    result["manifest_id"] = canonical_sha256(result)
    _write(args.output / "execution_closure_manifest.json", result)
    print(json.dumps({
        "authorization_receipt_id": receipt.receipt_id,
        "execution_closure_manifest_id": result["manifest_id"],
        "assignment_count": len(rows),
        "minedojo_started": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
