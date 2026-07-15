#!/usr/bin/env python3
"""Advance dry_run_completed only after the Round 5.9.2 meta-gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.final_taskset_release import load_taskset_release
from dc3pa.experiments.model_epoch import load_epoch
from dc3pa.experiments.phase_state import load_state, save_state_atomic
from dc3pa.experiments.preacquisition_gate import (
    advance_round592_dry_run_phase,
)


def load(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "phase-state", "preacquisition-gate", "readiness-report",
        "closed-model-epoch", "final-taskset-release", "migration-report",
        "source-commit", "output-state",
    ):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    advanced = advance_round592_dry_run_phase(
        state=load_state(args.phase_state),
        source_commit=args.source_commit,
        gate=load(args.preacquisition_gate),
        readiness=load(args.readiness_report),
        model_epoch=load_epoch(args.closed_model_epoch),
        final_taskset=load_taskset_release(args.final_taskset_release),
        migration_report=load(args.migration_report),
    )
    save_state_atomic(args.output_state, advanced)
    print(json.dumps(advanced.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
