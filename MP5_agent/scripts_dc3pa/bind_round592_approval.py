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
from dc3pa.experiments.provider_model_alias import (
    load_provider_model_alias_policy,
    sha256_file as sha256_alias_approval,
)


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
    parser.add_argument("--provider-model-alias-policy")
    parser.add_argument("--provider-model-alias-approval")
    parser.add_argument("--controller-revision")
    parser.add_argument("--log-fallback-policy")
    parser.add_argument("--log-fallback-approval")
    parser.add_argument("--natural-readiness-campaign")
    parser.add_argument("--paired-dry-run-protocol")
    args = parser.parse_args()
    alias_arguments = (
        args.provider_model_alias_policy,
        args.provider_model_alias_approval,
    )
    if any(alias_arguments) and not all(alias_arguments):
        parser.error(
            "model aliasing requires --provider-model-alias-policy and "
            "--provider-model-alias-approval"
        )
    alias_policy = (
        load_provider_model_alias_policy(
            args.provider_model_alias_policy,
            approval_record=args.provider_model_alias_approval,
        )
        if all(alias_arguments)
        else None
    )
    round593_arguments = (
        args.controller_revision,
        args.log_fallback_policy,
        args.log_fallback_approval,
        args.natural_readiness_campaign,
        args.paired_dry_run_protocol,
    )
    if any(round593_arguments) and not all(round593_arguments):
        parser.error(
            "Round 5.9.3 binding requires Controller revision, Log Fallback "
            "policy/approval, natural campaign and paired protocol"
        )

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
    if amendment.get("source_commit") != blueprint.source_commit and not all(
        round593_arguments
    ):
        raise ValueError("Author amendment/Blueprint source commit mismatch")
    revision = load(args.controller_revision) if all(round593_arguments) else None
    fallback_policy = load(args.log_fallback_policy) if revision else None
    natural_campaign = load(args.natural_readiness_campaign) if revision else None
    paired_protocol = load(args.paired_dry_run_protocol) if revision else None
    if revision:
        if revision.get("source_commit") != blueprint.source_commit:
            raise ValueError("Controller revision/Blueprint source commit mismatch")
        if fallback_policy.get("policy_id") != revision.get("fallback_policy_id"):
            raise ValueError("Controller revision/Log Fallback policy mismatch")
        if sha256_file(args.log_fallback_approval) != revision.get(
            "fallback_approval_sha256"
        ):
            raise ValueError("Controller revision/Log Fallback approval mismatch")
        if natural_campaign.get("source_commit") != blueprint.source_commit:
            raise ValueError("Natural campaign/Blueprint source commit mismatch")
        if natural_campaign.get("campaign_kind") != "natural_readiness":
            raise ValueError("Readiness campaign must be natural")
        if paired_protocol.get("source_commit") != blueprint.source_commit:
            raise ValueError("Paired protocol/Blueprint source commit mismatch")
        if paired_protocol.get("natural_campaign_id") != natural_campaign.get(
            "campaign_id"
        ):
            raise ValueError("Paired protocol/natural campaign mismatch")
        if paired_protocol.get("fallback_policy_id") != fallback_policy.get(
            "policy_id"
        ):
            raise ValueError("Paired protocol/Log Fallback policy mismatch")

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
        provider_model_alias_policy_id=(
            alias_policy.policy_id if alias_policy is not None else ""
        ),
        provider_model_alias_approval_sha256=(
            sha256_alias_approval(args.provider_model_alias_approval)
            if alias_policy is not None
            else ""
        ),
        returned_model_identity_match_required=alias_policy is None,
        experiment_approval_record_id=(
            blueprint.author_approval.approval_record_id if revision else ""
        ),
        controller_revision_id=(str(revision["revision_id"]) if revision else ""),
        log_fallback_policy_id=(
            str(fallback_policy["policy_id"]) if revision else ""
        ),
        log_fallback_approval_sha256=(
            sha256_file(args.log_fallback_approval) if revision else ""
        ),
        fallback_allowed_scopes=(
            tuple(revision["fallback_allowed_scopes"]) if revision else ()
        ),
        fallback_forbidden_scopes=(
            tuple(revision["fallback_forbidden_scopes"]) if revision else ()
        ),
        natural_readiness_campaign_id=(
            str(natural_campaign["campaign_id"]) if revision else ""
        ),
        paired_dry_run_protocol_id=(
            str(paired_protocol["protocol_id"]) if revision else ""
        ),
        fallback_assisted_runs_excluded_from_readiness=bool(revision),
        fallback_assisted_runs_excluded_from_paper_performance=bool(revision),
    ).with_id()
    save_immutable(args.output, binding.to_dict())
    print(json.dumps(binding.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
