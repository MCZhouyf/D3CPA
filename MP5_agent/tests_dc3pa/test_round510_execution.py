from datetime import datetime, timezone, timedelta
import pytest

from dc3pa.experiments.formal_acquisition_execution import (
    EntryAttemptLedger,
    FormalAcquisitionAttempt,
    TechnicalRetryPolicy,
    deterministic_attempt_id,
)


NOW = datetime.now(timezone.utc)


def attempt(
    *,
    attempt_index=0,
    attempt_id=None,
    retry_of="",
    status="technical_failure",
    failure_category="process_crash",
    task_completed=False,
    pipeline_pass=False,
    acquisition_path="",
    acquisition_sha="",
    acquisition_writes=0,
):
    effective_id = attempt_id or deterministic_attempt_id(
        "campaign", 0, attempt_index
    )
    return FormalAcquisitionAttempt(
        attempt_id=effective_id,
        stage6_receipt_id=f"stage6-{attempt_index}",
        campaign_id="campaign",
        schedule_id="schedule",
        formal_authorization_id="authorization",
        execution_tooling_binding_id="tooling",
        episode_index=0,
        group_id="group",
        task="craft chest",
        seed="1",
        difficulty="easy",
        method_id="single_chain_reactive_acquisition",
        attempt_index=attempt_index,
        retry_of_attempt_id=retry_of,
        source_commit="commit",
        blueprint_id="blueprint",
        bootstrap_policy_id="policy",
        bootstrap_amendment_id="amendment",
        bootstrap_data_binding_id="binding",
        prompt_hash_bundle_id="prompts",
        model_profile_id="profile",
        requested_model="gpt-5.1",
        returned_model_identities=("provider-returned-id",),
        started_at=NOW.isoformat(),
        finished_at=(NOW + timedelta(seconds=1)).isoformat(),
        status=status,
        failure_category=failure_category,
        failure_detail="detail" if failure_category else "",
        pipeline_pass=pipeline_pass,
        task_completed=task_completed,
        planner_calls=1,
        reflection_calls=0 if task_completed else 1,
        evaluation_chain_calls=0,
        controller_execution_count=1,
        bootstrap_event_ids=("event",),
        intervention_trigger_count=1,
        injected_log_count=2,
        naturally_collected_log_count=1,
        natural_completion=False,
        bootstrap_assisted_completion=task_completed,
        acquisition_record_path=acquisition_path,
        acquisition_record_sha256=acquisition_sha,
        trace_sha256="trace",
        formal_memory_write_count=0,
        acquisition_write_count=acquisition_writes,
        secret_scan_passed=True,
        inline_rgb_detected=False,
    ).with_id()


def ledger():
    return EntryAttemptLedger(
        campaign_id="campaign",
        schedule_id="schedule",
        episode_index=0,
        group_id="group",
        task="craft chest",
        seed="1",
        retry_policy_id=TechnicalRetryPolicy().with_id().policy_id,
    ).with_id()


def test_technical_failure_can_retry_then_success():
    policy = TechnicalRetryPolicy().with_id()
    first = attempt()
    item = ledger().append(first, retry_policy=policy)
    success = attempt(
        attempt_index=1,
        retry_of=deterministic_attempt_id("campaign", 0, 0),
        status="completed_success",
        failure_category="",
        task_completed=True,
        pipeline_pass=True,
        acquisition_path="episodes/a1.json",
        acquisition_sha="sha",
        acquisition_writes=1,
    )
    item = item.append(success, retry_policy=policy)
    assert item.resolved
    assert item.final_attempt.attempt_id == deterministic_attempt_id("campaign", 0, 1)


def test_scientific_failure_is_final_and_not_retryable():
    policy = TechnicalRetryPolicy().with_id()
    scientific = attempt(
        status="completed_scientific_failure",
        failure_category="planner_failure",
        pipeline_pass=True,
    )
    item = ledger().append(scientific, retry_policy=policy)
    assert item.resolved
    with pytest.raises(ValueError):
        item.append(
            attempt(
                attempt_index=1,
                retry_of=deterministic_attempt_id("campaign", 0, 0),
            ),
            retry_policy=policy,
        )


def test_returned_identity_is_recorded_but_need_not_equal_requested():
    item = attempt()
    assert item.requested_model == "gpt-5.1"
    assert item.returned_model_identities == ("provider-returned-id",)


def test_technical_failure_can_precede_model_or_trace_creation():
    item = attempt()
    object.__setattr__(item, "returned_model_identities", ())
    object.__setattr__(item, "trace_sha256", "")
    object.__setattr__(item, "receipt_id", "")
    rebuilt = item.with_id()
    assert rebuilt.status == "technical_failure"
