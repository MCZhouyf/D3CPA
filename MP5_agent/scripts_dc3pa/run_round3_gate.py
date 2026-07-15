#!/usr/bin/env python3
"""Focused hosted gate for Round 3 additive modules and integration tests."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROUND3_TESTS = [
    "tests_dc3pa/test_round3_ordinal_levels_and_parser.py",
    "tests_dc3pa/test_round3_observation_collector.py",
    "tests_dc3pa/test_round3_ordinal_calibration.py",
    "tests_dc3pa/test_round3_step_labels.py",
    "tests_dc3pa/test_round3_config_and_factory.py",
    "tests_dc3pa/test_round3_runtime_join.py",
    "tests_dc3pa/test_round3_shadow_invariance.py",
    "tests_dc3pa/test_round3_artifact_fail_closed.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit")
    parser.add_argument("--include-integration", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tests = list(ROUND3_TESTS)
    if args.include_integration:
        pass
    command = [sys.executable, "-m", "pytest", "-q", *tests]
    if args.junit:
        command.append(f"--junitxml={args.junit}")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
