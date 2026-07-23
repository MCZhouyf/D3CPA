#!/usr/bin/env python3
"""Hosted synthetic gate for prospective Round 5.13C contracts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "dc3pa/configs/round513cd_collection_contracts.DRAFT.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path)
    args = parser.parse_args()
    payload = json.loads(DRAFT.read_text(encoding="utf-8"))
    if payload.get("status") != "DRAFT" or len(payload.get("contracts", ())) != 12:
        raise ValueError("Round 5.13C public DRAFT inventory is incomplete")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests_dc3pa/test_round513c_collection_contracts.py",
    ]
    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        command.extend(("--junitxml", str(args.junit)))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
