#!/usr/bin/env python3
"""Focused hosted gate for Round 4 environment evidence V2."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROUND4_TESTS = [
    "tests_dc3pa/test_round4_environment_modes.py",
    "tests_dc3pa/test_round4_environment_v2.py",
    "tests_dc3pa/test_round4_config_and_factory.py",
    "tests_dc3pa/test_round4_shadow_invariance.py",
    "tests_dc3pa/test_round4_context_scope.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    existing = [test for test in ROUND4_TESTS if (root / test).exists()]
    if not existing:
        raise SystemExit("No Round 4 tests were found")

    command = [sys.executable, "-m", "pytest", "-q", *existing]
    if args.junit:
        report = Path(args.junit)
        report.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={report}")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
