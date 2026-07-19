#!/usr/bin/env python3
"""Build the immutable Round 5.11 closeout report without opening holdout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round511_closeout import (
    build_round511_closeout,
    write_closeout_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--campaign-root", required=True)
    parser.add_argument("--campaign-summary", required=True)
    parser.add_argument("--train-decisions", required=True)
    parser.add_argument("--tune-decisions", required=True)
    parser.add_argument("--scene-lineage-audit", required=True)
    parser.add_argument("--development-protocol", required=True)
    parser.add_argument("--analysis-policy", required=True)
    parser.add_argument("--development-tooling-binding", required=True)
    parser.add_argument("--development-input-release", required=True)
    parser.add_argument("--collection-audit", required=True)
    parser.add_argument("--confidence-release", required=True)
    parser.add_argument("--environment-release", required=True)
    parser.add_argument("--fusion-release", required=True)
    parser.add_argument("--paper-memory-release", required=True)
    parser.add_argument("--active-taskset-release", required=True)
    parser.add_argument("--sealed-holdout", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report = build_round511_closeout(
        baseline_sha=args.baseline_sha,
        campaign_root=args.campaign_root,
        campaign_summary_path=args.campaign_summary,
        train_decisions_path=args.train_decisions,
        tune_decisions_path=args.tune_decisions,
        scene_lineage_audit_path=args.scene_lineage_audit,
        development_protocol_path=args.development_protocol,
        analysis_policy_path=args.analysis_policy,
        development_tooling_binding_path=args.development_tooling_binding,
        development_input_release_path=args.development_input_release,
        collection_audit_path=args.collection_audit,
        confidence_release_path=args.confidence_release,
        environment_release_path=args.environment_release,
        fusion_release_path=args.fusion_release,
        paper_memory_release_path=args.paper_memory_release,
        active_taskset_release_path=args.active_taskset_release,
        sealed_holdout_path=args.sealed_holdout,
    )
    write_closeout_report(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
