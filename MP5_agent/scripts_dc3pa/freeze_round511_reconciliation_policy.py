#!/usr/bin/env python3
"""Write the immutable Round 5.11 reconciliation policy once."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round511_reconciliation import (
    Round511ReconciliationPolicy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    policy = Round511ReconciliationPolicy().with_id()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(policy.to_dict(), handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"policy_id": policy.policy_id}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
