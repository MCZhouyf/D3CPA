from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from dc3pa.experiments.formal_acquisition_execution import (
    TECHNICAL_FAILURE_CATEGORIES,
)
from dc3pa.experiments.round511_reconciliation import (
    MISSING_BUDGET_FIELDS,
    Round511ReconciliationApproval,
    Round511ReconciliationPolicy,
    classify_structured_failure,
)


def test_policy_reuses_frozen_taxonomy_and_budget_fields():
    policy = Round511ReconciliationPolicy().with_id()
    assert {rule.category for rule in policy.classification_rules} == set(
        TECHNICAL_FAILURE_CATEGORIES
    )
    assert policy.missing_budget_fields == MISSING_BUDGET_FIELDS
    assert policy.maximum_technical_retries == 2
    assert policy.policy_id == policy.compute_policy_id()


def test_structured_classifier_rejects_ambiguous_and_free_text():
    category, used = classify_structured_failure(
        {"failure_detail": "provider timed out", "task_completed": False}
    )
    assert category is None
    assert used == ()

    category, used = classify_structured_failure(
        {
            "provider_stage": "response",
            "provider_response_status": "empty",
        }
    )
    assert category == "provider_empty_response"
    assert used == ("provider_stage", "provider_response_status")


def test_approval_cannot_relax_retry_or_authorize_execution_implicitly():
    policy = Round511ReconciliationPolicy().with_id()
    payload = {
        "approval_name": "test",
        "approved_by": "ZYF",
        "approval_kind": "policy_freeze",
        "reconciliation_policy_id": policy.policy_id,
        "closeout_id": policy.closeout_id,
        "round512_closeout_sha": policy.round512_closeout_sha,
        "remediation_path": "none",
        "approved_at": "2026-07-19T00:00:00Z",
        "original_retry_limit_preserved": True,
        "originals_remain_immutable": True,
        "holdout_access_forbidden": True,
        "outcome_selection_forbidden": True,
    }
    approval = Round511ReconciliationApproval(**payload).with_id()
    assert approval.approval_id == approval.compute_approval_id()
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(approval, remediation_path="path_b", approval_id="")
    with pytest.raises(ValueError, match="weakens"):
        replace(
            approval,
            original_retry_limit_preserved=False,
            approval_id="",
        )


def test_policy_freeze_cli_is_directly_runnable_and_exclusive(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "policy.json"
    command = [
        sys.executable,
        str(root / "scripts_dc3pa" / "freeze_round511_reconciliation_policy.py"),
        "--output",
        str(output),
    ]
    first = subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["policy_id"] == Round511ReconciliationPolicy().compute_policy_id()
    assert payload["policy_id"] in first.stdout

    second = subprocess.run(command, cwd=root, capture_output=True, text=True)
    assert second.returncode != 0
