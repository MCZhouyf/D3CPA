import json
from pathlib import Path

import pytest

from dc3pa.experiments.round5122_explore120 import (
    Explore120BudgetContract,
    continuation_queue,
    write_effective_outputs,
)
from scripts_dc3pa.run_round511_development_campaign import _stage6_environment


def _assignment(group_id, sequence_index, role="dev_train"):
    return {
        "difficulty": "medium",
        "group_id": group_id,
        "role": role,
        "seed": str(sequence_index + 100),
        "sequence_index": sequence_index,
        "task": f"task {sequence_index}",
    }


def _record(path: Path, record_id: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"record_id": record_id}) + "\n", encoding="utf-8")


def test_amended_budget_changes_only_exploration_limit():
    budget = Explore120BudgetContract(
        source_commit="a" * 40,
        author_decision_id="decision",
    ).with_id()

    assert budget.max_explore_steps == 120
    assert budget.controller_exploration_step_limit == 120
    assert budget.max_execution_attempts == 4
    assert budget.episode_timeout_seconds == 1800
    with pytest.raises(ValueError, match="60-to-120"):
        Explore120BudgetContract(
            source_commit="a" * 40,
            author_decision_id="decision",
            max_explore_steps=121,
        )


def test_stage6_environment_can_bind_authorized_120_steps():
    env = _stage6_environment(seed=7, base={}, max_explore_steps=120)
    assert env["DC3PA_MAX_EXPLORE_STEPS"] == "120"


def test_queue_retries_failures_before_unstarted_and_never_reruns_successes():
    assignments = [_assignment("success", 0), _assignment("failure", 1), _assignment("pending", 2)]
    original = {
        "success": {"status": "completed_success"},
        "failure": {"status": "completed_scientific_failure"},
    }

    queue = continuation_queue(assignments, original)

    assert [(item["reason"], item["assignment"]["group_id"]) for item in queue] == [
        ("retry_scientific_failure", "failure"),
        ("unstarted", "pending"),
    ]


def test_effective_result_replaces_failure_only_when_retry_succeeds(tmp_path):
    original_root = tmp_path / "original"
    continuation_root = tmp_path / "continuation"
    (continuation_root / "effective_datasets").mkdir(parents=True)
    assignments = [_assignment("failed-then-success", 0), _assignment("failed-twice", 1)]
    _record(original_root / "old-a.jsonl", "old-a")
    _record(original_root / "old-b.jsonl", "old-b")
    _record(continuation_root / "new-a.jsonl", "new-a")
    _record(continuation_root / "new-b.jsonl", "new-b")
    original = {
        "failed-then-success": {
            "records": "old-a.jsonl",
            "run_id": "old-a",
            "status": "completed_scientific_failure",
        },
        "failed-twice": {
            "records": "old-b.jsonl",
            "run_id": "old-b",
            "status": "completed_scientific_failure",
        },
    }
    retries = {
        "failed-then-success": {
            "records": "new-a.jsonl",
            "run_id": "new-a",
            "status": "completed_success",
        },
        "failed-twice": {
            "records": "new-b.jsonl",
            "run_id": "new-b",
            "status": "completed_scientific_failure",
        },
    }

    summary = write_effective_outputs(
        output_root=continuation_root,
        original_root=original_root,
        assignments=assignments,
        original_results=original,
        continuation_results=retries,
    )

    assert summary["success_count"] == 1
    assert summary["scientific_failure_count"] == 1
    assert summary["superseded_failure_count"] == 1
    rows = [
        json.loads(line)
        for line in (continuation_root / "effective_datasets/dev_train.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [row["record_id"] for row in rows] == ["new-a", "old-b"]
    assert rows[0]["original_outcome_superseded"] is True
    assert rows[1]["original_outcome_superseded"] is False
