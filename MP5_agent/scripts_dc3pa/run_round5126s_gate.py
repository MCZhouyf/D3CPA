#!/usr/bin/env python3
"""Hosted gate for retiring the unconsumed Round 5.12.6 path."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRAFTS = (
    "dc3pa/configs/round5126_supersession_decision.DRAFT.json",
    "dc3pa/configs/old_monotonic_logistic_baseline_release.DRAFT.json",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path)
    args = parser.parse_args()
    for relative in DRAFTS:
        payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        if payload.get("status") != "DRAFT":
            raise ValueError(f"Public supersession contract is not DRAFT: {relative}")
    command = [sys.executable, "-m", "pytest", "-q", "tests_dc3pa/test_round5126_supersession.py"]
    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        command.extend(("--junitxml", str(args.junit)))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
