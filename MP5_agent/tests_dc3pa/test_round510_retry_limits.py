from datetime import datetime, timedelta, timezone

import pytest

from dc3pa.experiments.formal_acquisition_execution import (
    EntryAttemptLedger,
    FormalAcquisitionAttempt,
    TechnicalRetryPolicy,
    deterministic_attempt_id,
)


NOW = datetime.now(timezone.utc)


def technical(index, retry_of):
    return FormalAcquisitionAttempt(
        attempt_id=deterministic_attempt_id("campaign", 0, index),
        stage6_receipt_id="",
        campaign_id="campaign",
        schedule_id="schedule",
        formal_authorization_id="authorization",
        execution_tooling_binding_id="tooling",
        episode_index=0,
        group_id="group",
        task="task",
        seed="1",
        difficulty="basic",
        method_id="single_chain_reactive_acquisition",
        attempt_index=index,
        retry_of_attempt_id=retry_of,
        source_commit="commit",
        blueprint_id="blueprint",
        bootstrap_policy_id="policy",
        bootstrap_amendment_id="amendment",
        bootstrap_data_binding_id="binding",
        prompt_hash_bundle_id="prompts",
        model_profile_id="profile",
        requested_model="gpt-5.1",
        returned_model_identities=("returned",),
        started_at=NOW.isoformat(),
        finished_at=(NOW + timedelta(seconds=index + 1)).isoformat(),
        status="technical_failure",
        failure_category="process_crash",
        failure_detail="crash",
        pipeline_pass=False,
        task_completed=False,
        planner_calls=0,
        reflection_calls=0,
        evaluation_chain_calls=0,
        controller_execution_count=0,
        bootstrap_event_ids=(),
        intervention_trigger_count=0,
        injected_log_count=0,
        naturally_collected_log_count=0,
        natural_completion=False,
        bootstrap_assisted_completion=False,
        acquisition_record_path="",
        acquisition_record_sha256="",
        trace_sha256=f"trace-{index}",
        formal_memory_write_count=0,
        acquisition_write_count=0,
        secret_scan_passed=True,
        inline_rgb_detected=False,
    ).with_id()


def test_at_most_two_technical_retries():
    policy = TechnicalRetryPolicy().with_id()
    ledger = EntryAttemptLedger(
        campaign_id="campaign",
        schedule_id="schedule",
        episode_index=0,
        group_id="group",
        task="task",
        seed="1",
        retry_policy_id=policy.policy_id,
    ).with_id()
    first = technical(0, "")
    second = technical(1, first.attempt_id)
    third = technical(2, second.attempt_id)
    ledger = ledger.append(first, retry_policy=policy)
    ledger = ledger.append(second, retry_policy=policy)
    ledger = ledger.append(third, retry_policy=policy)
    with pytest.raises(ValueError):
        ledger.append(technical(3, third.attempt_id), retry_policy=policy)


def test_retry_cannot_change_source_commit():
    policy = TechnicalRetryPolicy().with_id()
    ledger = EntryAttemptLedger(
        campaign_id="campaign",
        schedule_id="schedule",
        episode_index=0,
        group_id="group",
        task="task",
        seed="1",
        retry_policy_id=policy.policy_id,
        attempts=(technical(0, ""),),
    ).with_id()
    changed = technical(1, ledger.attempts[0].attempt_id)
    object.__setattr__(changed, "source_commit", "other")
    with pytest.raises(ValueError):
        ledger.append(changed, retry_policy=policy)
