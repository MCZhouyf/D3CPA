from __future__ import annotations

import json
from pathlib import Path

from dc3pa.experiments.round511_closeout import (
    _audit_retry_lineage,
    _decision_accounting,
)


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _binding(run_id: str) -> dict:
    return {
        "collection_id": "collection",
        "development_input_release_id": "input",
        "development_protocol_id": "protocol",
        "role": "dev_train",
        "group_id": "group",
        "task": "craft stick",
        "seed": "1",
        "difficulty": "basic",
        "source_commit": "a" * 40,
        "paper_memory_v5_release_id": "memory",
        "snapshot_root_sha256": "snapshot",
        "bootstrap_policy_id": "bootstrap",
        "prompt_hash_bundle_id": "prompts",
        "requested_model_name": "gpt-5.1",
        "max_execution_attempts": 4,
        "max_explore_steps": 60,
        "episode_timeout_seconds": 1800,
        "run_id": run_id,
    }


def _campaign(tmp_path: Path, *, category: str = "provider_transport_failure") -> Path:
    root = tmp_path / "campaign"
    group = root / "runs" / "hash"
    for index in (0, 1):
        attempt = group / f"attempt-{index}"
        _write(attempt / "run_binding.json", _binding(f"run-{index}"))
        summary = {
            "attempt": index,
            "run_id": f"run-{index}",
            "accepted": index == 1,
            "pipeline_pass": index == 1,
            "task_completed": index == 1,
            "records_present": index == 1,
            "process_return_code": 0 if index == 1 else 1,
        }
        if index == 0 and category:
            summary["technical_failure_category"] = category
        _write(attempt / "attempt_summary.json", summary)
    _write(
        group / "accepted.json",
        {
            "attempt": 1,
            "run_id": "run-1",
            "role": "dev_train",
            "group_id": "group",
            "task": "craft stick",
            "seed": "1",
            "task_completed": True,
        },
    )
    return root


def test_retry_audit_accepts_frozen_category_and_bound_budgets(tmp_path):
    root = _campaign(tmp_path)
    audit, errors = _audit_retry_lineage(
        root,
        [{"record_id": "record", "run_id": "run-1"}],
        expected_technical_retries=1,
    )
    assert errors == []
    assert audit["technical_retry_attempts"] == 1
    assert audit["retry_count_by_category"] == {"provider_transport_failure": 1}


def test_retry_audit_fails_closed_when_category_is_unrecorded(tmp_path):
    root = _campaign(tmp_path, category="")
    audit, errors = _audit_retry_lineage(
        root,
        [{"record_id": "record", "run_id": "run-1"}],
        expected_technical_retries=1,
    )
    assert audit["retry_count_by_category"] == {"unrecorded": 1}
    assert any("unapproved technical category" in error for error in errors)


def test_decision_accounting_uses_runs_as_groups_not_rows():
    records = [
        {
            "role": "dev_train",
            "run_id": "run-1",
            "group_id": "group-1",
            "task": "craft stick",
            "seed": "1",
            "decision_correct": True,
            "knowledge_hard_feasible": True,
            "knowledge_unknown": False,
            "confidence_level": "high",
            "environment_raw_state": "matched",
        },
        {
            "role": "dev_train",
            "run_id": "run-1",
            "group_id": "group-1",
            "task": "craft stick",
            "seed": "1",
            "decision_correct": False,
            "knowledge_hard_feasible": False,
            "knowledge_unknown": True,
            "confidence_level": "low",
            "environment_raw_state": "unknown",
        },
    ]
    result = _decision_accounting(records, "dev_train")
    assert result["record_count"] == 2
    assert result["run_count"] == 1
    assert result["group_count"] == 1
    assert result["records_per_run_distribution"] == {"2": 1}
