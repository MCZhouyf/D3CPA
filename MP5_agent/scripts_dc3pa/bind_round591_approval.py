#!/usr/bin/env python3
"""Create an immutable ZYF Round 5.9.1 approval binding outside Git."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.design_migration import Round59ApprovalBinding, load_json
from dc3pa.experiments.model_epoch import save_immutable


def pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Use NAME=SHA256")
    name, digest = value.split("=", 1)
    if not name.strip() or len(digest.strip()) != 64:
        raise argparse.ArgumentTypeError("Prompt hash must use NAME=64_HEX")
    return name.strip(), digest.strip().lower()


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "author-approval", "blueprint-id", "approved-content-sha256",
        "migration-report", "reference-design-id", "controller-source",
        "evaluator-source", "task-validation-report", "schedule-salt", "output",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--prompt-hash", action="append", type=pair, required=True)
    args = parser.parse_args()

    approval = load_json(args.author_approval)
    migration = load_json(args.migration_report)
    tasks = load_json(args.task_validation_report)
    if approval.get("author_team") != "ZYF":
        raise SystemExit("Author approval is not from ZYF")
    if approval.get("approval_record_id") != "DC3PA-V2-ZYF-20260715-001":
        raise SystemExit("Unexpected ZYF approval record")
    if not migration.get("eligible"):
        raise SystemExit("Migration report is not eligible")
    if not tasks.get("eligible"):
        raise SystemExit("Task-asset validation is not eligible")
    policy = approval.get("model_policy", {})
    binding = Round59ApprovalBinding(
        blueprint_id=args.blueprint_id,
        approval_record_id=approval["approval_record_id"],
        approved_blueprint_content_sha256=args.approved_content_sha256,
        migration_report_id=str(migration.get("report_id", "")),
        reference_design_id=args.reference_design_id,
        mutable_alias_risk_acknowledged=bool(policy.get("mutable_alias_approved")),
        model_epoch_policy_version="round591-12h-v1",
        interleaved_schedule_policy_version="round591-block-interleaved-v1",
        interleaved_schedule_salt=args.schedule_salt,
        author_team="ZYF",
        source_commit=str(approval.get("source_commit", "")),
        model_id=str(policy.get("model", "")),
        reasoning_effort=str(policy.get("reasoning_effort", "")),
        maximum_model_epoch_hours=12.0,
        prompt_hashes=dict(args.prompt_hash),
        controller_source_sha256=sha256_file(args.controller_source),
        evaluator_source_sha256=sha256_file(args.evaluator_source),
        task_asset_validation_report_id=str(tasks.get("report_id", "")),
        runtime_task_tree_sha256=str(tasks.get("runtime_task_tree_sha256", "")),
    ).with_id()
    save_immutable(args.output, binding.to_dict())
    print(json.dumps(binding.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
