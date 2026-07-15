#!/usr/bin/env python3
"""Evaluate a locked development holdout exactly under a pre-specified policy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.reliability.activation_policy import load_activation_policy
from dc3pa.reliability.development_protocol import load_protocol
from dc3pa.reliability.fusion_artifact import load_fusion_artifact
from dc3pa.reliability.fusion_dataset import load_jsonl
from dc3pa.reliability.holdout_evaluation import (
    evaluate_holdout,
    save_holdout_report,
)
from dc3pa.experiments.dry_run import ensure_not_dry_run_artifact_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--holdout-dataset", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--activation-policy", required=True)
    parser.add_argument("--output-report", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()

    ensure_not_dry_run_artifact_path(args.artifact, label="fusion artifact")
    ensure_not_dry_run_artifact_path(args.holdout_dataset, label="holdout dataset")
    artifact = load_fusion_artifact(args.artifact)
    holdout = load_jsonl(Path(args.holdout_dataset))
    protocol = load_protocol(args.protocol)
    policy = load_activation_policy(args.activation_policy)

    if protocol.activation_policy_sha256 != policy.policy_id:
        raise ValueError("Protocol was not preregistered with this activation policy")
    if artifact.memory_snapshot_sha256 != protocol.memory_snapshot_sha256:
        raise ValueError("Artifact and protocol memory snapshot mismatch")
    if artifact.confidence_artifact_id != protocol.confidence_artifact_id:
        raise ValueError("Artifact and protocol confidence artifact mismatch")

    report = evaluate_holdout(
        holdout,
        artifact=artifact,
        policy=policy,
        protocol_id=protocol.protocol_id,
        source_commit=args.source_commit,
    )
    save_holdout_report(args.output_report, report, refuse_overwrite=True)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
