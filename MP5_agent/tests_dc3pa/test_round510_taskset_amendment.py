import csv
from io import StringIO

import pytest

from dc3pa.experiments.round510_taskset_amendment import (
    Round510TasksetAmendment,
    validate_catalog_replacement,
)
from dc3pa.experiments.formal_acquisition_execution import (
    FormalAcquisitionCampaign,
    TechnicalRetryPolicy,
)


def _amendment():
    return Round510TasksetAmendment(
        approval_record_id="DC3PA-ZYF-R510-TASKSET-007",
        approved_by="ZYF",
        approved_at="2026-07-16",
        source_commit="a" * 40,
        prior_taskset_release_id="prior-release",
        superseded_campaign_id="prior-campaign",
        removed_task="mine sand",
        added_task="craft wooden pressure plate",
        replacement_difficulty="basic",
        creative_payload_sha256="b" * 64,
        formal_task_spec_sha256="c" * 64,
        acquisition_seeds_reused=True,
        acquisition_order_preserved=True,
        prior_campaign_results_excluded=True,
        before_restarted_formal_acquisition=True,
        outcome_selected=False,
        reason="Author-directed task replacement.",
    ).with_id()


def test_round510_taskset_amendment_is_deterministic():
    item = _amendment()
    assert item.amendment_id == item.compute_amendment_id()


def test_round510_taskset_amendment_rejects_outcome_selection():
    payload = _amendment().payload_without_id()
    payload["outcome_selected"] = True
    with pytest.raises(ValueError, match="outcome tuning"):
        Round510TasksetAmendment(**payload)


def test_catalog_replacement_is_exact_and_preserves_basic_slot():
    rows = [
        {"task": f"basic {index}", "difficulty": "basic", "minimum_subgoals": "1"}
        for index in range(10)
    ]
    rows += [
        {"task": f"{difficulty} {index}", "difficulty": difficulty, "minimum_subgoals": "2"}
        for difficulty in ("easy", "medium", "hard", "complex")
        for index in range(10)
    ]
    rows[1] = {
        "task": "mine sand",
        "difficulty": "basic",
        "minimum_subgoals": "1",
    }
    amended = [dict(row) for row in rows]
    amended[1] = {
        "task": "craft wooden pressure plate",
        "difficulty": "basic",
        "minimum_subgoals": "3",
    }
    assert validate_catalog_replacement(rows, amended) == ()


def test_catalog_replacement_rejects_second_change():
    text = "task,difficulty,minimum_subgoals\nmine sand,basic,1\n"
    prior = list(csv.DictReader(StringIO(text)))
    amended = [
        {
            "task": "craft wooden pressure plate",
            "difficulty": "basic",
            "minimum_subgoals": "3",
        }
    ]
    assert "50 rows" in validate_catalog_replacement(prior, amended)[0]


def test_campaign_serialization_adds_binding_without_changing_legacy_payload():
    retry = TechnicalRetryPolicy().with_id()
    kwargs = {
        "campaign_name": "formal",
        "source_commit": "commit",
        "blueprint_id": "blueprint",
        "formal_authorization_id": "authorization",
        "execution_tooling_binding_id": "tooling",
        "schedule_id": "schedule",
        "bootstrap_policy_id": "policy",
        "bootstrap_amendment_id": "amendment",
        "bootstrap_data_binding_id": "binding",
        "model_profile_id": "profile",
        "prompt_hash_bundle_id": "prompts",
        "controller_identity_sha256": "controller",
        "evaluator_identity_sha256": "evaluator",
        "retry_policy_id": retry.policy_id,
    }
    legacy = FormalAcquisitionCampaign(**kwargs).with_id()
    amended = FormalAcquisitionCampaign(
        **kwargs, taskset_amendment_id="taskset-v2"
    ).with_id()
    assert "taskset_amendment_id" not in legacy.to_dict()
    assert amended.to_dict()["taskset_amendment_id"] == "taskset-v2"
    assert amended.campaign_id != legacy.campaign_id
