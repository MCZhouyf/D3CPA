#!/usr/bin/env python3
"""Run the final meta-gate before formal acquisition."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.final_taskset_release import (
    load_taskset_release,
    save_immutable,
)
from dc3pa.experiments.preacquisition_gate import (
    audit_preacquisition_gate,
)


def load(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--final-taskset-release", required=True)
    parser.add_argument("--migration-report", required=True)
    parser.add_argument("--approval-binding", required=True)
    parser.add_argument("--blueprint-validation", required=True)
    parser.add_argument("--closed-model-epoch", required=True)
    parser.add_argument("--acquisition-readiness", required=True)
    parser.add_argument("--output-report", required=True)
    args = parser.parse_args()

    report = audit_preacquisition_gate(
        source_commit=args.source_commit,
        final_taskset=load_taskset_release(args.final_taskset_release),
        migration_report=load(args.migration_report),
        approval_binding=load(args.approval_binding),
        blueprint_validation=load(args.blueprint_validation),
        closed_model_epoch=load(args.closed_model_epoch),
        acquisition_readiness=load(args.acquisition_readiness),
    )
    save_immutable(args.output_report, report.to_dict())
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.formal_acquisition_permitted else 2


if __name__ == "__main__":
    raise SystemExit(main())
