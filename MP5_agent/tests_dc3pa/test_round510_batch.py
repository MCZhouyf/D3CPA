from dc3pa.experiments.formal_acquisition_batch import plan_batch
from dc3pa.experiments.formal_acquisition_execution import (
    EntryAttemptLedger,
    FormalAcquisitionCampaign,
    TechnicalRetryPolicy,
)


def setup():
    retry = TechnicalRetryPolicy().with_id()
    campaign = FormalAcquisitionCampaign(
        campaign_name="formal",
        source_commit="commit",
        blueprint_id="blueprint",
        formal_authorization_id="authorization",
        execution_tooling_binding_id="tooling",
        schedule_id="schedule",
        bootstrap_policy_id="policy",
        bootstrap_amendment_id="amendment",
        bootstrap_data_binding_id="binding",
        model_profile_id="profile",
        prompt_hash_bundle_id="prompts",
        controller_identity_sha256="controller",
        evaluator_identity_sha256="evaluator",
        retry_policy_id=retry.policy_id,
    ).with_id()
    schedule = {
        "schedule_id": "schedule",
        "entries": [
            {
                "episode_index": i,
                "group_id": f"g{i}",
                "task": f"t{i}",
                "seed": str(i),
                "difficulty": "basic",
            }
            for i in range(100)
        ],
    }
    ledgers = [
        EntryAttemptLedger(
            campaign_id=campaign.campaign_id,
            schedule_id="schedule",
            episode_index=i,
            group_id=f"g{i}",
            task=f"t{i}",
            seed=str(i),
            retry_policy_id=retry.policy_id,
        ).with_id()
        for i in range(100)
    ]
    return retry, campaign, schedule, ledgers


def test_first_batch_contains_fixed_first_ten_entries():
    retry, campaign, schedule, ledgers = setup()
    result = plan_batch(
        campaign=campaign,
        schedule=schedule,
        ledgers=ledgers,
        retry_policy=retry,
        batch_index=0,
    )
    assert [item.episode_index for item in result.requests] == list(range(10))
    assert result.first_episode_index == 0
    assert result.last_episode_index == 9
