#!/usr/bin/env python3
"""Validate train/tune real-development inputs without opening holdout data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.reliability.activation_policy import load_activation_policy
from dc3pa.reliability.development_binding import (
    DatasetBindingExpectation,
    activation_policy_id,
    environment_parameter_sha256,
    load_collection_manifest,
    validate_dataset_binding,
)
from dc3pa.reliability.development_protocol import load_protocol
from dc3pa.reliability.final_test_exclusion import load_final_test_exclusion
from dc3pa.reliability.fusion_dataset import load_jsonl


def validate_role(
    *,
    role: str,
    dataset_path: str,
    collection_path: str,
    protocol,
    policy,
    exclusion,
    source_commit: str,
):
    examples = load_jsonl(Path(dataset_path))
    collection = load_collection_manifest(collection_path)
    protocol_id = protocol.protocol_id or protocol.compute_protocol_id()
    exclusion_id = exclusion.manifest_id or exclusion.compute_manifest_id()
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
        source_commit=source_commit,
    )
    report = validate_dataset_binding(
        examples,
        protocol=protocol,
        final_exclusion=exclusion,
        collection=collection,
        expectation=expectation,
    )
    report.require_eligible()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--activation-policy", required=True)
    parser.add_argument("--final-test-exclusion", required=True)
    parser.add_argument("--train-dataset", required=True)
    parser.add_argument("--train-collection", required=True)
    parser.add_argument("--tune-dataset", required=True)
    parser.add_argument("--tune-collection", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-report", required=True)
    args = parser.parse_args()

    protocol = load_protocol(args.protocol)
    policy = load_activation_policy(args.activation_policy)
    exclusion = load_final_test_exclusion(args.final_test_exclusion)
    protocol_id = protocol.protocol_id or protocol.compute_protocol_id()
    policy_id = policy.policy_id or policy.compute_policy_id()
    exclusion_id = exclusion.manifest_id or exclusion.compute_manifest_id()
    if activation_policy_id(protocol) != policy_id:
        raise ValueError("Protocol and activation policy IDs differ")
    exclusion.validate_assignments(protocol.assignments)

    train = validate_role(
        role="dev_train",
        dataset_path=args.train_dataset,
        collection_path=args.train_collection,
        protocol=protocol,
        policy=policy,
        exclusion=exclusion,
        source_commit=args.source_commit,
    )
    tune = validate_role(
        role="dev_tune",
        dataset_path=args.tune_dataset,
        collection_path=args.tune_collection,
        protocol=protocol,
        policy=policy,
        exclusion=exclusion,
        source_commit=args.source_commit,
    )

    report = {
        "eligible": True,
        "holdout_not_opened": True,
        "development_protocol_id": protocol_id,
        "activation_policy_id": policy_id,
        "final_test_exclusion_id": exclusion_id,
        "train": train.to_dict(),
        "tune": tune.to_dict(),
    }
    output = Path(args.output_report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
