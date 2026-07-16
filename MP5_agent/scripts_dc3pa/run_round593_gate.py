#!/usr/bin/env python3
"""Focused hosted gate for Round 5.9.3 Controller/fallback revision."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


TESTS = [
    "tests_dc3pa/test_round593_fallback_policy.py",
    "tests_dc3pa/test_round593_fallback_event.py",
    "tests_dc3pa/test_round593_receipt_metrics.py",
    "tests_dc3pa/test_round593_readiness_natural_only.py",
    "tests_dc3pa/test_round593_paired_campaign.py",
    "tests_dc3pa/test_round593_controller_revision.py",
    "tests_dc3pa/test_round593_evidence_invalidation.py",
    "tests_dc3pa/test_round593_provider_model_alias.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    selected = [item for item in TESTS if (root / item).exists()]
    if not selected:
        raise SystemExit("No Round 5.9.3 tests found")
    command = [sys.executable, "-m", "pytest", "-q", *selected]
    if args.junit:
        output = Path(args.junit)
        output.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={output}")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
