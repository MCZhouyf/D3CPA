#!/usr/bin/env python3
"""Hosted synthetic gate for the read-only Round 5.13B auditor."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRAFTS = (
    ROOT / "dc3pa/configs/round513_historical_compatibility_audit.DRAFT.json",
    ROOT / "dc3pa/configs/round513_historical_data_decision.DRAFT.json",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path)
    args = parser.parse_args()
    for path in DRAFTS:
        if json.loads(path.read_text(encoding="utf-8")).get("status") != "DRAFT":
            raise ValueError(f"Historical audit public contract is not DRAFT: {path.name}")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests_dc3pa/test_round513_audit.py",
        "tests_dc3pa/test_round513_method.py",
        "tests_dc3pa/test_round5126_supersession.py",
    ]
    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        command.extend(("--junitxml", str(args.junit)))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
