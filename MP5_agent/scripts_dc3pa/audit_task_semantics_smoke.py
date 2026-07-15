#!/usr/bin/env python3
"""Audit six critical task-semantics receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.final_taskset_release import (
    audit_task_semantics,
    load_semantic_receipt,
    save_immutable,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--task-asset-validation-report-id", required=True)
    parser.add_argument("--receipt", action="append", required=True)
    parser.add_argument("--output-report", required=True)
    args = parser.parse_args()

    report = audit_task_semantics(
        [load_semantic_receipt(path) for path in args.receipt],
        source_commit=args.source_commit,
        task_asset_validation_report_id=(
            args.task_asset_validation_report_id
        ),
    )
    save_immutable(args.output_report, report.to_dict())
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
