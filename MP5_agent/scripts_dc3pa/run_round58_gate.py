#!/usr/bin/env python3
"""Focused hosted gate for Round 5.8 GPT-5.1 reference profile."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


TESTS = [
    "tests_dc3pa/test_round58_reference_split.py",
    "tests_dc3pa/test_round58_seed_isolation.py",
    "tests_dc3pa/test_round58_development_roles.py",
    "tests_dc3pa/test_round58_reference_policies.py",
    "tests_dc3pa/test_round58_model_profile.py",
    "tests_dc3pa/test_round58_responses_adapter.py",
    "tests_dc3pa/test_round58_generator.py",
    "tests_dc3pa/test_round58_stage6_profile.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tests = [item for item in TESTS if (root / item).exists()]
    if not tests:
        raise SystemExit("No Round 5.8 tests found")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        "not minedojo",
        *tests,
    ]
    if args.junit:
        report = Path(args.junit)
        report.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={report}")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
