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

from dc3pa.reliability.development_protocol import load_protocol, sha256_file
from dc3pa.reliability.fusion_artifact import load_fusion_artifact
from dc3pa.reliability.holdout_evaluation import load_holdout_report
from dc3pa.reliability.paper_release import (
    build_paper_release,
    save_paper_release,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-name", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--holdout-report", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output-release", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()

    artifact = load_fusion_artifact(args.artifact)
    report = load_holdout_report(args.holdout_report)
    protocol = load_protocol(args.protocol)

    release = build_paper_release(
        release_name=args.release_name,
        artifact=artifact,
        artifact_sha256=sha256_file(args.artifact),
        report=report,
        report_sha256=sha256_file(args.holdout_report),
        development_protocol_id=protocol.protocol_id,
        activation_policy_id=protocol.activation_policy_sha256,
        environment_parameters=protocol.environment_parameters,
        source_commit=args.source_commit,
    )
    save_paper_release(args.output_release, release)
    print(json.dumps(release.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
