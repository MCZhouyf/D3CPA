#!/usr/bin/env python3
"""Freeze an eligible fusion artifact and holdout report into a paper release."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.reliability.development_binding import (
    activation_policy_id,
    environment_parameter_sha256,
)
from dc3pa.reliability.development_protocol import load_protocol, sha256_file
from dc3pa.reliability.fusion_artifact import load_fusion_artifact
from dc3pa.reliability.holdout_evaluation import load_holdout_report
from dc3pa.reliability.holdout_lock import load_holdout_lock
from dc3pa.reliability.paper_release import (
    build_paper_release,
    save_paper_release,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-name", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--holdout-report", required=True)
    parser.add_argument("--holdout-lock", required=True)
    parser.add_argument("--attempt-ledger", required=True)
    parser.add_argument("--final-test-exclusion-id", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output-release", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()

    artifact = load_fusion_artifact(args.artifact)
    report = load_holdout_report(args.holdout_report)
    lock = load_holdout_lock(args.holdout_lock)
    protocol = load_protocol(args.protocol)
    protocol_id = protocol.protocol_id or protocol.compute_protocol_id()
    artifact_id = artifact.artifact_id or artifact.compute_artifact_id()
    if lock.lock_id != lock.compute_lock_id():
        raise ValueError("Holdout lock ID mismatch")
    if lock.development_protocol_id != protocol_id:
        raise ValueError("Holdout lock protocol mismatch")
    if lock.fusion_artifact_id != artifact_id:
        raise ValueError("Holdout lock artifact mismatch")
    if lock.activation_policy_id != activation_policy_id(protocol):
        raise ValueError("Holdout lock activation policy mismatch")

    release = build_paper_release(
        release_name=args.release_name,
        artifact=artifact,
        artifact_sha256=sha256_file(args.artifact),
        report=report,
        report_sha256=sha256_file(args.holdout_report),
        development_protocol_id=protocol_id,
        activation_policy_id=activation_policy_id(protocol),
        environment_parameters=protocol.environment_parameters,
        source_commit=args.source_commit,
        final_test_exclusion_id=args.final_test_exclusion_id,
        holdout_lock_id=lock.lock_id,
        holdout_attempt_ledger_sha256=sha256_file(args.attempt_ledger),
        environment_parameter_sha256=environment_parameter_sha256(
            protocol.environment_parameters
        ),
    )
    save_paper_release(args.output_release, release)
    print(json.dumps(release.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
