#!/usr/bin/env python3
"""Run the hosted Round 5.12.6 pre-authorization gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests_dc3pa/test_round5126_confirmatory.py",
    "tests_dc3pa/test_round5124_holdout.py",
    "tests_dc3pa/test_round5125_replacement_holdout.py",
    "tests_dc3pa/test_round5121_runner_safeguards.py",
)
DRAFTS = (
    "dc3pa/configs/round5126_replacement_authorization.DRAFT.json",
    "dc3pa/configs/round5126_replacement_design.DRAFT.json",
    "dc3pa/configs/round5126_seed_namespace.DRAFT.json",
)


def _validate_drafts() -> None:
    for relative in DRAFTS:
        payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        if payload.get("status", payload.get("approval_status")) != "DRAFT":
            raise ValueError(f"Public contract is not DRAFT: {relative}")
    authorization = json.loads((ROOT / DRAFTS[0]).read_text(encoding="utf-8"))
    if authorization.get("authorization_id") is not None:
        raise ValueError("Public DRAFT fabricates an authorization ID")
    namespace = json.loads((ROOT / DRAFTS[2]).read_text(encoding="utf-8"))
    if namespace.get("salt_commitment_sha256") is not None:
        raise ValueError("Public DRAFT contains a namespace commitment")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path)
    args = parser.parse_args()
    _validate_drafts()
    command = [sys.executable, "-m", "pytest", "-q", *TESTS]
    if args.junit is not None:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        command.extend(("--junitxml", str(args.junit)))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
