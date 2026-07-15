#!/usr/bin/env python3
"""Advance dry_run_completed only with complete Round 5.9.1 evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.model_epoch import load_epoch
from dc3pa.experiments.phase_state import load_state, save_state_atomic


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "phase-state", "readiness-report", "closed-model-epoch",
        "task-validation-report", "migration-report", "source-commit", "output-state",
    ):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    readiness = json.loads(Path(args.readiness_report).read_text())
    task_report = json.loads(Path(args.task_validation_report).read_text())
    migration = json.loads(Path(args.migration_report).read_text())
    epoch = load_epoch(args.closed_model_epoch)
    state = load_state(args.phase_state)
    if not readiness.get("eligible"):
        raise SystemExit("Readiness is not eligible")
    if not task_report.get("eligible") or not migration.get("eligible"):
        raise SystemExit("Task validation or semantic migration is not eligible")
    if epoch.status != "closed" or epoch.invariant_errors():
        raise SystemExit("Model epoch is not validly closed")
    expected = {
        "model_epoch_id": epoch.epoch_id,
        "blueprint_id": state.experiment_id,
        "task_asset_validation_report_id": task_report.get("report_id"),
        "migration_report_id": migration.get("report_id"),
    }
    for name, value in expected.items():
        if readiness.get(name) != value:
            raise SystemExit(f"Readiness {name} mismatch")
    advanced = state.advance(
        phase="dry_run_completed",
        source_commit=args.source_commit,
        artifact_ids={
            "round591_readiness_id": readiness["readiness_id"],
            "closed_model_epoch_id": epoch.epoch_id,
            "blueprint_id": state.experiment_id,
            "task_asset_validation_report_id": str(task_report["report_id"]),
            "semantic_migration_report_id": str(migration["report_id"]),
        },
    )
    save_state_atomic(args.output_state, advanced)
    print(json.dumps(advanced.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
