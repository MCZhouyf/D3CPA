#!/usr/bin/env python3
"""Focused hosted gate for Round 5 monotonic fusion."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROUND5_TESTS = [
    "tests_dc3pa/test_round5_feature_extraction.py",
    "tests_dc3pa/test_round5_grouped_dataset.py",
    "tests_dc3pa/test_round5_fusion_artifact.py",
    "tests_dc3pa/test_round5_monotonic_trainer.py",
    "tests_dc3pa/test_round5_shadow_invariance.py",
    "tests_dc3pa/test_round5_contract_and_factory.py",
    "tests_dc3pa/test_round5_memory_count_independence.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tests = [item for item in ROUND5_TESTS if (root / item).exists()]
    if not tests:
        raise SystemExit("No Round 5 tests found")
    command = [sys.executable, "-m", "pytest", "-q", *tests]
    if args.junit:
        output = Path(args.junit)
        output.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={output}")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
