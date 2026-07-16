#!/usr/bin/env python3
"""Validate every Round 5.9.2 Blueprint and approval binding."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.blueprint import load_blueprint
from dc3pa.experiments.final_taskset_release import (
    load_taskset_release,
    save_immutable,
)
from dc3pa.experiments.round592_approval import (
    load_round592_approval,
    validate_round592_blueprint,
)


def load(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "blueprint", "approval-binding", "final-taskset-release",
        "migration-report", "task-asset-validation", "task-semantic-smoke",
        "schema-v2-design", "prompt-identity", "controller-source",
        "controller-config", "evaluator-source", "evaluator-config", "output",
    ):
        parser.add_argument("--" + name, required=True)
    for name in (
        "controller-revision", "log-fallback-policy",
        "natural-readiness-campaign", "paired-dry-run-protocol",
    ):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    round593_paths = (
        args.controller_revision,
        args.log_fallback_policy,
        args.natural_readiness_campaign,
        args.paired_dry_run_protocol,
    )
    if any(round593_paths) and not all(round593_paths):
        parser.error("Round 5.9.3 Blueprint validation inputs must be complete")
    report = validate_round592_blueprint(
        blueprint=load_blueprint(args.blueprint),
        binding=load_round592_approval(args.approval_binding),
        final_taskset=load_taskset_release(args.final_taskset_release),
        migration_report=load(args.migration_report),
        task_asset_validation=load(args.task_asset_validation),
        semantic_smoke=load(args.task_semantic_smoke),
        schema_v2_design=load(args.schema_v2_design),
        prompt_identity=load(args.prompt_identity),
        controller_source=args.controller_source,
        controller_config=args.controller_config,
        evaluator_source=args.evaluator_source,
        evaluator_config=args.evaluator_config,
        controller_revision=(
            load(args.controller_revision) if all(round593_paths) else None
        ),
        log_fallback_policy=(
            load(args.log_fallback_policy) if all(round593_paths) else None
        ),
        natural_readiness_campaign=(
            load(args.natural_readiness_campaign) if all(round593_paths) else None
        ),
        paired_dry_run_protocol=(
            load(args.paired_dry_run_protocol) if all(round593_paths) else None
        ),
    )
    save_immutable(args.output, report.to_dict())
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
