#!/usr/bin/env python3
"""Freeze the final runtime-validated taskset release."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.final_taskset_release import (
    build_final_taskset_release,
    load_amendment,
    load_taskset_release,
    load_semantic_report,
    save_immutable,
)


def load_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-name", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--amendment", required=True)
    parser.add_argument("--task-asset-validation", required=True)
    parser.add_argument("--task-semantic-smoke", required=True)
    parser.add_argument("--resolution-report", required=True)
    parser.add_argument("--output-release", required=True)
    parser.add_argument("--prior-final-taskset-release")
    parser.add_argument("--controller-revision")
    args = parser.parse_args()
    if bool(args.prior_final_taskset_release) != bool(args.controller_revision):
        parser.error(
            "taskset amendment reuse requires both prior release and "
            "Controller revision"
        )

    release = build_final_taskset_release(
        release_name=args.release_name,
        source_commit=args.source_commit,
        amendment=load_amendment(args.amendment),
        task_asset_validation=load_json(args.task_asset_validation),
        task_asset_validation_path=args.task_asset_validation,
        semantic_smoke=load_semantic_report(args.task_semantic_smoke),
        semantic_smoke_path=args.task_semantic_smoke,
        resolution_report_path=args.resolution_report,
        prior_taskset_release=(
            load_taskset_release(args.prior_final_taskset_release)
            if args.prior_final_taskset_release
            else None
        ),
        controller_revision=(
            load_json(args.controller_revision) if args.controller_revision else None
        ),
    )
    save_immutable(args.output_release, release.to_dict())
    print(json.dumps(release.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
