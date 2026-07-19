import json
import os
from pathlib import Path

import pytest

from dc3pa.experiments.round5122_pathb import (
    ASSIGNMENT_MANIFEST_ID,
    CompleteExecutionBudgetContract,
    FreshDevelopmentCampaignAuthorization,
    PathBRemediationApproval,
    canonical_assignment_manifest_id,
    fresh_campaign_id,
    initialize_fresh_campaign_root,
    persist_complete_budget_contract,
    validate_campaign_authorization,
    validate_fresh_assignments,
)
from scripts_dc3pa import run_round511_development_campaign as campaign_runner


def test_old_frozen_60_assignment_manifest_matches_exactly():
    configured = os.environ.get("DC3PA_ROUND511_ASSIGNMENTS", "")
    if not configured:
        pytest.skip("Immutable external development manifest is not mounted")
    path = Path(configured)
    if not path.is_file():
        pytest.skip("Immutable external development manifest is not mounted")
    assignments = json.loads(path.read_text(encoding="utf-8"))["assignments"]
    validate_fresh_assignments(assignments)
    assert canonical_assignment_manifest_id(assignments) == ASSIGNMENT_MANIFEST_ID


def test_frozen_assignments_initialize_exactly_60_empty_ledgers(tmp_path):
    configured = os.environ.get("DC3PA_ROUND511_ASSIGNMENTS", "")
    if not configured:
        pytest.skip("Immutable external development manifest is not mounted")
    assignments = json.loads(Path(configured).read_text(encoding="utf-8"))["assignments"]
    budget, approval, authorization = _contracts()
    root = tmp_path / "fresh-campaign"
    initialize_fresh_campaign_root(
        output_root=root,
        approval=approval,
        authorization=authorization,
        budget=budget,
        assignments=assignments,
    )
    assert len(list((root / "runs").iterdir())) == 60
    assert all(not list(path.iterdir()) for path in (root / "runs").iterdir())
    validate_campaign_authorization(
        approval=approval,
        authorization=authorization,
        budget=budget,
        assignments=assignments,
        current_source_sha="a" * 40,
        output_root=root,
    )
    ledger = next((root / "runs").iterdir())
    attempt = ledger / "attempt-0"
    attempt.mkdir()
    (attempt / "run_binding.json").write_text(
        json.dumps(
            {
                "collection_id": "old-campaign",
                "fresh_campaign_authorization_id": "",
                "path_b_approval_id": "",
                "source_commit": "b" * 40,
                "execution_budget_snapshot_id": "old-budget",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Old campaign attempt import"):
        validate_campaign_authorization(
            approval=approval,
            authorization=authorization,
            budget=budget,
            assignments=assignments,
            current_source_sha="a" * 40,
            output_root=root,
        )


def test_complete_budget_rejects_missing_author_timeout_decision():
    with pytest.raises(ValueError, match="author timeout decision"):
        CompleteExecutionBudgetContract(
            source_commit="a" * 40,
            episode_timeout_seconds=1800,
            environment_task_timeout_seconds=1800,
            author_timeout_decision_id="",
        )


def test_complete_budget_rejects_missing_episode_timeout():
    with pytest.raises(ValueError, match="explicitly positive"):
        CompleteExecutionBudgetContract.from_mapping(
            {
                "source_commit": "a" * 40,
                "episode_timeout_seconds": None,
                "environment_task_timeout_seconds": None,
                "author_timeout_decision_id": "author-timeout-decision",
            }
        )


def test_complete_budget_has_one_frozen_runtime_profile():
    contract = CompleteExecutionBudgetContract(
        source_commit="a" * 40,
        episode_timeout_seconds=1800,
        environment_task_timeout_seconds=1800,
        author_timeout_decision_id="author-timeout-decision",
    ).with_id()
    assert contract.max_execution_attempts == 4
    assert contract.max_explore_steps == 60
    assert contract.planning_replanning_limit == 4
    assert contract.action_step_limit == 30
    assert contract.provider_request_timeout_seconds == 180.0
    assert contract.provider_maximum_retries == 3
    assert contract.controller_exploration_step_limit == 60
    assert contract.controller_task_retry_limit == 30
    assert contract.maximum_technical_retries == 2
    assert contract.contract_id == contract.compute_contract_id()


def _contracts():
    source = "a" * 40
    budget = CompleteExecutionBudgetContract(
        source_commit=source,
        episode_timeout_seconds=1800,
        environment_task_timeout_seconds=1800,
        author_timeout_decision_id="author-timeout-decision",
    ).with_id()
    approval = PathBRemediationApproval(
        approval_name="test",
        approved_by="ZYF",
        approved_at="2026-07-19T00:00:00Z",
        fresh_campaign_source_sha=source,
        complete_budget_contract_id=budget.contract_id,
        approval_statement="Path B authorizes a fresh 60-unit execution",
    ).with_id()
    authorization = FreshDevelopmentCampaignAuthorization(
        authorization_name="test",
        approved_by="ZYF",
        authorized_at="2026-07-19T00:00:00+00:00",
        source_commit=source,
        path_b_approval_id=approval.approval_id,
        complete_budget_contract_id=budget.contract_id,
        campaign_id=fresh_campaign_id(
            source_commit=source,
            path_b_approval_id=approval.approval_id,
            complete_budget_contract_id=budget.contract_id,
        ),
    ).with_id()
    return budget, approval, authorization


def test_approval_timestamps_require_timezone():
    budget, _, _ = _contracts()
    with pytest.raises(ValueError, match="timezone"):
        PathBRemediationApproval(
            approval_name="test",
            approved_by="ZYF",
            approved_at="2026-07-19T00:00:00",
            fresh_campaign_source_sha="a" * 40,
            complete_budget_contract_id=budget.contract_id,
            approval_statement="Path B authorizes a fresh 60-unit execution",
        )


def test_fresh_root_initialization_rejects_historical_content(tmp_path):
    _, approval, authorization = _contracts()
    root = tmp_path / "campaign"
    root.mkdir()
    (root / "old_accepted.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="absent or empty"):
        initialize_fresh_campaign_root(
            output_root=root,
            approval=approval,
            authorization=authorization,
            budget=_contracts()[0],
            assignments=[],
        )


def test_attempt_three_is_rejected_before_process_factory(monkeypatch, tmp_path):
    budget, approval, authorization = _contracts()
    group = tmp_path / "group"
    for index in range(3):
        attempt = group / f"attempt-{index}"
        attempt.mkdir(parents=True)
        (attempt / "attempt_summary.json").write_text(
            json.dumps(
                {
                    "accepted": False,
                    "attempt": index,
                    "failure_category": "infrastructure_timeout",
                    "status": "technical_failure",
                }
            )
            + "\n",
            encoding="utf-8",
        )
    budget_path = tmp_path / "budget.json"
    persist_complete_budget_contract(budget_path, budget)
    assignment = {
        "difficulty": "basic",
        "group_id": "dev_train:basic:test:1",
        "role": "dev_train",
        "seed": "1",
        "sequence_index": 0,
        "task": "test",
    }
    calls = []
    monkeypatch.setattr(
        campaign_runner.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"stdout": "a" * 40 + "\n"})(),
    )
    monkeypatch.setattr(
        campaign_runner,
        "_run_stage6_process",
        lambda *args, **kwargs: calls.append((args, kwargs)) or 0,
    )

    with pytest.raises(RuntimeError, match="before environment launch"):
        campaign_runner._run_authorized_stage6_process(
            ["stage6"],
            approval=approval,
            authorization=authorization,
            budget=budget,
            assignment=assignment,
            expected_assignment=assignment,
            current_source_sha="a" * 40,
            group_root=group,
            attempt_index=3,
            budget_snapshot_path=budget_path,
            cwd=tmp_path,
            env={},
            output=None,
        )
    assert calls == []


def test_budget_profile_mismatch_blocks_process_factory(monkeypatch, tmp_path):
    budget, approval, authorization = _contracts()
    wrong_budget = CompleteExecutionBudgetContract(
        source_commit="a" * 40,
        episode_timeout_seconds=900,
        environment_task_timeout_seconds=900,
        author_timeout_decision_id="different-author-decision",
    ).with_id()
    budget_path = tmp_path / "budget.json"
    persist_complete_budget_contract(budget_path, wrong_budget)
    calls = []
    monkeypatch.setattr(
        campaign_runner.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"stdout": "a" * 40 + "\n"})(),
    )
    monkeypatch.setattr(
        campaign_runner,
        "_run_stage6_process",
        lambda *args, **kwargs: calls.append((args, kwargs)) or 0,
    )
    assignment = {"role": "dev_train"}

    with pytest.raises(ValueError, match="snapshot missing or mismatched"):
        campaign_runner._run_authorized_stage6_process(
            ["stage6"],
            approval=approval,
            authorization=authorization,
            budget=budget,
            assignment=assignment,
            expected_assignment=assignment,
            current_source_sha="a" * 40,
            group_root=tmp_path / "group",
            attempt_index=0,
            budget_snapshot_path=budget_path,
            cwd=tmp_path,
            env={},
            output=None,
        )
    assert calls == []


def test_runner_exposes_no_partial_campaign_or_budget_override():
    option_strings = {
        option
        for action in campaign_runner.build_parser()._actions
        for option in action.option_strings
    }
    assert "--limit" not in option_strings
    assert "--timeout-seconds" not in option_strings
    assert "--maximum-technical-retries" not in option_strings
    assert "--path-b-approval" in option_strings
    assert "--fresh-campaign-authorization" in option_strings
    assert "--complete-execution-budget-contract" in option_strings
