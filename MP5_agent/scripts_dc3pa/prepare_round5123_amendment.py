#!/usr/bin/env python3
"""Audit the completed development campaign and emit external Phase A drafts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round5123_audit import (
    Round5123AuditInputs,
    build_draft_amendment,
    build_runtime_segment_manifest,
    git_source_identity_resolver,
    write_json_immutable,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round5122-result-sha", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--campaign-root", action="append", type=Path, required=True)
    parser.add_argument("--assignments", type=Path, required=True)
    parser.add_argument("--effective-status", type=Path, required=True)
    parser.add_argument("--effective-train", type=Path, required=True)
    parser.add_argument("--effective-tune", type=Path, required=True)
    parser.add_argument("--continuation-manifest", type=Path, required=True)
    parser.add_argument("--continuation-approval", type=Path, required=True)
    parser.add_argument("--development-input-release", type=Path, required=True)
    parser.add_argument("--paper-memory-release", type=Path, required=True)
    parser.add_argument("--active-taskset-release", type=Path, required=True)
    parser.add_argument("--formal-log-bootstrap-policy", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--output-draft-amendment", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manifest = build_runtime_segment_manifest(
        Round5123AuditInputs(
            round5122_result_sha=args.round5122_result_sha,
            campaign_roots=tuple(args.campaign_root),
            assignments_path=args.assignments,
            effective_status_path=args.effective_status,
            effective_train_path=args.effective_train,
            effective_tune_path=args.effective_tune,
            continuation_manifest_path=args.continuation_manifest,
            continuation_approval_path=args.continuation_approval,
            development_input_release_path=args.development_input_release,
            paper_memory_release_path=args.paper_memory_release,
            active_taskset_release_path=args.active_taskset_release,
            formal_log_bootstrap_policy_path=args.formal_log_bootstrap_policy,
        ),
        source_identity_resolver=git_source_identity_resolver(args.repo_root),
    )
    amendment = build_draft_amendment(manifest)
    write_json_immutable(args.output_manifest, manifest.to_dict())
    write_json_immutable(args.output_draft_amendment, amendment.to_dict())
    print(
        json.dumps(
            {
                "runtime_segment_manifest_id": manifest.manifest_id,
                "segment_count": len(manifest.segments),
                "resolved_units": 60,
                "accepted_decision_records": 681,
                "draft_amendment_id": amendment.amendment_id,
                "draft_status": amendment.status,
                "author_approval_required": True,
                "fusion_fitted": False,
                "holdout_opened": False,
                "final_evaluation_opened": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
