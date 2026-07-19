"""Auditable 120-step continuation of the frozen Round 5.12.2 campaign."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .round5122_pathb import ASSIGNMENT_MANIFEST_ID, canonical_assignment_manifest_id


SCHEMA_VERSION = 1
ORIGINAL_MAX_EXPLORE_STEPS = 60
AMENDED_MAX_EXPLORE_STEPS = 120


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def load_json(path: str | Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _require_timestamp(value: str) -> None:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Approval timestamp must include a timezone")


@dataclass(frozen=True)
class Explore120BudgetContract:
    source_commit: str
    author_decision_id: str
    episode_timeout_seconds: int = 1800
    environment_task_timeout_seconds: int = 1800
    max_execution_attempts: int = 4
    max_explore_steps: int = AMENDED_MAX_EXPLORE_STEPS
    controller_exploration_step_limit: int = AMENDED_MAX_EXPLORE_STEPS
    planning_replanning_limit: int = 4
    action_step_limit: int = 30
    provider_request_timeout_seconds: float = 180.0
    provider_maximum_retries: int = 3
    maximum_technical_retries: int = 2
    schema_version: int = SCHEMA_VERSION
    contract_id: str = ""

    def __post_init__(self) -> None:
        if len(self.source_commit) != 40 or not self.author_decision_id:
            raise ValueError("The amended budget requires source and author bindings")
        expected = (
            self.episode_timeout_seconds == 1800,
            self.environment_task_timeout_seconds == self.episode_timeout_seconds,
            self.max_execution_attempts == 4,
            self.max_explore_steps == AMENDED_MAX_EXPLORE_STEPS,
            self.controller_exploration_step_limit == AMENDED_MAX_EXPLORE_STEPS,
            self.planning_replanning_limit == 4,
            self.action_step_limit == 30,
            self.provider_request_timeout_seconds == 180.0,
            self.provider_maximum_retries == 3,
            self.maximum_technical_retries == 2,
        )
        if not all(expected):
            raise ValueError("Only the approved 60-to-120 exploration change is allowed")
        if self.contract_id and self.contract_id != self.compute_contract_id():
            raise ValueError("Amended budget contract hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("contract_id", None)
        return payload

    def compute_contract_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "Explore120BudgetContract":
        return replace(self, contract_id=self.compute_contract_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.contract_id else self.with_id()
        payload = item.payload_without_id()
        payload["contract_id"] = item.contract_id
        payload["snapshot_id"] = item.contract_id
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Explore120BudgetContract":
        values = dict(payload)
        values.pop("snapshot_id", None)
        return cls(**values)


@dataclass(frozen=True)
class Explore120ContinuationApproval:
    approved_by: str
    approved_at: str
    approval_statement: str
    source_commit: str
    original_campaign_id: str
    original_authorization_id: str
    original_budget_contract_id: str
    amended_budget_contract_id: str
    assignment_manifest_id: str = ASSIGNMENT_MANIFEST_ID
    retry_scientific_failures: bool = True
    continue_unstarted_units: bool = True
    rerun_original_successes: bool = False
    replace_conclusion_only_on_retry_success: bool = True
    preserve_original_evidence: bool = True
    evaluation_chain_calls_required: int = 0
    memory_writes_required: int = 0
    acquisition_writes_required: int = 0
    holdout_sealed: bool = True
    final_evaluation_unopened: bool = True
    schema_version: int = SCHEMA_VERSION
    approval_id: str = ""

    def __post_init__(self) -> None:
        if self.approved_by != "ZYF":
            raise ValueError("Explicit ZYF approval is required")
        _require_timestamp(self.approved_at)
        if len(self.source_commit) != 40:
            raise ValueError("Continuation source commit is incomplete")
        ids = (
            self.original_campaign_id,
            self.original_authorization_id,
            self.original_budget_contract_id,
            self.amended_budget_contract_id,
        )
        if any(len(value) != 64 for value in ids):
            raise ValueError("Continuation approval bindings are incomplete")
        safeguards = (
            "120" in self.approval_statement,
            self.assignment_manifest_id == ASSIGNMENT_MANIFEST_ID,
            self.retry_scientific_failures,
            self.continue_unstarted_units,
            not self.rerun_original_successes,
            self.replace_conclusion_only_on_retry_success,
            self.preserve_original_evidence,
            self.evaluation_chain_calls_required == 0,
            self.memory_writes_required == 0,
            self.acquisition_writes_required == 0,
            self.holdout_sealed,
            self.final_evaluation_unopened,
        )
        if not all(safeguards):
            raise ValueError("Continuation safeguards are incomplete")
        if self.approval_id and self.approval_id != self.compute_approval_id():
            raise ValueError("Continuation approval hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("approval_id", None)
        return payload

    def compute_approval_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "Explore120ContinuationApproval":
        return replace(self, approval_id=self.compute_approval_id())

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> "Explore120ContinuationApproval":
        return cls(**dict(payload))


def continuation_id(
    *, source_commit: str, approval_id: str, budget_contract_id: str
) -> str:
    return _sha(
        {
            "approval_id": approval_id,
            "assignment_manifest_id": ASSIGNMENT_MANIFEST_ID,
            "budget_contract_id": budget_contract_id,
            "source_commit": source_commit,
        }
    )


def validate_contracts(
    *,
    approval: Explore120ContinuationApproval,
    budget: Explore120BudgetContract,
    source_commit: str,
    original_manifest: Mapping[str, Any],
    assignments: Sequence[Mapping[str, Any]],
) -> None:
    approval = approval.with_id()
    budget = budget.with_id()
    if approval.source_commit != budget.source_commit or source_commit != budget.source_commit:
        raise ValueError("Continuation source binding mismatch")
    if approval.amended_budget_contract_id != budget.contract_id:
        raise ValueError("Continuation budget binding mismatch")
    if original_manifest.get("campaign_id") != approval.original_campaign_id:
        raise ValueError("Original campaign binding mismatch")
    if original_manifest.get("campaign_authorization_id") != approval.original_authorization_id:
        raise ValueError("Original authorization binding mismatch")
    if original_manifest.get("complete_execution_budget_contract_id") != approval.original_budget_contract_id:
        raise ValueError("Original budget binding mismatch")
    if canonical_assignment_manifest_id(assignments) != ASSIGNMENT_MANIFEST_ID:
        raise ValueError("Continuation assignments differ from the frozen manifest")


def original_result_map(
    original_root: str | Path, assignments: Sequence[Mapping[str, Any]]
) -> dict[str, Mapping[str, Any]]:
    root = Path(original_root)
    allowed = {str(item["group_id"]) for item in assignments}
    results: dict[str, Mapping[str, Any]] = {}
    for marker_path in (root / "runs").glob("*/accepted.json"):
        marker = load_json(marker_path)
        group_id = str(marker.get("group_id", ""))
        if group_id not in allowed or group_id in results:
            raise ValueError("Original campaign result ledger is invalid")
        status = str(marker.get("status", ""))
        if status not in {"completed_success", "completed_scientific_failure"}:
            raise ValueError("Original result is not a completed scientific outcome")
        item = dict(marker)
        item["marker_path"] = str(marker_path.relative_to(root))
        results[group_id] = item
    return results


def continuation_queue(
    assignments: Sequence[Mapping[str, Any]],
    original_results: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    ordered = sorted(assignments, key=lambda item: int(item["sequence_index"]))
    retries = []
    remaining = []
    for assignment in ordered:
        group_id = str(assignment["group_id"])
        result = original_results.get(group_id)
        if result is None:
            remaining.append({"reason": "unstarted", "assignment": dict(assignment)})
        elif result.get("status") == "completed_scientific_failure":
            retries.append(
                {"reason": "retry_scientific_failure", "assignment": dict(assignment)}
            )
    return retries + remaining


def initialize_continuation_root(
    *,
    output_root: str | Path,
    approval: Explore120ContinuationApproval,
    budget: Explore120BudgetContract,
    original_root: str | Path,
    original_results: Mapping[str, Mapping[str, Any]],
    queue: Sequence[Mapping[str, Any]],
) -> Path:
    root = Path(output_root)
    approval = approval.with_id()
    budget = budget.with_id()
    payload = {
        "amended_budget_contract_id": budget.contract_id,
        "approval_id": approval.approval_id,
        "assignment_manifest_id": approval.assignment_manifest_id,
        "continuation_id": continuation_id(
            source_commit=approval.source_commit,
            approval_id=approval.approval_id,
            budget_contract_id=budget.contract_id,
        ),
        "original_campaign_id": approval.original_campaign_id,
        "original_campaign_root": str(Path(original_root).resolve()),
        "original_completed_unit_count": len(original_results),
        "queue": list(queue),
        "schema_version": SCHEMA_VERSION,
        "source_commit": approval.source_commit,
    }
    payload["manifest_id"] = _sha(payload)
    path = root / "continuation_input_manifest.json"
    if path.exists():
        if load_json(path) != payload:
            raise ValueError("Continuation input manifest changed")
        return path
    if root.exists() and any(root.iterdir()):
        raise ValueError("Continuation output root must start empty")
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "runs").mkdir()
    (root / "effective_datasets").mkdir()
    return path


def persist_budget(path: str | Path, budget: Explore120BudgetContract) -> None:
    target = Path(path)
    payload = budget.with_id().to_dict()
    if target.exists():
        if load_json(target) != payload:
            raise ValueError("Continuation budget snapshot changed")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_effective_outputs(
    *,
    output_root: str | Path,
    original_root: str | Path,
    assignments: Sequence[Mapping[str, Any]],
    original_results: Mapping[str, Mapping[str, Any]],
    continuation_results: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Publish one effective outcome per unit without altering original evidence."""
    root = Path(output_root)
    old_root = Path(original_root)
    outcomes = []
    rows_by_role: dict[str, list[dict[str, Any]]] = {"dev_train": [], "dev_tune": []}
    seen_ids: set[str] = set()
    for assignment in sorted(assignments, key=lambda item: int(item["sequence_index"])):
        group_id = str(assignment["group_id"])
        original = original_results.get(group_id)
        retry = continuation_results.get(group_id)
        selected = original
        source_root = old_root
        superseded = False
        if original is None:
            selected = retry
            source_root = root
        elif original.get("status") == "completed_scientific_failure" and retry:
            if retry.get("status") == "completed_success":
                selected = retry
                source_root = root
                superseded = True
        if selected is None:
            outcomes.append(
                {"group_id": group_id, "status": "pending", "superseded": False}
            )
            continue
        outcomes.append(
            {
                "group_id": group_id,
                "original_status": original.get("status") if original else None,
                "selected_run_id": selected["run_id"],
                "status": selected["status"],
                "superseded": superseded,
            }
        )
        records_path = source_root / str(selected["records"])
        for line in records_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            record_id = str(record.get("record_id", ""))
            if not record_id or record_id in seen_ids:
                raise ValueError("Effective decision record IDs are invalid")
            seen_ids.add(record_id)
            materialized = dict(record)
            materialized["effective_outcome_source"] = (
                "120_step_continuation" if source_root == root else "original_60_step"
            )
            materialized["original_outcome_superseded"] = superseded
            rows_by_role[str(assignment["role"])].append(materialized)
    destination = root / "effective_datasets"
    destination.mkdir(exist_ok=True)
    roles = {}
    for role, rows in rows_by_role.items():
        target = destination / f"{role}.jsonl"
        temporary = target.with_suffix(".jsonl.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        roles[role] = {
            "record_count": len(rows),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
    summary = {
        "completed_unit_count": sum(item["status"] != "pending" for item in outcomes),
        "scientific_failure_count": sum(
            item["status"] == "completed_scientific_failure" for item in outcomes
        ),
        "success_count": sum(item["status"] == "completed_success" for item in outcomes),
        "superseded_failure_count": sum(bool(item["superseded"]) for item in outcomes),
        "outcomes": outcomes,
        "roles": roles,
        "schema_version": SCHEMA_VERSION,
    }
    summary["summary_id"] = _sha(summary)
    target = root / "effective_campaign_status.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return summary
