#!/usr/bin/env python3
"""Focused hosted gate for Round 5.5.1 experiment-safety hardening."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROUND551_TESTS = [
    "tests_dc3pa/test_round551_final_test_exclusion.py",
    "tests_dc3pa/test_round551_dataset_protocol_binding.py",
    "tests_dc3pa/test_round551_per_example_provenance.py",
    "tests_dc3pa/test_round551_collection_accounting.py",
    "tests_dc3pa/test_round551_holdout_lock.py",
    "tests_dc3pa/test_round551_holdout_single_use.py",
    "tests_dc3pa/test_round551_protocol_compatibility.py",
    "tests_dc3pa/test_round551_reproducibility_manifest.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tests = [item for item in ROUND551_TESTS if (root / item).exists()]
    if not tests:
        raise SystemExit("No Round 5.5.1 tests found")
    command = [sys.executable, "-m", "pytest", "-q", *tests]
    if args.junit:
        output = Path(args.junit)
        output.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={output}")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
