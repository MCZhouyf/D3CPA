#!/usr/bin/env python3
"""Run the hosted Round 5.12.1 reconciliation and safeguard gate."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests_dc3pa/test_round512_closeout.py",
    "tests_dc3pa/test_round5121_policy.py",
    "tests_dc3pa/test_round5121_reconciliation.py",
    "tests_dc3pa/test_round5121_runner_safeguards.py",
    "tests_dc3pa/test_round511_campaign_runner.py",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    command = [sys.executable, "-m", "pytest", "-q", *TESTS]
    if args.junit is not None:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        command.extend(["--junitxml", str(args.junit)])
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
