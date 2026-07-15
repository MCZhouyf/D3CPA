#!/usr/bin/env python3
"""Fit and validate DC3PA's four-feature monotonic Logistic fusion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.reliability.fusion_artifact import (
    FusionArtifact,
    save_fusion_artifact,
)
from dc3pa.reliability.fusion_dataset import (
    dataset_sha256,
    load_jsonl,
    validate_group_isolation,
)
from dc3pa.reliability.fusion_features import FEATURE_SCHEMA_VERSION
from dc3pa.reliability.fusion_training import (
    TrainerConfig,
    fit_monotonic_logistic,
)
from dc3pa.experiments.dry_run import ensure_not_dry_run_artifact_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output-artifact", required=True)
    parser.add_argument("--output-report", required=True)
    parser.add_argument("--memory-snapshot-sha256", required=True)
    parser.add_argument("--confidence-artifact-id", required=True)
    parser.add_argument("--created-from-commit", required=True)
    parser.add_argument("--knowledge-impl", default="hard_gate_v2")
    parser.add_argument("--model-confidence-impl", default="ordinal_calibrated")
    parser.add_argument("--environment-impl", default="topk_v2")
    parser.add_argument("--environment-scope", default="current_context_only")
    parser.add_argument("--knowledge-prior", type=float, default=0.5)
    parser.add_argument("--environment-unknown", type=float, default=0.5)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--l2", type=float, default=1e-3)
    parser.add_argument("--max-epochs", type=int, default=5000)
    parser.add_argument("--patience", type=int, default=200)
    args = parser.parse_args()

    ensure_not_dry_run_artifact_path(args.dataset, label="fusion dataset")
    examples = load_jsonl(Path(args.dataset))
    validate_group_isolation(examples)
    training = [item for item in examples if item.split == "train"]
    validation = [item for item in examples if item.split == "validation"]
    if any(item.split == "test" for item in examples):
        # A test split can be present for later locked evaluation, but the
        # trainer must not inspect its labels or metrics.
        pass

    fit = fit_monotonic_logistic(
        training,
        validation,
        config=TrainerConfig(
            learning_rate=args.learning_rate,
            l2=args.l2,
            max_epochs=args.max_epochs,
            patience=args.patience,
        ),
    )
    artifact = FusionArtifact(
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        knowledge_impl=args.knowledge_impl,
        model_confidence_impl=args.model_confidence_impl,
        environment_impl=args.environment_impl,
        environment_scope=args.environment_scope,
        knowledge_unknown_prior=args.knowledge_prior,
        environment_unknown_compatibility=args.environment_unknown,
        intercept=fit.intercept,
        coefficients=fit.coefficients,
        dataset_sha256=dataset_sha256(examples),
        memory_snapshot_sha256=args.memory_snapshot_sha256,
        confidence_artifact_id=args.confidence_artifact_id,
        created_from_commit=args.created_from_commit,
        training_metrics=fit.training_metrics,
        validation_metrics=fit.validation_metrics,
        trainer_config=fit.trainer_config,
    ).with_id()

    artifact_id = save_fusion_artifact(Path(args.output_artifact), artifact)
    report = {
        "artifact_id": artifact_id,
        "training_count": len(training),
        "validation_count": len(validation),
        "epochs": fit.epochs,
        "coefficients": dict(fit.coefficients),
        "intercept": fit.intercept,
        "training_metrics": dict(fit.training_metrics),
        "validation_metrics": dict(fit.validation_metrics),
        "legacy_validation_metrics": (
            dict(fit.legacy_validation_metrics)
            if fit.legacy_validation_metrics
            else None
        ),
        "equal_weight_validation_metrics": dict(fit.equal_weight_validation_metrics),
        "activation_assessment": dict(fit.activation_assessment),
        "warning": (
            "Do not activate monotonic_logistic_v2 unless the development-set "
            "assessment is eligible and shadow traces are manually reviewed."
        ),
    }
    report_path = Path(args.output_report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
