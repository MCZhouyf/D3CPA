#!/usr/bin/env python3
"""Prepare the E3F Boundary-A audits; never seal or authorize execution."""

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
    Formal50AlignedSmokeCandidateAudit,
    Round513E2TechnicalCampaignCloseout,
    Round513E3SourceChangeAudit,
    build_decision_inputs,
    build_provider_contracts,
    build_task_asset_audit,
    scientific_payload_root_without_seed_disclosure,
)
from dc3pa.experiments.round513e_authoritative import (  # noqa: E402
    derive_formal_50_task_smoke_assignments,
)


BASE_SOURCE = "a329fd904eb98b96be5328c726531e8b799555f0"
REVIEWED_COMMITS = (
    "6ea8119b0ab37342fedd6ca3c6f8688fe2daac9c",
    "01cba8dc66e6caf10b378f9be9ca0907b9dc4f25",
)
NAMESPACE_LABEL = "dc3pa-round513e3-formal50-engineering-smoke-v4.1.2"


def _write(path: Path, payload: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _source_change_audit(source: str) -> Round513E3SourceChangeAudit:
    changed = tuple(filter(None, _git("diff", "--name-only", f"{BASE_SOURCE}..{source}").splitlines()))
    forbidden_prefixes = (
        "MP5_agent/agent/controller.py",
        "MP5_agent/dc3pa/evaluation/",
        "MP5_agent/dc3pa/memory/",
        "MP5_agent/dc3pa/reliability/",
        "MP5_agent/dc3pa/trigger/",
        "MP5_agent/agent/tasks/",
    )
    forbidden = tuple(path for path in changed if path.startswith(forbidden_prefixes))
    return Round513E3SourceChangeAudit(
        source_commit=source,
        historical_execution_source=BASE_SOURCE,
        reviewed_commits=REVIEWED_COMMITS,
        changed_files=changed,
        allowed_change_categories=(
            "formal_50_smoke_candidate_metadata",
            "track_e_provider_json_request_policy",
            "planner_schema_parser_and_bound_schema",
            "e3_versioned_freeze_and_audit_infrastructure",
            "focused_tests_and_public_documentation",
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


def _campaign_closeout(source: str, campaign_root: Path) -> Round513E2TechnicalCampaignCloseout:
    summary_path = campaign_root / "final_campaign_summary.json"
    report_path = campaign_root / "FINAL_CAMPAIGN_REPORT.md"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    expected = {
        "assignment_count": 9,
        "scientific_record_count": 0,
        "scientific_success_count": 0,
        "scientific_failure_count": 0,
        "original_high_level_action_started_count": 0,
        "evaluation_call_count": 0,
        "memory_or_acquisition_write_count": 0,
        "planner_call_count": 8,
    }
    mismatches = {key: summary.get(key) for key, value in expected.items() if summary.get(key) != value}
    if mismatches:
        raise ValueError(f"Historical campaign summary mismatch: {mismatches}")
    return Round513E2TechnicalCampaignCloseout(
        source_commit=source,
        campaign_id=str(summary["campaign_id"]),
        campaign_summary_file_sha256=file_sha256(summary_path),
        campaign_report_file_sha256=file_sha256(report_path),
    ).with_id()


def _task_hashes() -> dict[str, str]:
    result = {}
    for path in sorted((ROOT / "agent" / "tasks" / "creative").glob("*.json")):
        result[f"agent/tasks/creative/{path.name}"] = file_sha256(path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--campaign-root", type=Path, required=True)
    args = parser.parse_args()

    source = _git("rev-parse", "HEAD")
    if source != args.source_commit:
        raise ValueError("Boundary-A source does not match HEAD")
    if _git("status", "--porcelain"):
        raise ValueError("Boundary-A generation requires a clean worktree")
    if args.output.exists():
        raise FileExistsError("E3F output path already exists")
    args.output.mkdir(parents=True, mode=0o700)

    closeout = _campaign_closeout(source, args.campaign_root)
    source_audit = _source_change_audit(source)
    schema, provider_policy, planner_contract, capability = build_provider_contracts(source)
    task_audit = build_task_asset_audit(
        source_commit=source, agent_root=ROOT, formal_root=args.formal_root,
    )
    namespace_id, assignments = derive_formal_50_task_smoke_assignments(
        source_commit=source,
        namespace_label=NAMESPACE_LABEL,
        task_file_sha256_by_path=_task_hashes(),
    )
    candidate_audit = Formal50AlignedSmokeCandidateAudit(
        source_commit=source,
        namespace_id=namespace_id,
        task_asset_audit_id=task_audit.audit_id,
        candidate_count=len(assignments),
        scientific_payload_root=scientific_payload_root_without_seed_disclosure(assignments),
        task_seed_order_changed_after_observation=False,
        contains_pig_or_creature=any(item.terminal_task in {"pig", "creature"} for item in assignments),
        asset_binding_passed=task_audit.status == "PASS",
        status="PASS" if task_audit.status == "PASS" else "BLOCKED",
    ).with_id()
    iron_decision, proxy_audit, proxy_decision = build_decision_inputs(
        source_commit=source, task_audit=task_audit,
    )

    artifacts = {
        "e2_technical_campaign_closeout.json": (closeout.to_dict(), "closeout_id"),
        "e3_source_change_audit.json": (source_audit.to_dict(), "audit_id"),
        "track_e_provider_request_policy_v4_1_2_e3.json": (provider_policy.to_dict(), "policy_id"),
        "planner_runtime_request_contract_v4_1_2_e3.json": (planner_contract.to_dict(), "contract_id"),
        "track_e_json_mode_capability_receipt.json": (capability.to_dict(), "receipt_id"),
        "formal50_task_asset_binding_audit.json": (task_audit.to_dict(), "audit_id"),
        "formal50_aligned_smoke_candidate_audit.json": (candidate_audit.to_dict(), "audit_id"),
        "iron_ingot_task_asset_decision_input.json": (iron_decision.to_dict(), "decision_input_id"),
        "proxy_action_coverage_audit.json": (proxy_audit.to_dict(), "audit_id"),
        "proxy_action_coverage_decision_input.json": (proxy_decision.to_dict(), "decision_input_id"),
    }
    manifest_rows = []
    for filename, (payload, id_field) in artifacts.items():
        path = args.output / filename
        _write(path, payload)
        manifest_rows.append({"filename": filename, "id": payload[id_field], "sha256": file_sha256(path)})
    manifest = {
        "source_commit": source,
        "phase": "AUTHOR_BOUNDARY_A",
        "source_freeze_permitted": False,
        "assignment_seal_permitted": False,
        "minedojo_execution_permitted": False,
        "formal_task_asset_status": task_audit.status,
        "proxy_policy_status": "PENDING_ZYF",
        "iron_ingot_asset_status": "PENDING_ZYF",
        "planner_schema_id": schema.schema_id,
        "planner_prompt_template_id": schema.prompt_id,
        "planner_parser_id": schema.parser_id,
        "gamma_candidate": "0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f",
        "gamma_cov_text": "1.0",
        "gamma_minus_text": "-0.01040883",
        "gamma_plus_text": "0.00744657",
        "artifacts": manifest_rows,
    }
    manifest["manifest_id"] = canonical_sha256(manifest)
    _write(args.output / "manifest.json", manifest)
    print(json.dumps({
        "phase": manifest["phase"],
        "manifest_id": manifest["manifest_id"],
        "task_asset_status": task_audit.status,
        "proxy_decision_input_id": proxy_decision.decision_input_id,
        "iron_ingot_decision_input_id": iron_decision.decision_input_id,
        "minedojo_started": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
