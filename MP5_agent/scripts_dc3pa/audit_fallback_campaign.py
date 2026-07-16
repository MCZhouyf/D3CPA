#!/usr/bin/env python3
"""Summarize natural and fallback-assisted dry-run metrics separately."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.paired_dry_run import summarize_receipts


def load(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument(
        "--campaign-kind",
        required=True,
        choices=("natural_readiness", "fallback_diagnostic"),
    )
    parser.add_argument("--receipt", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    summary = summarize_receipts(
        campaign_id=args.campaign_id,
        campaign_kind=args.campaign_kind,
        receipt_payloads=[load(path) for path in args.receipt],
    )
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
