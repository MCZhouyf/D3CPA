#!/usr/bin/env python3
"""Focused hosted gate for Round 5.9.2 final-taskset release."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


TESTS = [
    "tests_dc3pa/test_round592_taskset_amendment.py",
    "tests_dc3pa/test_round592_task_semantics.py",
    "tests_dc3pa/test_round592_semantic_fixture.py",
    "tests_dc3pa/test_round592_final_taskset_release.py",
    "tests_dc3pa/test_round592_command_evidence.py",
    "tests_dc3pa/test_round592_preacquisition_gate.py",
    "tests_dc3pa/test_round592_approval.py",
    "tests_dc3pa/test_round592_schedule_cli.py",
    "tests_dc3pa/test_round592_stage6_task_identity.py",
    "tests_dc3pa/test_round592_readiness_marker.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    selected = [item for item in TESTS if (root / item).exists()]
    if not selected:
        raise SystemExit("No Round 5.9.2 tests found")
    command = [sys.executable, "-m", "pytest", "-q", *selected]
    if args.junit:
        output = Path(args.junit)
        output.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={output}")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
