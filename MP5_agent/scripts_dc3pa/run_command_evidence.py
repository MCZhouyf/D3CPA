#!/usr/bin/env python3
"""Run a command and capture immutable stdout/stderr/hash evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.command_evidence import run_command_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-name", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("A command is required after --")

    report = run_command_evidence(
        evidence_name=args.evidence_name,
        source_commit=args.source_commit,
        command=command,
        cwd=args.cwd,
        output_root=args.output_root,
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.passed else report.exit_code or 2


if __name__ == "__main__":
    raise SystemExit(main())
