#!/usr/bin/env python3
"""Audit externally produced tiny dry-run receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.dry_run import (
    audit_dry_run,
    load_campaign,
    load_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--receipt", action="append", required=True)
    parser.add_argument("--output-report", required=True)
    args = parser.parse_args()

    report = audit_dry_run(
        load_campaign(args.campaign),
        [load_receipt(path) for path in args.receipt],
    )
    output = Path(args.output_report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
