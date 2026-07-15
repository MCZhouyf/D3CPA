#!/usr/bin/env python3
"""Focused hosted gate for Round 5.7 author decisions and dry-run audit."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


TESTS = [
    "tests_dc3pa/test_round57_author_pack_placeholders.py",
    "tests_dc3pa/test_round57_author_pack_matrix.py",
    "tests_dc3pa/test_round57_prompt_hashes.py",
    "tests_dc3pa/test_round57_dry_run_selection.py",
    "tests_dc3pa/test_round57_dry_run_audit.py",
    "tests_dc3pa/test_round57_pack_manifest.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tests = [item for item in TESTS if (root / item).exists()]
    if not tests:
        raise SystemExit("No Round 5.7 tests found")
    command = [sys.executable, "-m", "pytest", "-q", *tests]
    if args.junit:
        output = Path(args.junit)
        output.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={output}")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
