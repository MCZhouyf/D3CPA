import pytest

from dc3pa.experiments.paired_dry_run import (
    build_paired_protocol,
    summarize_receipts,
)


def campaign(campaign_id, seed="1"):
    return {
        "campaign_id": campaign_id,
        "entries": [
            {
                "entry_id": "entry",
                "group_id": "group",
                "task": "crafting table",
                "seed": seed,
                "maximum_high_level_steps": 60,
                "maximum_llm_calls": 30,
                "maximum_replans": 3,
            }
        ],
    }


def test_paired_protocol_requires_identical_entries():
    item = build_paired_protocol(
        protocol_name="pair",
        source_commit="commit",
        blueprint_id="blueprint",
        model_profile_id="profile",
        prompt_hash_bundle_id="prompts",
        natural_campaign=campaign("natural"),
        diagnostic_campaign=campaign("diagnostic"),
        fallback_policy_id="policy",
    )
    assert item.protocol_id

    with pytest.raises(ValueError):
        build_paired_protocol(
            protocol_name="pair",
            source_commit="commit",
            blueprint_id="blueprint",
            model_profile_id="profile",
            prompt_hash_bundle_id="prompts",
            natural_campaign=campaign("natural", seed="1"),
            diagnostic_campaign=campaign("diagnostic", seed="2"),
            fallback_policy_id="policy",
        )


def test_summary_separates_natural_and_assisted_completion():
    payload = {
        "campaign_id": "diagnostic",
        "entry_id": "entry",
        "status": "pipeline_pass",
        "fallback_metrics": {
            "task_completed": True,
            "natural_completion": False,
            "fallback_assisted_completion": True,
            "fallback_trigger_count": 1,
            "total_injected_logs": 4,
            "planner_calls": 1,
            "reflection_calls": 0,
            "evaluation_chain_calls": 0,
        },
    }
    summary = summarize_receipts(
        campaign_id="diagnostic",
        campaign_kind="fallback_diagnostic",
        receipt_payloads=[payload],
    )
    assert summary.task_completed_count == 1
    assert summary.natural_completion_count == 0
    assert summary.fallback_assisted_completion_count == 1
