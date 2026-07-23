#!/usr/bin/env python3
"""Round 5.13D synthetic instrumentation and optional full-environment gate."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_TESTS = (
    "tests_dc3pa/test_round513d_instrumentation.py",
    "tests_dc3pa/test_round513d_runtime.py",
    "tests_dc3pa/test_round513d_readiness.py",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--full-environment", action="store_true")
    args = parser.parse_args()
    command = [sys.executable, "-m", "pytest", "-q"]
    if args.full_environment:
        command.extend(("-m", "minedojo", "tests_dc3pa/test_round513d_full_environment.py"))
    else:
        command.extend(SYNTHETIC_TESTS)
    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        command.extend(("--junitxml", str(args.junit)))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
