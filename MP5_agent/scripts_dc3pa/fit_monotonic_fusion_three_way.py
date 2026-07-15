#!/usr/bin/env python3
"""Fit only on dev_train and dev_tune; never open holdout data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.reliability.development_protocol import load_protocol
from dc3pa.reliability.fusion_artifact import FusionArtifact, save_fusion_artifact
from dc3pa.reliability.fusion_dataset import dataset_sha256, load_jsonl
from dc3pa.reliability.fusion_features import FEATURE_SCHEMA_VERSION
from dc3pa.reliability.fusion_training import TrainerConfig, fit_monotonic_logistic


def combined_hash(*values: str) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dataset", required=True)
    parser.add_argument("--tune-dataset", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output-artifact", required=True)
    parser.add_argument("--output-report", required=True)
    parser.add_argument("--created-from-commit", required=True)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--l2", type=float, default=1e-3)
    parser.add_argument("--max-epochs", type=int, default=5000)
    parser.add_argument("--patience", type=int, default=200)
    args = parser.parse_args()

    protocol = load_protocol(args.protocol)
    training = load_jsonl(Path(args.train_dataset))
    tuning = load_jsonl(Path(args.tune_dataset))
    if any(item.split == "test" for item in training + tuning):
        raise ValueError("Train/tune files must not contain locked holdout examples")

    fit = fit_monotonic_logistic(
        training,
        tuning,
        config=TrainerConfig(
            learning_rate=args.learning_rate,
            l2=args.l2,
            max_epochs=args.max_epochs,
            patience=args.patience,
        ),
    )
    train_hash = dataset_sha256(training)
    tune_hash = dataset_sha256(tuning)
    artifact = FusionArtifact(
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        knowledge_impl=protocol.knowledge_impl,
        model_confidence_impl=protocol.model_confidence_impl,
        environment_impl=protocol.environment_impl,
        environment_scope=protocol.environment_scope,
        knowledge_unknown_prior=0.5,
        environment_unknown_compatibility=0.5,
        intercept=fit.intercept,
        coefficients=fit.coefficients,
        dataset_sha256=combined_hash(train_hash, tune_hash),
        memory_snapshot_sha256=protocol.memory_snapshot_sha256,
        confidence_artifact_id=protocol.confidence_artifact_id,
        created_from_commit=args.created_from_commit,
        training_metrics=fit.training_metrics,
        validation_metrics=fit.validation_metrics,
        trainer_config={
            **dict(fit.trainer_config),
            "development_protocol_id": protocol.protocol_id,
            "train_dataset_sha256": train_hash,
            "tune_dataset_sha256": tune_hash,
            "holdout_not_opened": True,
        },
    ).with_id()
    artifact_id = save_fusion_artifact(Path(args.output_artifact), artifact)
    report = {
        "artifact_id": artifact_id,
        "development_protocol_id": protocol.protocol_id,
        "train_count": len(training),
        "tune_count": len(tuning),
        "train_dataset_sha256": train_hash,
        "tune_dataset_sha256": tune_hash,
        "holdout_not_opened": True,
        "epochs": fit.epochs,
        "coefficients": dict(fit.coefficients),
        "training_metrics": dict(fit.training_metrics),
        "tune_metrics": dict(fit.validation_metrics),
        "legacy_tune_metrics": (
            dict(fit.legacy_validation_metrics)
            if fit.legacy_validation_metrics
            else None
        ),
        "equal_weight_tune_metrics": dict(fit.equal_weight_validation_metrics),
        "note": (
            "This report is not an activation decision. The locked development "
            "holdout must be evaluated separately under a pre-hashed policy."
        ),
    }
    output = Path(args.output_report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
