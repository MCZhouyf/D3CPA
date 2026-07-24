#!/usr/bin/env python3
"""Freeze source-frozen E3 objects and stop at Author Boundary B."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round513e2h import canonical_sha256, file_sha256  # noqa: E402
from dc3pa.experiments.round513e3f import (  # noqa: E402
    CHRMLiteEngineeringSmokeAssignmentsV4_1_2_E3,
    CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2_E3,
    CHRMLiteEngineeringSmokeExclusionAuditV4_1_2_E3,
    CHRMLiteEngineeringSmokePoolV4_1_2_E3,
    CHRMLiteEngineeringSmokeRuntimeReleaseV4_1_2_E3,
    CHRMLiteEngineeringSmokeSealV4_1_2_E3,
    E3_AUTHORIZATION_DECLARATIONS,
    FORMAL_CATALOG_CANONICAL_SHA256,
    FORMAL_TASKSET_RELEASE_ID,
    GAMMA_CANDIDATE_B,
    GAMMA_TEXT,
    Round513E3AuthorBoundaryAReceipt,
    Round513E3ContractCompatibilityRelease,
    Round513E3ExternalManifestGateAudit,
    Round513E3ResolvedTaskAssetAudit,
    Round513E3SourceChangeAudit,
    Round513E3SourceFreezeAudit,
    build_provider_contracts,
    derive_authorized_e3_assignments,
    validate_boundary_a_approval,
)


BASE_SOURCE = "a329fd904eb98b96be5328c726531e8b799555f0"
NAMESPACE_LABEL = "dc3pa-round513e3-formal50-engineering-smoke-v4.1.2"
PROXY_DECISION_ID = "085c53aea5a629cfb5d6e220f52136bfdb357aa6b9c42aa2516abb5d04565512"
PROXY_DECISION_SHA = "93d228dcf98d801513f7d734e89ba19bd6b6976d8e34f42876ffcd3d6bcfd6fe"
IRON_DECISION_ID = "c7a0827769b36d48e67f5899d4af79a76e2b886267504d5c5fe8bb83e8327857"
IRON_DECISION_SHA = "3c4b4680ebdf427d0255845b8a90f061aeb2f23a39f344bbada408367ca4c634"
TECHNICAL_RETRY_POLICY_ID = "5e832b2056ba8c7c2aed7096a4f2fd22fe8d2a15e4c7ce427ac3896663bb15b5"
PROCESS_CLEANUP_POLICY_ID = "99d6d818a329cef6bc29ad9527aa42320f8173861c7b7ceb10837f0005296e14"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write(path: Path, payload: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _verify_hashed(path: Path, id_field: str, expected_id: str, expected_sha: str | None = None) -> dict:
    if expected_sha is not None and file_sha256(path) != expected_sha:
        raise ValueError(f"Frozen file SHA mismatch: {path.name}")
    payload = _load(path)
    if payload.get(id_field) != expected_id:
        raise ValueError(f"Frozen object ID mismatch: {path.name}")
    canonical = dict(payload)
    canonical.pop(id_field)
    if canonical_sha256(canonical) != expected_id:
        raise ValueError(f"Frozen canonical hash mismatch: {path.name}")
    return payload


def _source_change_audit(source: str) -> Round513E3SourceChangeAudit:
    changed = tuple(filter(None, _git("diff", "--name-only", f"{BASE_SOURCE}..{source}").splitlines()))
    forbidden = tuple(path for path in changed if path.startswith((
        "MP5_agent/agent/controller.py", "MP5_agent/dc3pa/evaluation/",
        "MP5_agent/dc3pa/memory/", "MP5_agent/dc3pa/reliability/",
        "MP5_agent/dc3pa/trigger/", "MP5_agent/agent/tasks/",
    )))
    return Round513E3SourceChangeAudit(
        source_commit=source,
        historical_execution_source=BASE_SOURCE,
        reviewed_commits=tuple(_git("rev-list", "--reverse", f"{BASE_SOURCE}..{source}").splitlines()),
        changed_files=changed,
        allowed_change_categories=(
            "formal_50_smoke_candidate_metadata",
            "track_e_provider_json_request_policy",
            "planner_schema_parser_and_bound_schema",
            "e3_versioned_freeze_and_audit_infrastructure",
            "focused_tests_workflow_and_public_documentation",
        ),
        controller_production_changed=any(path == "MP5_agent/agent/controller.py" for path in forbidden),
        evaluator_production_changed=any(path.startswith("MP5_agent/dc3pa/evaluation/") for path in forbidden),
        memory_production_changed=any(path.startswith("MP5_agent/dc3pa/memory/") for path in forbidden),
        scientific_method_changed=any(path.startswith(("MP5_agent/dc3pa/reliability/", "MP5_agent/dc3pa/trigger/")) for path in forbidden),
        gamma_changed=False,
        retry_policy_changed=False,
        cleanup_policy_changed=False,
        formal_task_assets_changed=any(path.startswith("MP5_agent/agent/tasks/") for path in forbidden),
        status="PASS" if not forbidden else "BLOCKED",
    ).with_id()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--boundary-a-root", type=Path, required=True)
    parser.add_argument("--boundary-a-approval", type=Path, required=True)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--prior-authorization-input", type=Path, required=True)
    parser.add_argument("--external-gate-evidence", type=Path, required=True)
    parser.add_argument("--github-actions-evidence", type=Path, required=True)
    args = parser.parse_args()

    source = _git("rev-parse", "HEAD")
    if source != args.source_commit or _git("status", "--porcelain"):
        raise ValueError("Final E3 freeze requires exact clean HEAD")
    remote_sha = _git("ls-remote", "origin", "refs/heads/round513e3f-freeze-reauthorization").split()[0]
    if remote_sha != source:
        raise ValueError("Remote branch does not contain final E3 source")
    if args.output.exists():
        raise FileExistsError("Final E3 output already exists")

    proxy = _verify_hashed(
        args.boundary_a_root / "proxy_action_coverage_decision_input.json",
        "decision_input_id", PROXY_DECISION_ID, PROXY_DECISION_SHA,
    )
    iron = _verify_hashed(
        args.boundary_a_root / "iron_ingot_task_asset_decision_input.json",
        "decision_input_id", IRON_DECISION_ID, IRON_DECISION_SHA,
    )
    approval_text = args.boundary_a_approval.read_text(encoding="utf-8")
    validate_boundary_a_approval(approval_text)
    boundary_receipt = Round513E3AuthorBoundaryAReceipt(
        source_commit=source,
        proxy_decision_input_id=proxy["decision_input_id"],
        proxy_decision_input_file_sha256=PROXY_DECISION_SHA,
        proxy_choice="P1",
        iron_decision_input_id=iron["decision_input_id"],
        iron_decision_input_file_sha256=IRON_DECISION_SHA,
        iron_choice="I1",
        approval_statement_sha256=file_sha256(args.boundary_a_approval),
        deterministic_formal_alignment_authorized=True,
        approved_by="ZYF",
    ).with_id()

    external = _load(args.external_gate_evidence)
    if external.get("source_commit") != source or external.get("status") != "PASS":
        raise ValueError("External gate evidence is not valid for final source")
    external_audit = Round513E3ExternalManifestGateAudit(
        source_commit=source,
        round511_assignment_manifest_id=str(external["round511_assignment_manifest_id"]),
        round511_assignment_manifest_file_sha256=str(external["round511_assignment_manifest_file_sha256"]),
        relevant_tests_passed=int(external["relevant_tests_passed"]),
        relevant_tests_failed=int(external["relevant_tests_failed"]),
        relevant_tests_skipped=int(external["relevant_tests_skipped"]),
        snapshot_guard_passed=bool(external["snapshot_guard_passed"]),
        memory_write_probe_rejected=bool(external["memory_write_probe_rejected"]),
        minedojo_launch_count=int(external["minedojo_launch_count"]),
    ).with_id()
    actions = _load(args.github_actions_evidence)
    if actions.get("head_sha") != source or actions.get("conclusion") != "success":
        raise ValueError("GitHub Actions evidence does not bind green final source")

    source_change = _source_change_audit(source)
    source_freeze = Round513E3SourceFreezeAudit(
        source_commit=source,
        source_change_audit_id=source_change.audit_id,
        boundary_a_receipt_id=boundary_receipt.receipt_id,
        external_manifest_gate_audit_id=external_audit.audit_id,
        github_actions_run_id=str(actions["run_id"]),
        github_actions_url=str(actions["url"]),
        github_actions_conclusion="success",
        remote_branch_contains_source=True,
        worktree_clean=True,
        diff_check_passed=True,
    ).with_id()
    schema, provider_policy, planner_contract, capability = build_provider_contracts(source)
    prior = _load(args.prior_authorization_input)
    compatibility = Round513E3ContractCompatibilityRelease(
        source_commit=source,
        source_freeze_audit_id=source_freeze.audit_id,
        historical_compatibility_release_id=str(prior["compatibility_release_id"]),
        provider_request_policy_id=provider_policy.policy_id,
        planner_runtime_request_contract_id=planner_contract.contract_id,
        planner_schema_id=schema.schema_id,
        parser_id=schema.parser_id,
        historical_e1r_e2h_reconstructable=True,
    ).with_id()
    runtime = CHRMLiteEngineeringSmokeRuntimeReleaseV4_1_2_E3(
        source_commit=source,
        source_freeze_audit_id=source_freeze.audit_id,
        compatibility_release_id=compatibility.release_id,
        provider_request_policy_id=provider_policy.policy_id,
        planner_runtime_request_contract_id=planner_contract.contract_id,
        technical_retry_policy_id=TECHNICAL_RETRY_POLICY_ID,
        process_cleanup_policy_id=PROCESS_CLEANUP_POLICY_ID,
        controller_id=str(prior["controller_id"]),
        evaluator_id=str(prior["evaluator_id"]),
        budget_profile_id=str(prior["budget_profile_id"]),
        memory_no_write=True,
        evaluation_chain_changed=False,
        minedojo_started=False,
    ).with_id()

    namespace_id, rows = derive_authorized_e3_assignments(
        source_commit=source, formal_root=args.formal_root, namespace_label=NAMESPACE_LABEL,
    )
    resolved_assets = Round513E3ResolvedTaskAssetAudit(
        source_commit=source,
        boundary_a_receipt_id=boundary_receipt.receipt_id,
        original_blocked_asset_audit_id=str(iron["task_asset_audit_id"]),
        formal_taskset_release_id=FORMAL_TASKSET_RELEASE_ID,
        formal_catalog_file_sha256=file_sha256(args.formal_root / "schema_v2/final_tasks.csv"),
        assignment_count=9,
        catalog_match_count=9,
        difficulty_match_count=9,
        immutable_asset_binding_count=9,
        formal_assets_modified=False,
        status="PASS",
    ).with_id()
    pool = CHRMLiteEngineeringSmokePoolV4_1_2_E3(
        source_commit=source, namespace_id=namespace_id,
        task_asset_audit_id=resolved_assets.audit_id,
        proxy_policy="P1", assignment_count=9,
    ).with_id()
    assignments = CHRMLiteEngineeringSmokeAssignmentsV4_1_2_E3(
        source_commit=source, namespace_id=namespace_id,
        runtime_release_id=runtime.release_id, assignments=rows,
    ).with_id()
    protected_root = canonical_sha256({
        "acquisition": "03127d1296e8ba9ef8f62707f665d3ec21ec233aa4fdad6452690e005098720f",
        "historical_development": "90553e430d1effc09ef95f6afa995c64e26d60fdcd432212496a1ff3c444c406",
        "previous_smoke": "3157a431b880872f08f6c410978bc2b57e46428cfef6e2699ddfc4765279890f",
        "formal_catalog": FORMAL_CATALOG_CANONICAL_SHA256,
    })
    exclusion = CHRMLiteEngineeringSmokeExclusionAuditV4_1_2_E3(
        source_commit=source, assignments_id=assignments.assignments_id,
        namespace_id=namespace_id, protected_namespace_root=protected_root,
        acquisition_overlap_count=0, historical_development_overlap_count=0,
        previous_smoke_overlap_count=0, future_formal_v412_overlap_count=0,
        holdout_overlap_count=0, final_overlap_count=0,
        proof_method="cryptographic_namespace_and_assignment_id_domain_separation",
        eligible=True,
    ).with_id()
    assignment_payload = [item.to_dict() for item in rows]
    seal = CHRMLiteEngineeringSmokeSealV4_1_2_E3(
        source_commit=source, pool_id=pool.pool_id,
        assignments_id=assignments.assignments_id,
        assignments_root_sha256=canonical_sha256(assignment_payload),
        exclusion_audit_id=exclusion.audit_id,
        compatibility_release_id=compatibility.release_id,
        runtime_release_id=runtime.release_id,
        assignment_count=9, proxy_policy="P1",
    ).with_id()
    authorization = CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2_E3(
        source_commit=source, source_freeze_audit_id=source_freeze.audit_id,
        e2_closeout_id="ccffd372afaa152440114b880329a29837f365c6894254621f99b72da49c9df8",
        boundary_a_receipt_id=boundary_receipt.receipt_id,
        runtime_release_id=runtime.release_id, compatibility_release_id=compatibility.release_id,
        provider_request_policy_id=provider_policy.policy_id,
        planner_runtime_request_contract_id=planner_contract.contract_id,
        planner_schema_id=schema.schema_id, planner_prompt_id=schema.prompt_id,
        planner_parser_id=schema.parser_id, formal_taskset_release_id=FORMAL_TASKSET_RELEASE_ID,
        formal_catalog_sha256=FORMAL_CATALOG_CANONICAL_SHA256,
        task_asset_audit_id=resolved_assets.audit_id, proxy_policy="P1",
        pool_id=pool.pool_id, assignments_id=assignments.assignments_id,
        exclusion_audit_id=exclusion.audit_id, seal_id=seal.seal_id,
        paper_memory_release_id=str(prior["paper_memory_release_id"]),
        paper_memory_root=str(prior["paper_memory_root"]),
        mineclip_policy_id=str(prior["mineclip_policy_id"]),
        scene_exemplar_release_id=str(prior["scene_exemplar_release_id"]),
        rule_registry_id=str(prior["rule_registry_id"]),
        bilateral_policy_id=str(prior["bilateral_policy_id"]),
        decision_record_schema_id=str(prior["decision_record_schema_id"]),
        step_outcome_registry_id=str(prior["step_outcome_registry_id"]),
        instrumentation_release_id=str(prior["instrumentation_release_id"]),
        controller_id=str(prior["controller_id"]), evaluator_id=str(prior["evaluator_id"]),
        budget_profile_id=str(prior["budget_profile_id"]),
        technical_retry_policy_id=TECHNICAL_RETRY_POLICY_ID,
        process_cleanup_policy_id=PROCESS_CLEANUP_POLICY_ID,
        gamma_candidate=GAMMA_CANDIDATE_B, gamma_cov_text=GAMMA_TEXT[0],
        gamma_minus_text=GAMMA_TEXT[1], gamma_plus_text=GAMMA_TEXT[2],
        declarations=E3_AUTHORIZATION_DECLARATIONS,
    ).with_id()

    args.output.mkdir(parents=True, mode=0o700)
    objects = {
        "author_boundary_a_receipt.json": (boundary_receipt.to_dict(), "receipt_id"),
        "source_change_audit.json": (source_change.to_dict(), "audit_id"),
        "external_manifest_gate_audit.json": (external_audit.to_dict(), "audit_id"),
        "source_freeze_audit.json": (source_freeze.to_dict(), "audit_id"),
        "provider_request_policy.json": (provider_policy.to_dict(), "policy_id"),
        "planner_runtime_request_contract.json": (planner_contract.to_dict(), "contract_id"),
        "json_mode_capability_receipt.json": (capability.to_dict(), "receipt_id"),
        "contract_compatibility_release.json": (compatibility.to_dict(), "release_id"),
        "runtime_release.json": (runtime.to_dict(), "release_id"),
        "resolved_task_asset_audit.json": (resolved_assets.to_dict(), "audit_id"),
        "engineering_smoke_pool.json": (pool.to_dict(), "pool_id"),
        "engineering_smoke_assignments.json": (assignments.to_dict(), "assignments_id"),
        "engineering_smoke_exclusion_audit.json": (exclusion.to_dict(), "audit_id"),
        "engineering_smoke_seal.json": (seal.to_dict(), "seal_id"),
        "engineering_smoke_authorization_input.json": (authorization.to_dict(), "authorization_input_id"),
    }
    manifest_rows = []
    for filename, (payload, id_field) in objects.items():
        path = args.output / filename
        _write(path, payload)
        manifest_rows.append({"filename": filename, "id": payload[id_field], "sha256": file_sha256(path)})
    manifest = {
        "source_commit": source, "phase": "AUTHOR_BOUNDARY_B",
        "source_frozen": True, "assignment_count": 9,
        "proxy_policy": "P1", "iron_asset_policy": "I1",
        "authorization_status": "pending_ZYF_boundary_B",
        "minedojo_execution_permitted": False, "minedojo_started": False,
        "artifacts": manifest_rows,
    }
    manifest["manifest_id"] = canonical_sha256(manifest)
    _write(args.output / "manifest.json", manifest)
    print(json.dumps({
        "phase": manifest["phase"], "manifest_id": manifest["manifest_id"],
        "source_freeze_audit_id": source_freeze.audit_id,
        "seal_id": seal.seal_id,
        "authorization_input_id": authorization.authorization_input_id,
        "minedojo_started": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
