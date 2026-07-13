#!/usr/bin/env python3
"""Focused Round 2 gate.  Run from the MP5_agent directory."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROUND2_TESTS = [
    "tests_dc3pa/test_round2_knowledge_v2.py",
    "tests_dc3pa/test_round2_hard_gate_hybrid.py",
    "tests_dc3pa/test_round2_constraint_repair_policy.py",
    "tests_dc3pa/test_stage3_projection_and_knowledge.py",
    "tests_dc3pa/test_stage3_environment_and_hybrid.py",
    "tests_dc3pa/test_stage3_weights_and_config.py",
    "tests_dc3pa/test_stage4_5_planners.py",
    "tests_dc3pa/test_stage6_material_repair.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    command = [sys.executable, "-m", "pytest", "-q"]
    command.extend(["tests_dc3pa"] if args.full else ROUND2_TESTS)
    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={args.junit}")
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
