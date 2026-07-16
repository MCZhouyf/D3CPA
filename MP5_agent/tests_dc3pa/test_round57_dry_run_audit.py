from __future__ import annotations

import pytest

from dc3pa.experiments.dry_run import DryRunReceipt, audit_dry_run, build_dry_run_campaign
from dc3pa.experiments.dry_run import (
    ensure_not_dry_run_artifact_path,
    mark_dry_run_output_root,
)
from tests_dc3pa.round56_helpers import make_blueprint


def _campaign():
    return build_dry_run_campaign(
        blueprint=make_blueprint(),
        selected_group_ids=["train"],
        source_commit="commit",
        require_confidence_observations=True,
        require_execution_label_joins=True,
    )


def test_task_failure_does_not_fail_pipeline_audit():
    campaign = _campaign()
    entry = campaign.entries[0]
    receipt = DryRunReceipt(
        campaign_id=campaign.campaign_id,
        entry_id=entry.entry_id,
        status="pipeline_pass",
        process_exit_code=0,
        launch_validation_passed=True,
        controller_started=True,
        telemetry_event_count=10,
        stable_step_identity_count=2,
        confidence_observation_count=2,
        execution_label_join_count=1,
        censored_excluded_count=1,
        ambiguous_excluded_count=0,
        technical_failure_count=0,
        inline_rgb_detected=False,
        secret_scan_passed=True,
        excluded_from_formal_fitting=True,
        formal_memory_used=False,
        output_manifest_sha256="hash",
        task_completed=False,
        fallback_metrics={
            "natural_completion": False,
            "fallback_assisted_completion": False,
            "fallback_trigger_count": 0,
            "total_injected_logs": 0,
        },
    )
    report = audit_dry_run(campaign, [receipt])
    assert report.eligible
    assert report.warnings


def test_controller_fallback_is_reported_separately_from_pipeline_status():
    campaign = _campaign()
    entry = campaign.entries[0]
    receipt = DryRunReceipt(
        campaign_id=campaign.campaign_id,
        entry_id=entry.entry_id,
        status="pipeline_pass",
        process_exit_code=0,
        launch_validation_passed=True,
        controller_started=True,
        telemetry_event_count=10,
        stable_step_identity_count=2,
        confidence_observation_count=2,
        execution_label_join_count=1,
        censored_excluded_count=0,
        ambiguous_excluded_count=0,
        technical_failure_count=0,
        inline_rgb_detected=False,
        secret_scan_passed=True,
        excluded_from_formal_fitting=True,
        formal_memory_used=False,
        output_manifest_sha256="hash",
        task_completed=True,
        fallback_metrics={
            "natural_completion": False,
            "fallback_assisted_completion": True,
            "fallback_trigger_count": 1,
            "total_injected_logs": 3,
        },
    )

    report = audit_dry_run(campaign, [receipt])

    assert report.eligible
    assert report.summary["fallback_trigger_count"] == 1
    assert report.summary["fallback_assisted_completion_count"] == 1
    assert report.summary["total_injected_logs"] == 3


def test_formal_memory_or_formal_inclusion_fails_audit():
    campaign = _campaign()
    entry = campaign.entries[0]
    receipt = DryRunReceipt(
        campaign_id=campaign.campaign_id,
        entry_id=entry.entry_id,
        status="pipeline_pass",
        process_exit_code=0,
        launch_validation_passed=True,
        controller_started=True,
        telemetry_event_count=1,
        stable_step_identity_count=1,
        confidence_observation_count=1,
        execution_label_join_count=1,
        censored_excluded_count=0,
        ambiguous_excluded_count=0,
        technical_failure_count=0,
        inline_rgb_detected=False,
        secret_scan_passed=True,
        excluded_from_formal_fitting=False,
        formal_memory_used=True,
        output_manifest_sha256="hash",
        task_completed=True,
        fallback_metrics={
            "natural_completion": True,
            "fallback_assisted_completion": False,
            "fallback_trigger_count": 0,
            "total_injected_logs": 0,
        },
    )
    assert not audit_dry_run(campaign, [receipt]).eligible


def test_formal_input_guard_rejects_marked_dry_run_root(tmp_path):
    root = mark_dry_run_output_root(
        tmp_path / "dry-run",
        campaign_id="campaign",
        entry_id="entry",
    )
    dataset = root / "dataset.jsonl"
    dataset.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="dry-run artifact root"):
        ensure_not_dry_run_artifact_path(dataset, label="dataset")
