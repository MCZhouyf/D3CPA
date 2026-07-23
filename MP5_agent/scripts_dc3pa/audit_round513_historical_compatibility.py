#!/usr/bin/env python3
"""Run the read-only Round 5.13B audit against mounted immutable artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round513_audit import (
    HistoricalAuditInputs,
    build_historical_compatibility_audit,
)


def _write_exclusive(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--source-commit", required=True)
    value.add_argument("--train", type=Path, required=True)
    value.add_argument("--tune", type=Path, required=True)
    value.add_argument("--acceptance", type=Path, required=True)
    value.add_argument("--closeout", type=Path, required=True)
    value.add_argument("--effective-status", type=Path, required=True)
    value.add_argument("--campaign-root", action="append", type=Path, required=True)
    value.add_argument("--paper-memory-release", type=Path, required=True)
    value.add_argument("--paper-memory-database", type=Path, required=True)
    value.add_argument("--scene-lineage-audit", type=Path, required=True)
    value.add_argument("--confidence-release", type=Path, required=True)
    value.add_argument("--environment-release", type=Path, required=True)
    value.add_argument("--fusion-feature-release", type=Path, required=True)
    value.add_argument("--active-taskset-release", type=Path, required=True)
    value.add_argument("--ordinal-confidence-source", type=Path, required=True)
    value.add_argument("--output-dir", type=Path, required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    artifacts = build_historical_compatibility_audit(
        HistoricalAuditInputs(
            source_commit=args.source_commit,
            train_path=args.train,
            tune_path=args.tune,
            acceptance_path=args.acceptance,
            closeout_path=args.closeout,
            effective_status_path=args.effective_status,
            campaign_roots=tuple(args.campaign_root),
            paper_memory_release_path=args.paper_memory_release,
            paper_memory_database_path=args.paper_memory_database,
            scene_lineage_audit_path=args.scene_lineage_audit,
            confidence_release_path=args.confidence_release,
            environment_release_path=args.environment_release,
            fusion_feature_release_path=args.fusion_feature_release,
            active_taskset_release_path=args.active_taskset_release,
            ordinal_confidence_source_path=args.ordinal_confidence_source,
        )
    )
    names = (
        "historical_dataset_lineage_audit.json",
        "feature_availability_matrix.json",
        "missing_evidence_registry.json",
        "cdt_identifiability_audit.json",
        "historical_log_compatibility_audit.json",
        "round513_historical_data_decision.json",
    )
    for name, artifact in zip(names, artifacts):
        _write_exclusive(args.output_dir / name, artifact.to_dict())
    lineage, matrix, _, cdt, compatibility, decision = artifacts
    print(json.dumps({
        "lineage_audit_id": lineage.audit_id,
        "train_rows": lineage.train_rows,
        "tune_rows": lineage.tune_rows,
        "feature_matrix_id": matrix.matrix_id,
        "compatibility_audit_id": compatibility.audit_id,
        "same_generation_confidence_rows": compatibility.same_generation_confidence_rows,
        "environment_bilateral_rows": compatibility.environment_bilateral_rows,
        "main_label_fully_joined_rows": compatibility.main_label_fully_joined_rows,
        "cdt_audit_id": cdt.audit_id,
        "cdt_decision": cdt.decision,
        "historical_data_decision_id": decision.decision_id,
        "historical_data_decision": decision.decision,
        "holdout_accessed": False,
        "minedojo_started": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
