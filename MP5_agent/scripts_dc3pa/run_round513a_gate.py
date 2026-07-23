#!/usr/bin/env python3
"""Hosted CHRM-lite + CDT-lite V4.1 method-contract gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRAFTS = tuple(sorted((ROOT / "dc3pa/configs").glob("round513_*v4_1.DRAFT.json")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path)
    args = parser.parse_args()
    if len(DRAFTS) != 5:
        raise ValueError("V4.1 public DRAFT inventory is incomplete")
    for path in DRAFTS:
        if json.loads(path.read_text(encoding="utf-8")).get("status") != "DRAFT":
            raise ValueError(f"V4.1 public contract is not DRAFT: {path.name}")
    command = [sys.executable, "-m", "pytest", "-q", "tests_dc3pa/test_round513_method.py"]
    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        command.extend(("--junitxml", str(args.junit)))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
