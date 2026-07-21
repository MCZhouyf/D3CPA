#!/usr/bin/env python3
"""Fit the fixed-policy Round 5.12.4 candidate using train and tune only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round5124_fusion_data import load_directed_jsonl, sha256_file
from dc3pa.experiments.round5124_fusion_fit import (
    Round5124ActivationPolicy,
    Round5124FitPolicy,
    build_fit_ledger,
    build_tune_selection_report,
    fit_candidate,
    write_json_immutable,
)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    for name in (
        "train",
        "tune",
        "fit-policy",
        "activation-policy",
        "candidate-output",
        "tune-report-output",
        "fit-ledger-output",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    train = load_directed_jsonl(args.train)
    tune = load_directed_jsonl(args.tune)
    if any(item.role != "dev_train" for item in train):
        raise ValueError("Training file contains non-train rows")
    if any(item.role != "dev_tune" for item in tune):
        raise ValueError("Tune file contains non-tune rows")
    fit_payload = load(args.fit_policy)
    fit_payload["l2_candidate_values"] = tuple(fit_payload["l2_candidate_values"])
    fit_policy = Round5124FitPolicy(**fit_payload)
    activation_payload = load(args.activation_policy)
    activation_payload["primary_metrics"] = tuple(
        activation_payload["primary_metrics"]
    )
    activation_payload["calibration_metrics"] = tuple(
        activation_payload["calibration_metrics"]
    )
    activation_policy = Round5124ActivationPolicy(**activation_payload)
    if fit_policy.source_commit != args.source_commit:
        raise ValueError("Fit policy source commit mismatch")
    if activation_policy.source_commit != args.source_commit:
        raise ValueError("Activation policy source commit mismatch")
    artifact = fit_candidate(
        source_commit=args.source_commit,
        train_records=train,
        tune_records=tune,
        fit_policy=fit_policy,
        activation_policy=activation_policy,
        train_dataset_sha256=sha256_file(args.train),
        tune_dataset_sha256=sha256_file(args.tune),
    )
    tune_report = build_tune_selection_report(
        source_commit=args.source_commit,
        records=tune,
        artifact=artifact,
        activation_policy=activation_policy,
    )
    ledger = build_fit_ledger(
        source_commit=args.source_commit,
        train_path=args.train,
        tune_path=args.tune,
        fit_policy=fit_policy,
        activation_policy=activation_policy,
        artifact=artifact,
        tune_report=tune_report,
    )
    write_json_immutable(args.candidate_output, artifact.to_dict())
    write_json_immutable(args.tune_report_output, tune_report)
    write_json_immutable(args.fit_ledger_output, ledger)
    print(
        json.dumps(
            {
                "candidate_artifact_id": artifact.artifact_id,
                "fit_ledger_id": ledger["ledger_id"],
                "tune_selection_report_id": tune_report["report_id"],
                "intercept": artifact.intercept,
                "coefficients": artifact.coefficients,
                "selected_l2": artifact.selected_l2,
                "selected_checkpoint": artifact.selected_checkpoint,
                "holdout_opened": False,
                "final_evaluation_opened": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
