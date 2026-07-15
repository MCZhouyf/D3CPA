#!/usr/bin/env python3
"""Focused hosted gate for Round 5.6 real-experiment configuration."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROUND56_TESTS = [
    "tests_dc3pa/test_round56_paper_task_matrix.py",
    "tests_dc3pa/test_round56_acquisition_development_isolation.py",
    "tests_dc3pa/test_round56_author_approval.py",
    "tests_dc3pa/test_round56_environment_search_binding.py",
    "tests_dc3pa/test_round56_launch_validation.py",
    "tests_dc3pa/test_round56_phase_state.py",
    "tests_dc3pa/test_round56_pack_validation.py",
    "tests_dc3pa/test_round56_draft_rejection.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tests = [test for test in ROUND56_TESTS if (root / test).exists()]
    if not tests:
        raise SystemExit("No Round 5.6 tests found")
    command = [sys.executable, "-m", "pytest", "-q", *tests]
    if args.junit:
        output = Path(args.junit)
        output.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={output}")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
