#!/usr/bin/env python3
"""Hosted gate for the Round 5.12 closeout boundary."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", default="")
    args = parser.parse_args()
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests_dc3pa/test_round512_closeout.py",
    ]
    if args.junit:
        output = Path(args.junit)
        output.parent.mkdir(parents=True, exist_ok=True)
        command.extend(["--junitxml", str(output)])
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
