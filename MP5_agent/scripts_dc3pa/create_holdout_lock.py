#!/usr/bin/env python3
"""Validate and lock the development holdout before outcome evaluation."""

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
from dc3pa.reliability.fusion_artifact import load_fusion_artifact
from dc3pa.reliability.fusion_dataset import load_jsonl
from dc3pa.reliability.holdout_lock import (
    HoldoutLockManifest,
    save_holdout_lock,
    sha256_file,
    utc_now,
)
from dc3pa.experiments.dry_run import ensure_not_dry_run_artifact_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--activation-policy", required=True)
    parser.add_argument("--final-test-exclusion", required=True)
    parser.add_argument("--holdout-dataset", required=True)
    parser.add_argument("--holdout-collection", required=True)
    parser.add_argument("--fusion-artifact", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-lock", required=True)
    args = parser.parse_args()

    ensure_not_dry_run_artifact_path(args.holdout_dataset, label="holdout dataset")
    ensure_not_dry_run_artifact_path(args.holdout_collection, label="holdout collection")
    ensure_not_dry_run_artifact_path(args.fusion_artifact, label="fusion artifact")
    protocol = load_protocol(args.protocol)
    policy = load_activation_policy(args.activation_policy)
    exclusion = load_final_test_exclusion(args.final_test_exclusion)
    collection = load_collection_manifest(args.holdout_collection)
    artifact = load_fusion_artifact(args.fusion_artifact)
    examples = load_jsonl(Path(args.holdout_dataset))
    protocol_id = protocol.protocol_id or protocol.compute_protocol_id()
    policy_id = policy.policy_id or policy.compute_policy_id()
    exclusion_id = exclusion.manifest_id or exclusion.compute_manifest_id()
    collection_id = collection.manifest_id or collection.compute_manifest_id()

    if activation_policy_id(protocol) != policy_id:
        raise ValueError("Protocol and activation policy IDs differ")
    exclusion.validate_assignments(protocol.assignments)
    if artifact.memory_snapshot_sha256 != protocol.memory_snapshot_sha256:
        raise ValueError("Fusion artifact memory snapshot mismatch")
    if artifact.confidence_artifact_id != protocol.confidence_artifact_id:
        raise ValueError("Fusion artifact confidence artifact mismatch")

    expectation = DatasetBindingExpectation(
        role="dev_holdout",
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
        source_commit=args.source_commit,
    )
    binding = validate_dataset_binding(
        examples,
        protocol=protocol,
        final_exclusion=exclusion,
        collection=collection,
        expectation=expectation,
    )
    binding.require_eligible()
    if any(item.split != "test" for item in examples):
        raise ValueError("Paper holdout requires split='test' for every example")

    lock = HoldoutLockManifest(
        lock_name="dc3pa-development-holdout-v1",
        holdout_dataset_sha256=sha256_file(args.holdout_dataset),
        development_protocol_id=protocol_id,
        activation_policy_id=policy_id,
        fusion_artifact_id=artifact.artifact_id,
        fusion_artifact_sha256=sha256_file(args.fusion_artifact),
        final_test_exclusion_id=exclusion_id,
        collection_manifest_id=collection_id,
        memory_snapshot_sha256=protocol.memory_snapshot_sha256,
        confidence_artifact_id=protocol.confidence_artifact_id,
        environment_parameter_sha256=environment_parameter_sha256(
            protocol.environment_parameters
        ),
        source_commit=args.source_commit,
        created_at=utc_now(),
    ).with_id()
    save_holdout_lock(args.output_lock, lock, refuse_overwrite=True)
    print(
        json.dumps(
            {
                "lock": lock.to_dict(),
                "dataset_binding": binding.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
