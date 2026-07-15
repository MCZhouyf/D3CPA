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

from dc3pa.reliability.development_binding import (
    DatasetBindingExpectation,
    activation_policy_id,
    environment_parameter_sha256,
    load_collection_manifest,
    validate_dataset_binding,
)
from dc3pa.reliability.development_protocol import load_protocol
from dc3pa.reliability.final_test_exclusion import load_final_test_exclusion
from dc3pa.reliability.fusion_artifact import FusionArtifact, save_fusion_artifact
from dc3pa.reliability.fusion_dataset import dataset_sha256, load_jsonl
from dc3pa.reliability.fusion_features import FEATURE_SCHEMA_VERSION
from dc3pa.reliability.fusion_training import TrainerConfig, fit_monotonic_logistic


def combined_hash(*values: str) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _validate_if_requested(
    *,
    args,
    protocol,
    training,
    tuning,
) -> tuple[dict, dict]:
    strict_inputs = [
        args.final_test_exclusion,
        args.train_collection,
        args.tune_collection,
    ]
    if not any(strict_inputs):
        return {}, {}
    if not all(strict_inputs):
        raise ValueError(
            "--final-test-exclusion, --train-collection, and --tune-collection "
            "must be supplied together for paper binding"
        )
    exclusion = load_final_test_exclusion(args.final_test_exclusion)
    exclusion.validate_assignments(protocol.assignments)
    protocol_id = protocol.protocol_id or protocol.compute_protocol_id()
    exclusion_id = exclusion.manifest_id or exclusion.compute_manifest_id()

    def validate(role: str, examples, collection_path: str):
        collection = load_collection_manifest(collection_path)
        expectation = DatasetBindingExpectation(
            role=role,
            protocol_id=protocol_id,
            final_test_exclusion_id=exclusion_id,
            memory_snapshot_sha256=protocol.memory_snapshot_sha256,
            confidence_artifact_id=protocol.confidence_artifact_id,
            knowledge_impl=protocol.knowledge_impl,
            model_confidence_impl=protocol.model_confidence_impl,
            environment_impl=protocol.environment_impl,
            environment_scope=protocol.environment_scope,
            environment_parameter_sha256=environment_parameter_sha256(
                protocol.environment_parameters
            ),
            source_commit=args.created_from_commit,
        )
        report = validate_dataset_binding(
            examples,
            protocol=protocol,
            final_exclusion=exclusion,
            collection=collection,
            expectation=expectation,
        )
        report.require_eligible()
        return report.to_dict()

    return (
        validate("dev_train", training, args.train_collection),
        validate("dev_tune", tuning, args.tune_collection),
    )


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
    parser.add_argument("--final-test-exclusion", default="")
    parser.add_argument("--train-collection", default="")
    parser.add_argument("--tune-collection", default="")
    args = parser.parse_args()

    protocol = load_protocol(args.protocol)
    protocol_id = protocol.protocol_id or protocol.compute_protocol_id()
    training = load_jsonl(Path(args.train_dataset))
    tuning = load_jsonl(Path(args.tune_dataset))
    if any(item.split == "test" for item in training + tuning):
        raise ValueError("Train/tune files must not contain locked holdout examples")
    train_binding, tune_binding = _validate_if_requested(
        args=args,
        protocol=protocol,
        training=training,
        tuning=tuning,
    )

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
            "development_protocol_id": protocol_id,
            "activation_policy_id": activation_policy_id(protocol),
            "train_dataset_sha256": train_hash,
            "tune_dataset_sha256": tune_hash,
            "holdout_not_opened": True,
            "train_binding": train_binding,
            "tune_binding": tune_binding,
        },
    ).with_id()
    artifact_id = save_fusion_artifact(Path(args.output_artifact), artifact)
    report = {
        "artifact_id": artifact_id,
        "development_protocol_id": protocol_id,
        "activation_policy_id": activation_policy_id(protocol),
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
        "train_binding": train_binding,
        "tune_binding": tune_binding,
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
