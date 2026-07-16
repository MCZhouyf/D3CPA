#!/usr/bin/env python3
"""Focused hosted gate for Round 5.10 formal acquisition and memory freeze."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


TESTS = [
    "tests_dc3pa/test_round510_execution.py",
    "tests_dc3pa/test_round510_tooling_binding.py",
    "tests_dc3pa/test_round510_source_extension.py",
    "tests_dc3pa/test_round510_retry_limits.py",
    "tests_dc3pa/test_round510_acquisition_binding.py",
    "tests_dc3pa/test_round510_batch.py",
    "tests_dc3pa/test_round510_scene_only.py",
    "tests_dc3pa/test_round510_acquisition_audit.py",
    "tests_dc3pa/test_round510_memory_contract.py",
    "tests_dc3pa/test_round510_snapshot_release.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    selected = [item for item in TESTS if (root / item).exists()]
    if not selected:
        raise SystemExit("No Round 5.10 tests found")
    command = [sys.executable, "-m", "pytest", "-q", *selected]
    if args.junit:
        output = Path(args.junit)
        output.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={output}")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
