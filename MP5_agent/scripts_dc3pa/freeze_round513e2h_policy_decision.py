#!/usr/bin/env python3
"""Freeze E2H supersession and the unresolved retry/cleanup author input."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round513e2h import (  # noqa: E402
    PolicyCandidate,
    ProcessCleanupPolicyProvenanceAudit,
    Round513E2AuthorizationSupersessionDecision,
    TechnicalRetryAndCleanupDecisionInput,
    TechnicalRetryPolicyProvenanceAudit,
    canonical_sha256,
    file_sha256,
)


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object: {path}")
    return payload


def _write(path: Path, payload: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--old-authorization-input", type=Path, required=True)
    parser.add_argument("--old-approval", type=Path, required=True)
    parser.add_argument("--old-seal", type=Path, required=True)
    parser.add_argument("--retry-policy", type=Path, required=True)
    parser.add_argument("--cleanup-script", type=Path, required=True)
    args = parser.parse_args()

    source = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT.parent, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT.parent, check=True,
        capture_output=True, text=True,
    ).stdout.strip():
        raise ValueError("E2H policy decision freeze requires a clean worktree")
    if args.output.exists():
        raise FileExistsError("E2H policy decision output already exists")
    args.output.mkdir(parents=True)

    old_auth = _load(args.old_authorization_input)
    old_seal = _load(args.old_seal)
    retry = _load(args.retry_policy)
    supersession = Round513E2AuthorizationSupersessionDecision(
        source_commit=source,
        old_authorization_input_id=str(old_auth["authorization_input_id"]),
        old_authorization_input_file_sha256=file_sha256(args.old_authorization_input),
        old_approval_statement_sha256=file_sha256(args.old_approval),
        old_assignment_seal_id=str(old_seal["seal_id"]),
        old_execution_source_sha=str(old_auth["source_commit"]),
    ).with_id()

    retry_candidate = PolicyCandidate(
        candidate_id=str(retry["policy_id"]),
        source_scope="Round 5.10 formal Acquisition, not prospective E2 Smoke",
        source_file_sha256=file_sha256(args.retry_policy),
        completeness="incomplete_for_E2",
        scientific_validity_impact=(
            "preserves scientific failures and attempts but lacks E2 total-attempt, "
            "backoff, and cleanup bindings"
        ),
        engineering_cost="up to two technical retries per entry in its original scope",
    )
    retry_audit = TechnicalRetryPolicyProvenanceAudit(
        source_commit=source,
        candidates=(retry_candidate,),
        unique_complete_forward_policy_found=False,
        missing_required_fields=(
            "E2_scope_authorization", "maximum_attempts_by_error_category",
            "total_maximum_attempts", "backoff", "process_cleanup_policy_id",
            "unclassified_failure_campaign_stop",
        ),
        conclusion="AUTHOR_DECISION_REQUIRED",
    ).with_id()

    cleanup_sha = file_sha256(args.cleanup_script)
    cleanup_candidate = PolicyCandidate(
        candidate_id=canonical_sha256({
            "source_file_sha256": cleanup_sha,
            "scope": "legacy stop_agent_bg shell script",
        }),
        source_scope="Legacy background-agent shutdown helper",
        source_file_sha256=cleanup_sha,
        completeness="incomplete_for_E2",
        scientific_validity_impact=(
            "does not prove scoped ownership of killed processes or complete residual cleanup"
        ),
        engineering_cost="fast broad process-name cleanup with unrelated-process risk",
    )
    cleanup_audit = ProcessCleanupPolicyProvenanceAudit(
        source_commit=source,
        candidates=(cleanup_candidate,),
        unique_complete_forward_policy_found=False,
        missing_required_fields=(
            "campaign_owned_process_groups", "MineDojo_process_check",
            "Minecraft_process_check", "Mineflayer_process_check", "bridge_process_check",
            "port_inventory", "lock_inventory", "display_session_inventory",
            "graceful_shutdown_timeout", "post_cleanup_zero_residual_assertion",
        ),
        unrelated_process_kill_risk=True,
        conclusion="AUTHOR_DECISION_REQUIRED",
    ).with_id()

    decision = TechnicalRetryAndCleanupDecisionInput(
        source_commit=source,
        retry_provenance_audit_id=retry_audit.audit_id,
        cleanup_provenance_audit_id=cleanup_audit.audit_id,
        retry_candidates=(
            {
                "candidate": "T0_no_retry",
                "maximum_attempts_per_technical_category": 1,
                "total_maximum_attempts": 1,
                "backoff_requires_author_value": False,
                "scientific_success_retries": 0,
                "scientific_failure_retries": 0,
                "impact": "lowest contamination risk; technical failures remain unresolved",
            },
            {
                "candidate": "T1_one_retry",
                "maximum_attempts_per_technical_category": 2,
                "total_maximum_attempts": 2,
                "backoff_requires_author_value": True,
                "scientific_success_retries": 0,
                "scientific_failure_retries": 0,
                "impact": "moderate recovery cost; requires exact backoff and category approval",
            },
            {
                "candidate": "T2_two_retries_R510_aligned",
                "maximum_attempts_per_technical_category": 3,
                "total_maximum_attempts": 3,
                "backoff_requires_author_value": True,
                "scientific_success_retries": 0,
                "scientific_failure_retries": 0,
                "impact": "highest recovery cost; R5.10 count precedent but not E2 authorization",
            },
        ),
        cleanup_candidates=(
            {
                "candidate": "C1_scoped_process_group_cleanup",
                "scope": "only campaign-recorded process groups, ports, locks, and displays",
                "impact": "lowest unrelated-process risk; requires complete launch ownership ledger",
            },
            {
                "candidate": "C2_scoped_then_verified_signature_fallback",
                "scope": "campaign process groups, then exact executable/signature fallback",
                "impact": "stronger recovery with additional identity and grace-time requirements",
            },
        ),
        required_author_fields=(
            "retry_candidate", "allowed_technical_failure_categories",
            "maximum_attempts_per_technical_category", "total_maximum_attempts",
            "backoff_seconds", "cleanup_candidate", "cleanup_grace_seconds",
            "campaign_owned_ports", "campaign_owned_lock_patterns",
            "campaign_owned_display_sessions",
        ),
    ).with_id()

    objects = (
        ("round513e2_authorization_supersession_decision.json", supersession.to_dict(), supersession.decision_id),
        ("technical_retry_policy_provenance_audit.json", retry_audit.to_dict(), retry_audit.audit_id),
        ("process_cleanup_policy_provenance_audit.json", cleanup_audit.to_dict(), cleanup_audit.audit_id),
        ("technical_retry_and_cleanup_decision_input.json", decision.to_dict(), decision.decision_input_id),
    )
    manifest_entries = []
    for filename, payload, object_id in objects:
        path = args.output / filename
        _write(path, payload)
        manifest_entries.append({"filename": filename, "id": object_id, "sha256": file_sha256(path)})
    manifest = {
        "schema_version": 1,
        "source_commit": source,
        "status": "BLOCKED_PENDING_ZYF_RETRY_CLEANUP_DECISION",
        "minedojo_started": False,
        "smoke_outcomes_observed": False,
        "new_assignment_seal_created": False,
        "new_authorization_input_created": False,
        "artifacts": manifest_entries,
    }
    _write(args.output / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
