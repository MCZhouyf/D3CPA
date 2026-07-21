#!/usr/bin/env python3
"""Evaluate the consumed holdout once and freeze an eligible or null release."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round5124_holdout_evaluator import evaluate_locked_holdout


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "features",
        "candidate",
        "activation-policy",
        "runtime-release",
        "execution-manifest",
        "ledger",
        "campaign-summary",
        "output-report",
        "output-paper-release",
    ):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = evaluate_locked_holdout(
        feature_path=args.features,
        candidate_path=args.candidate,
        activation_policy_path=args.activation_policy,
        runtime_release_path=args.runtime_release,
        execution_manifest_path=args.execution_manifest,
        ledger_path=args.ledger,
        campaign_summary_path=args.campaign_summary,
        source_commit=source_commit,
    )
    _write(args.output_report, report)
    release = None
    if report["eligible"]:
        release = {
            "schema_version": 1,
            "release_name": "Round5124PaperFusionRelease",
            "source_commit": source_commit,
            "candidate_artifact_id": report["candidate_artifact_id"],
            "activation_policy_id": report["activation_policy_id"],
            "holdout_report_id": report["report_id"],
            "final_runtime_release_id": report["final_runtime_release_id"],
            "single_use_ledger_id": report["single_use_ledger_id"],
            "eligible": True,
            "final_evaluation_opened": False,
        }
        import hashlib

        release["release_id"] = hashlib.sha256(
            json.dumps(release, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    _write(args.output_paper_release, release)
    print(json.dumps({"report": report, "paper_fusion_release": release}, indent=2, sort_keys=True))
    return 0 if report["eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
