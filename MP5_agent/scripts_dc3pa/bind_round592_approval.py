#!/usr/bin/env python3
"""Freeze the ZYF Round 5.9.2 approval binding outside Git."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.blueprint import load_blueprint, sha256_file
from dc3pa.experiments.final_taskset_release import (
    load_taskset_release,
    save_immutable,
)
from dc3pa.experiments.round592_approval import Round592ApprovalBinding


def load(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "author-amendment", "blueprint", "final-taskset-release",
        "task-semantic-smoke", "task-asset-validation", "migration-report",
        "schema-v2-design", "prompt-identity", "controller-source",
        "controller-config", "evaluator-source", "evaluator-config",
        "schedule-salt", "output",
    ):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()

    amendment = load(args.author_amendment)
    blueprint = load_blueprint(args.blueprint)
    release = load_taskset_release(args.final_taskset_release)
    smoke = load(args.task_semantic_smoke)
    tasks = load(args.task_asset_validation)
    migration = load(args.migration_report)
    design = load(args.schema_v2_design)
    prompts = load(args.prompt_identity)
    if amendment.get("approved_by") != "ZYF":
        raise ValueError("Taskset amendment is not ZYF approved")
    if amendment.get("source_commit") != blueprint.source_commit:
        raise ValueError("Author amendment/Blueprint source commit mismatch")

    binding = Round592ApprovalBinding(
        approval_record_id=str(amendment["approval_record_id"]),
        approved_by="ZYF",
        approved_at=str(amendment["approval_effective_date"]),
        source_commit=blueprint.source_commit,
        blueprint_id=blueprint.blueprint_id,
        approved_blueprint_content_sha256=(
            blueprint.author_approval.approved_blueprint_content_sha256
        ),
        final_taskset_release_id=release.release_id,
        taskset_amendment_id=release.amendment_id,
        task_semantic_smoke_report_id=str(smoke["report_id"]),
        task_asset_validation_report_id=str(tasks["report_id"]),
        runtime_task_tree_sha256=str(tasks["runtime_task_tree_sha256"]),
        semantic_migration_report_id=str(migration["report_id"]),
        schema_v2_design_id=str(design["design_id"]),
        prompt_hashes=dict(prompts["prompt_hashes"]),
        controller_source_sha256=sha256_file(args.controller_source),
        controller_config_sha256=sha256_file(args.controller_config),
        evaluator_source_sha256=sha256_file(args.evaluator_source),
        evaluator_config_sha256=sha256_file(args.evaluator_config),
        model_id="gpt-5.1",
        reasoning_effort="low",
        mutable_alias_risk_acknowledged=True,
        maximum_model_epoch_hours=12.0,
        model_epoch_policy_version="round592-12h-v1",
        execution_schedule_policy_version="round592-block-interleaved-v1",
        execution_schedule_salt=args.schedule_salt,
    ).with_id()
    save_immutable(args.output, binding.to_dict())
    print(json.dumps(binding.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
