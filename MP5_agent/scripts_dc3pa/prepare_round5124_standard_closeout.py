#!/usr/bin/env python3
"""Audit and freeze the external Round 5.12.4 standard closeout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round5124_audit import (
    StandardCloseoutInputs,
    build_bootstrap_policy,
    build_l2_provenance_audit,
    build_standard_acceptance,
    write_json_immutable,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--source-commit", required=True)
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--author-prompt", type=Path, required=True)
    value.add_argument("--author-effective-date", required=True)
    value.add_argument("--campaign-root", action="append", type=Path, required=True)
    value.add_argument("--assignments", type=Path, required=True)
    value.add_argument("--continuation-manifest", type=Path, required=True)
    value.add_argument("--continuation-approval", type=Path, required=True)
    value.add_argument("--effective-status", type=Path, required=True)
    value.add_argument("--effective-train", type=Path, required=True)
    value.add_argument("--effective-tune", type=Path, required=True)
    value.add_argument("--development-input-release", type=Path, required=True)
    value.add_argument("--analysis-policy", type=Path, required=True)
    value.add_argument("--paper-memory-release", type=Path, required=True)
    value.add_argument("--active-taskset-release", type=Path, required=True)
    value.add_argument("--formal-log-bootstrap-policy", type=Path, required=True)
    value.add_argument("--historical-runtime-manifest", type=Path, required=True)
    value.add_argument("--historical-activation-policy", type=Path, required=True)
    value.add_argument("--output-dir", type=Path, required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    decision, acceptance, closeout = build_standard_acceptance(
        StandardCloseoutInputs(
            source_commit=args.source_commit,
            author_prompt_path=args.author_prompt,
            author_effective_date=args.author_effective_date,
            campaign_roots=tuple(args.campaign_root),
            assignments_path=args.assignments,
            continuation_manifest_path=args.continuation_manifest,
            continuation_approval_path=args.continuation_approval,
            effective_status_path=args.effective_status,
            effective_train_path=args.effective_train,
            effective_tune_path=args.effective_tune,
            development_input_release_path=args.development_input_release,
            analysis_policy_path=args.analysis_policy,
            paper_memory_release_path=args.paper_memory_release,
            active_taskset_release_path=args.active_taskset_release,
            formal_log_bootstrap_policy_path=args.formal_log_bootstrap_policy,
            historical_runtime_manifest_path=args.historical_runtime_manifest,
        )
    )
    l2_audit = build_l2_provenance_audit(args.repo_root)
    bootstrap = build_bootstrap_policy(args.historical_activation_policy)
    outputs = {
        "standardization_decision.json": decision.to_dict(),
        "standard_development_dataset_acceptance.json": acceptance.to_dict(),
        "standard_development_closeout.json": closeout.to_dict(),
        "l2_provenance_audit.json": l2_audit.to_dict(),
        "round5124_bootstrap_policy.json": bootstrap.to_dict(),
    }
    for name, payload in outputs.items():
        write_json_immutable(args.output_dir / name, payload)
    print(
        json.dumps(
            {
                "standardization_decision_id": decision.decision_id,
                "acceptance_id": acceptance.acceptance_id,
                "closeout_id": closeout.closeout_id,
                "l2_provenance_audit_id": l2_audit.audit_id,
                "l2_case": l2_audit.case,
                "l2_candidate_values": list(l2_audit.candidate_values),
                "bootstrap_policy_id": bootstrap.policy_id,
                "holdout_opened": False,
                "fusion_fitted": False,
                "final_evaluation_opened": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
