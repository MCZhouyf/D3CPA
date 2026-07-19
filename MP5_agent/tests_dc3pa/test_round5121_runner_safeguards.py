import hashlib
import json
from pathlib import Path

import pytest

from dc3pa.experiments.round511_remediation import (
    approved_execution_budget,
    materialize_accepted_datasets,
    next_attempt_index,
    persist_budget_snapshot,
    recover_accepted_marker,
    validate_retry_limit,
)


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _summary(group: Path, index: int, *, category: str, accepted: bool = False):
    _write(
        group / f"attempt-{index}" / "attempt_summary.json",
        {
            "run_id": f"run-{index}",
            "attempt": index,
            "accepted": accepted,
            "failure_category": category,
            "status": "technical_failure" if not accepted else "completed_success",
        },
    )


def test_retry_three_is_rejected_before_environment_launch(tmp_path):
    group = tmp_path / "group"
    for index in range(3):
        _summary(group, index, category="infrastructure_timeout")
    with pytest.raises(RuntimeError, match="before environment launch"):
        next_attempt_index(group)
    with pytest.raises(ValueError, match="exactly two"):
        validate_retry_limit(3)


def test_scientific_completion_and_unclassified_failure_cannot_retry(tmp_path):
    scientific = tmp_path / "scientific"
    _summary(scientific, 0, category="", accepted=True)
    with pytest.raises(ValueError, match="scientific attempt"):
        next_attempt_index(scientific)

    ambiguous = tmp_path / "ambiguous"
    _summary(ambiguous, 0, category="unclassifiable")
    with pytest.raises(ValueError, match="unclassified"):
        next_attempt_index(ambiguous)


def test_budget_snapshot_is_complete_immutable_and_idempotent(tmp_path):
    snapshot = approved_execution_budget(
        max_execution_attempts=4,
        max_explore_steps=60,
        episode_timeout_seconds=1800,
    )
    path = tmp_path / "budget.json"
    persist_budget_snapshot(path, snapshot)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    persist_budget_snapshot(path, snapshot)
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == after
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["provider_request_timeout_seconds"] == 180.0
    assert payload["provider_maximum_retries"] == 3
    assert payload["maximum_technical_retries"] == 2


def test_only_accepted_records_are_materialized_and_resume_is_idempotent(tmp_path):
    failed = tmp_path / "runs" / "failed" / "attempt-0"
    failed.mkdir(parents=True)
    (failed / "development_decisions.jsonl").write_text(
        json.dumps({"record_id": "failed-row"}) + "\n", encoding="utf-8"
    )

    group = tmp_path / "runs" / "accepted"
    attempt = group / "attempt-0"
    _write(
        attempt / "run_binding.json",
        {
            "role": "dev_train",
            "group_id": "group",
            "task": "task",
            "seed": "1",
        },
    )
    _write(attempt / "bootstrap_receipt.json", {"pipeline_pass": True})
    (attempt / "development_decisions.jsonl").write_text(
        json.dumps({"record_id": "accepted-row"}) + "\n", encoding="utf-8"
    )
    snapshot = approved_execution_budget(
        max_execution_attempts=4,
        max_explore_steps=60,
        episode_timeout_seconds=1800,
    )
    persist_budget_snapshot(attempt / "execution_budget_snapshot.json", snapshot)
    _write(
        attempt / "attempt_summary.json",
        {
            "run_id": "run-0",
            "attempt": 0,
            "accepted": True,
            "task_completed": False,
            "status": "completed_scientific_failure",
        },
    )

    marker = recover_accepted_marker(tmp_path, group)
    assert marker is not None
    first = materialize_accepted_datasets(tmp_path)
    second = materialize_accepted_datasets(tmp_path)
    assert first == second
    records = (tmp_path / "accepted_datasets" / "dev_train.jsonl").read_text()
    assert "accepted-row" in records
    assert "failed-row" not in records
    assert snapshot.snapshot_id in records
    assert first["accepted_unit_count"] == 1


def test_protected_role_cannot_be_materialized(tmp_path):
    records = tmp_path / "records.jsonl"
    records.write_text(json.dumps({"record_id": "holdout"}) + "\n", encoding="utf-8")
    _write(
        tmp_path / "runs" / "group" / "accepted.json",
        {
            "role": "dev_holdout",
            "records": "records.jsonl",
            "run_id": "run",
            "execution_budget_snapshot_id": "budget",
        },
    )
    with pytest.raises(ValueError, match="protected role"):
        materialize_accepted_datasets(tmp_path)
