#!/usr/bin/env python3
"""Retire the unconsumed Round 5.12.6 path and freeze its Logistic baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round5126_confirmatory import sha256_file
from dc3pa.experiments.round5126_supersession import (
    OldMonotonicLogisticBaselineRelease,
    RetiredAuthorizationRegistry,
    Round5126SupersessionDecision,
)


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--source-sha", required=True)
    value.add_argument("--authorization-input", type=Path, required=True)
    value.add_argument("--invalidation-receipt", type=Path, required=True)
    value.add_argument("--preflight-binding", type=Path, required=True)
    value.add_argument("--runtime-release", type=Path, required=True)
    value.add_argument("--exclusion-registry", type=Path, required=True)
    value.add_argument("--candidate", type=Path, required=True)
    value.add_argument("--feature-schema", type=Path, required=True)
    value.add_argument("--confidence-release", type=Path, required=True)
    value.add_argument("--environment-release", type=Path, required=True)
    value.add_argument("--paper-memory-release", type=Path, required=True)
    value.add_argument("--development-train", type=Path, required=True)
    value.add_argument("--development-tune", type=Path, required=True)
    value.add_argument("--fusion-train", type=Path, required=True)
    value.add_argument("--fusion-tune", type=Path, required=True)
    value.add_argument("--activation-policy", type=Path, required=True)
    value.add_argument("--output-dir", type=Path, required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    authorization = _load(args.authorization_input)
    invalidation = _load(args.invalidation_receipt)
    preflight = _load(args.preflight_binding)
    runtime = _load(args.runtime_release)
    exclusion = _load(args.exclusion_registry)
    candidate = _load(args.candidate)
    feature_schema = _load(args.feature_schema)
    confidence = _load(args.confidence_release)
    environment = _load(args.environment_release)
    memory = _load(args.paper_memory_release)
    activation = _load(args.activation_policy)

    if authorization.get("source_sha") != args.source_sha:
        raise ValueError("Pending authorization source SHA changed")
    if authorization.get("authorization_status") != "pending":
        raise ValueError("Old authorization is not pending")
    if any(
        authorization.get(name)
        for name in (
            "assignment_generation_permitted",
            "additional_holdout_generation_permitted",
            "post_holdout_tuning_permitted",
            "final_evaluation_permitted",
            "round6_permitted",
        )
    ):
        raise ValueError("Pending authorization opened a forbidden phase")
    expected_invalidation = {
        "status": "invalidated_before_assignment_generation",
        "assignments_generated": False,
        "ledger_created": False,
        "bundle_read": False,
        "minedojo_started": False,
        "salt_and_namespace_reuse_forbidden": True,
    }
    if any(invalidation.get(key) != value for key, value in expected_invalidation.items()):
        raise ValueError("Old authorization was not invalidated before generation")
    if invalidation.get("authorization_input_id") != authorization.get(
        "authorization_input_id"
    ):
        raise ValueError("Invalidation/authorization identity mismatch")
    if invalidation.get("authorization_input_sha256") != sha256_file(
        args.authorization_input
    ):
        raise ValueError("Invalidation/authorization file hash mismatch")

    decision = Round5126SupersessionDecision(
        source_sha=args.source_sha,
        pending_authorization_input_id=str(authorization["authorization_input_id"]),
        invalidation_receipt_id=str(invalidation["receipt_id"]),
    ).with_id()
    registry = RetiredAuthorizationRegistry(
        source_sha=args.source_sha,
        pending_authorization_input_id=str(authorization["authorization_input_id"]),
        pending_authorization_input_sha256=sha256_file(args.authorization_input),
        salt_commitment_sha256=str(authorization["namespace"]["salt_commitment_sha256"]),
        namespace_id=str(authorization["namespace"]["namespace_id"]),
        preflight_binding_id=str(preflight["binding_id"]),
        preflight_binding_sha256=sha256_file(args.preflight_binding),
        runtime_release_id=str(runtime["release_id"]),
        runtime_release_sha256=sha256_file(args.runtime_release),
        exclusion_registry_id=str(exclusion["registry_id"]),
        exclusion_registry_sha256=sha256_file(args.exclusion_registry),
        invalidation_receipt_id=str(invalidation["receipt_id"]),
        supersession_decision_id=decision.decision_id,
    ).with_id()
    baseline = OldMonotonicLogisticBaselineRelease(
        release_name="OldMonotonicLogisticBaselineRelease",
        retired_from_source_sha=args.source_sha,
        model_source_commit=str(candidate["source_commit"]),
        feature_schema_id=str(candidate["feature_direction_policy_id"]),
        feature_schema_sha256=sha256_file(args.feature_schema),
        feature_order=tuple(candidate["feature_order"]),
        coefficients={key: float(value) for key, value in candidate["coefficients"].items()},
        intercept=float(candidate["intercept"]),
        selected_l2=float(candidate["selected_l2"]),
        selected_checkpoint=int(candidate["selected_checkpoint"]),
        confidence_release_id=str(confidence["release_id"]),
        confidence_release_sha256=sha256_file(args.confidence_release),
        environment_release_id=str(environment["release_id"]),
        environment_release_sha256=sha256_file(args.environment_release),
        paper_memory_v5_release_id=str(memory["release_id"]),
        paper_memory_v5_root_sha256=str(memory["snapshot_root_sha256"]),
        development_train_sha256=sha256_file(args.development_train),
        development_tune_sha256=sha256_file(args.development_tune),
        fusion_train_sha256=sha256_file(args.fusion_train),
        fusion_tune_sha256=sha256_file(args.fusion_tune),
        activation_policy_id=str(activation["policy_id"]),
        activation_policy_sha256=sha256_file(args.activation_policy),
    ).with_id()

    outputs = {
        "round5126_supersession_decision.json": decision.to_dict(),
        "retired_authorization_registry.json": registry.to_dict(),
        "old_monotonic_logistic_baseline_release.json": baseline.to_dict(),
    }
    for name, payload in outputs.items():
        _write_exclusive(args.output_dir / name, payload)
    print(
        json.dumps(
            {
                "supersession_decision_id": decision.decision_id,
                "retired_authorization_registry_id": registry.registry_id,
                "old_logistic_baseline_release_id": baseline.release_id,
                "assignments_generated": False,
                "ledger_created": False,
                "bundle_read": False,
                "minedojo_started": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
