#!/usr/bin/env python3
"""Run one real-environment controlled task-semantics fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.integration.round592_semantics import collect_task_semantic_receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-task", required=True)
    parser.add_argument("--difficulty", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--task-asset-validation-report-id", required=True)
    parser.add_argument("--requested-seed", required=True)
    parser.add_argument("--output-receipt", required=True)
    parser.add_argument("--output-trace", required=True)
    parser.add_argument("--output-observation", required=True)
    args = parser.parse_args()
    receipt = collect_task_semantic_receipt(
        runtime_task_path=args.runtime_task,
        difficulty=args.difficulty,
        source_commit=args.source_commit,
        task_asset_validation_report_id=args.task_asset_validation_report_id,
        requested_seed=args.requested_seed,
        output_receipt=args.output_receipt,
        output_trace=args.output_trace,
        output_observation=args.output_observation,
    )
    print(json.dumps(receipt.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
