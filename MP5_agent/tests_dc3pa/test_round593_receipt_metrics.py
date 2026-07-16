from dc3pa.experiments.dry_run import (
    DryRunCampaign,
    DryRunCampaignEntry,
    receipt_from_stage6_result,
)
from dc3pa.experiments.log_fallback import (
    LogFallbackEvent,
    LogFallbackPolicy,
    receipt_metrics_from_events,
)


def fallback_event():
    return LogFallbackEvent(
        fallback_kind="log_inventory_injection",
        scope="diagnostic_dry_run",
        policy_id="policy",
        inventory_before=0,
        inventory_target=4,
        inventory_after=4,
        naturally_collected_count=0,
        injected_count=4,
        natural_collection_attempts=3,
        bounded_attempts_exhausted=True,
        triggered=True,
        source_commit="commit",
        task="crafting table",
        seed="1",
    ).with_id()


def test_fallback_completion_is_not_natural_completion():
    policy = LogFallbackPolicy().with_id()
    metrics = receipt_metrics_from_events(
        policy=policy,
        enabled=True,
        events=[fallback_event()],
        task_completed=True,
        planner_calls=1,
        reflection_calls=0,
        evaluation_chain_calls=0,
    )
    assert metrics.fallback_assisted_completion
    assert not metrics.natural_completion
    assert metrics.total_injected_logs == 4


def test_natural_completion_has_no_fallback():
    policy = LogFallbackPolicy().with_id()
    metrics = receipt_metrics_from_events(
        policy=policy,
        enabled=False,
        events=[],
        task_completed=True,
        planner_calls=1,
        reflection_calls=0,
        evaluation_chain_calls=0,
    )
    assert metrics.natural_completion
    assert not metrics.fallback_assisted_completion


def test_receipt_binds_approved_provider_model_alias_policy(tmp_path):
    entry = DryRunCampaignEntry(
        entry_id="entry",
        group_id="group",
        task="craft crafting table",
        seed="1",
        maximum_high_level_steps=10,
        maximum_llm_calls=2,
        maximum_replans=0,
        timeout_seconds=60,
        launch_trace={},
    )
    campaign = DryRunCampaign(
        campaign_name="diagnostic",
        blueprint_id="blueprint",
        source_commit="commit",
        entries=(entry,),
        require_confidence_observations=False,
        require_execution_label_joins=False,
    ).with_id()

    receipt = receipt_from_stage6_result(
        campaign=campaign,
        entry_id=entry.entry_id,
        result=None,
        output_root=tmp_path / "output",
        process_exit_code=0,
        launch_validation_passed=True,
        formal_memory_used=False,
        truth_evidence={"provider_model_alias_policy_id": "policy-id"},
    )

    assert (
        receipt.metadata["provider_model_identity_validation"]
        == "approved_alias_policy"
    )
    assert receipt.metadata["provider_model_alias_policy_id"] == "policy-id"
