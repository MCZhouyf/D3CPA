#!/usr/bin/env python3
"""Run the hosted Round 5.12.4 standard-closeout gate."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests_dc3pa/test_round5124_standard_closeout.py",
    "tests_dc3pa/test_round5124_fusion_data.py",
    "tests_dc3pa/test_round5124_fusion_fit.py",
    "tests_dc3pa/test_round5123_amendment.py",
    "tests_dc3pa/test_round5122_contracts.py",
    "tests_dc3pa/test_round55_grouped_bootstrap.py",
    "tests_dc3pa/test_round55_holdout_isolation.py",
    "tests_dc3pa/test_round551_holdout_single_use.py",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path)
    args = parser.parse_args()
    command = [sys.executable, "-m", "pytest", "-q", *TESTS]
    if args.junit is not None:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        command.extend(["--junitxml", str(args.junit)])
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
