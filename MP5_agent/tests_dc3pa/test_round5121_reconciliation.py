import json
from pathlib import Path
import subprocess

from dc3pa.experiments.round511_reconciliation import (
    choose_salvage_path,
    reconcile_execution_budgets,
    reconcile_technical_failures,
)


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _attempt(root: Path, index: int, *, code: int, accepted: bool):
    attempt = root / f"attempt-{index}"
    _write(
        attempt / "run_binding.json",
        {
            "run_id": f"run-{index}",
            "task": "task",
            "seed": "1",
            "role": "dev_train",
            "group_id": "group",
            "source_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
        },
    )
    _write(
        attempt / "attempt_summary.json",
        {
            "run_id": f"run-{index}",
            "attempt": index,
            "process_return_code": code,
            "accepted": accepted,
        },
    )


def test_timeout_is_classified_but_plain_exit_one_remains_unclassifiable(tmp_path):
    group = tmp_path / "runs" / "hash"
    _attempt(group, 0, code=124, accepted=False)
    _attempt(group, 1, code=1, accepted=False)
    _attempt(group, 2, code=0, accepted=True)
    _write(
        group / "accepted.json",
        {"attempt": 2, "task": "task", "seed": "1", "group_id": "group"},
    )

    rows, summary = reconcile_technical_failures(tmp_path)
    assert [row["assigned_category"] for row in rows] == [
        "infrastructure_timeout",
        "unclassifiable",
    ]
    assert summary["unclassifiable_attempts"] == 1
    assert not summary["technical_failure_reconciliation_eligible"]


def test_budget_provenance_does_not_promote_cli_default(tmp_path):
    group = tmp_path / "runs" / "hash"
    _attempt(group, 0, code=0, accepted=True)
    repo_root = Path(__file__).resolve().parents[2]

    rows, summary = reconcile_execution_budgets(tmp_path, repo_root=repo_root)
    by_field = {row["field_name"]: row for row in rows}
    assert by_field["max_execution_attempts"]["reconstruction_status"] == "proven"
    assert by_field["max_explore_steps"]["reconstructed_value"] == 60
    assert by_field["episode_timeout_seconds"]["reconstruction_status"] == "unprovable"
    assert summary["fields_proven"] == 2
    assert summary["fields_unprovable"] == 1
    assert not summary["budget_reconciliation_eligible"]


def test_salvage_path_is_deterministic_and_requires_matching_approval():
    decision = choose_salvage_path(
        {"unclassifiable_attempts": 1},
        {"fields_unprovable": 1},
        retry_limit_violations=3,
        contamination_count=0,
        lineage_mismatch_count=0,
        remediation_approval=None,
    )
    assert decision["scientifically_required_path"] == "path_b"
    assert decision["selected_path"] == "path_c"
    assert decision["salvage_status"] == "blocked"
    assert not decision["mine_dojo_execution_permitted"]
