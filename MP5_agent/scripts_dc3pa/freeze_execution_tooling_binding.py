#!/usr/bin/env python3
"""Freeze a tooling binding from a Git-computed source-extension audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.execution_tooling_binding import (
    ALLOWED_CHANGE_CLASSES,
    ExecutionToolingBinding,
)


def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "source-audit", "approval", "authorization", "schedule", "policy",
        "amendment", "blueprint", "taskset-release", "output",
    ):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    audit = load(args.source_audit)
    approval = load(args.approval)
    authorization = load(args.authorization)
    schedule = load(args.schedule)
    policy = load(args.policy)
    amendment = load(args.amendment)
    blueprint = load(args.blueprint)
    taskset = load(args.taskset_release)
    if not audit.get("eligible", False):
        raise ValueError("source-extension audit is ineligible")
    identities = audit["protected_identities"]
    item = ExecutionToolingBinding(
        binding_name="dc3pa-round510-execution-tooling-v1",
        approved_by=str(approval["approved_by"]),
        approval_record_id=str(approval["approval_record_id"]),
        source_extension_audit_sha256=sha(args.source_audit),
        parent_source_commit=str(audit["parent_source_commit"]),
        new_source_commit=str(audit["new_source_commit"]),
        parent_formal_authorization_id=str(authorization["authorization_id"]),
        bootstrap_policy_id=str(policy["policy_id"]),
        bootstrap_amendment_id=str(amendment["amendment_id"]),
        blueprint_id=str(blueprint["blueprint_id"]),
        acquisition_schedule_id=str(schedule["schedule_id"]),
        taskset_release_id=str(taskset["release_id"]),
        prompt_hash_bundle_id_before=identities["prompt_hash_bundle"]["before"],
        prompt_hash_bundle_id_after=identities["prompt_hash_bundle"]["after"],
        controller_identity_sha256_before=identities["controller"]["before"],
        controller_identity_sha256_after=identities["controller"]["after"],
        evaluator_identity_sha256_before=identities["evaluator"]["before"],
        evaluator_identity_sha256_after=identities["evaluator"]["after"],
        task_catalog_sha256_before=identities["task_catalog"]["before"],
        task_catalog_sha256_after=identities["task_catalog"]["after"],
        allowed_change_classes=tuple(sorted(ALLOWED_CHANGE_CLASSES)),
        prompts_changed=False,
        controller_behavior_changed=False,
        evaluator_behavior_changed=False,
        task_catalog_changed=False,
        seeds_or_schedule_changed=False,
        bootstrap_policy_changed=False,
        formal_acquisition_started_before_binding=bool(
            approval["formal_acquisition_started_before_binding"]
        ),
    ).with_id()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(item.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(item.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
