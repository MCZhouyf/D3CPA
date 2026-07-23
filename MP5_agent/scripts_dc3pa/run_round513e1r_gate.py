#!/usr/bin/env python3
"""Hosted synthetic gate for authoritative V4.1.2 and E1R preparation."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path)
    args = parser.parse_args()
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests_dc3pa/test_round513e_authoritative.py",
    ]
    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        command.extend(("--junitxml", str(args.junit)))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
