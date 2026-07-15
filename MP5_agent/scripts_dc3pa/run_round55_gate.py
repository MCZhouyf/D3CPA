#!/usr/bin/env python3
"""Focused hosted gate for Round 5.5 real-development activation."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROUND55_TESTS = [
    "tests_dc3pa/test_round55_development_protocol.py",
    "tests_dc3pa/test_round55_activation_policy.py",
    "tests_dc3pa/test_round55_grouped_bootstrap.py",
    "tests_dc3pa/test_round55_holdout_isolation.py",
    "tests_dc3pa/test_round55_paper_release.py",
    "tests_dc3pa/test_round55_data_audit.py",
    "tests_dc3pa/test_round55_runtime_release_binding.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tests = [item for item in ROUND55_TESTS if (root / item).exists()]
    if not tests:
        raise SystemExit("No Round 5.5 tests found")
    command = [sys.executable, "-m", "pytest", "-q", *tests]
    if args.junit:
        output = Path(args.junit)
        output.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={output}")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
