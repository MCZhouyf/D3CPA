#!/usr/bin/env python3
"""Freeze public-safe CHRM-lite + CDT-lite V4.1 contracts externally."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round513_method import build_method_contracts


def _write_exclusive(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    method, feature, label, provenance, statistical = build_method_contracts(
        args.source_commit
    )
    outputs = {
        "chrmlite_cdtlite_method_contract_v4_1.json": method.to_dict(),
        "chrmlite_feature_schema_v4_1.json": feature.to_dict(),
        "chrmlite_label_policy_v4_1.json": label.to_dict(),
        "chrmlite_parameter_provenance_policy_v4_1.json": provenance.to_dict(),
        "chrmlite_statistical_analysis_policy_v4_1.json": statistical.to_dict(),
    }
    for name, payload in outputs.items():
        _write_exclusive(args.output_dir / name, payload)
    print(json.dumps({
        "method_contract_id": method.contract_id,
        "feature_schema_id": feature.schema_id,
        "label_policy_id": label.policy_id,
        "parameter_provenance_policy_id": provenance.policy_id,
        "statistical_analysis_policy_id": statistical.policy_id,
        "model_fitted": False,
        "cdt_parameters_estimated": False,
        "holdout_accessed": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
