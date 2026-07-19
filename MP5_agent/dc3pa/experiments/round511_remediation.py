"""Prospective safeguards for an author-approved Round 5.11 remediation run."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from dc3pa.providers.model_profile import OpenAIResponsesModelProfile

from .formal_acquisition_execution import TECHNICAL_FAILURE_CATEGORIES
from .round511_reconciliation import (
    Round511ReconciliationPolicy,
    _structured_attempt_signals,
    _trace_event_types,
    classify_structured_failure,
    sha256_file,
)


SCHEMA_VERSION = 1
MAXIMUM_TECHNICAL_RETRIES = 2


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _load_json(path: str | Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


@dataclass(frozen=True)
class ExecutionBudgetSnapshot:
    max_execution_attempts: int
    max_explore_steps: int
    episode_timeout_seconds: int
    provider_request_timeout_seconds: float
    provider_maximum_retries: int
    maximum_technical_retries: int = MAXIMUM_TECHNICAL_RETRIES
    schema_version: int = SCHEMA_VERSION
    snapshot_id: str = ""

    def __post_init__(self) -> None:
        numeric = (
            self.max_execution_attempts,
            self.max_explore_steps,
            self.episode_timeout_seconds,
            self.provider_request_timeout_seconds,
        )
        if any(isinstance(value, bool) or value <= 0 for value in numeric):
            raise ValueError("Execution budgets must be positive")
        if self.provider_maximum_retries < 0:
            raise ValueError("Provider retries cannot be negative")
        if self.maximum_technical_retries != MAXIMUM_TECHNICAL_RETRIES:
            raise ValueError("The frozen technical retry maximum changed")
        expected = self.compute_snapshot_id()
        if self.snapshot_id and self.snapshot_id != expected:
            raise ValueError("Execution budget snapshot hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("snapshot_id", None)
        return payload

    def compute_snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "ExecutionBudgetSnapshot":
        return replace(self, snapshot_id=self.compute_snapshot_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.snapshot_id else self.with_id()
        payload = item.payload_without_id()
        payload["snapshot_id"] = item.snapshot_id
        return payload


def approved_execution_budget(
    *, max_execution_attempts: int, max_explore_steps: int, episode_timeout_seconds: int
) -> ExecutionBudgetSnapshot:
    profile = OpenAIResponsesModelProfile().with_id()
    return ExecutionBudgetSnapshot(
        max_execution_attempts=max_execution_attempts,
        max_explore_steps=max_explore_steps,
        episode_timeout_seconds=episode_timeout_seconds,
        provider_request_timeout_seconds=profile.request_timeout_seconds,
        provider_maximum_retries=profile.maximum_retries,
    ).with_id()


def validate_retry_limit(value: int) -> None:
    if value != MAXIMUM_TECHNICAL_RETRIES:
        raise ValueError("The frozen retry maximum must remain exactly two")


def persist_budget_snapshot(path: str | Path, snapshot: ExecutionBudgetSnapshot) -> None:
    target = Path(path)
    payload = snapshot.to_dict()
    if target.exists():
        existing = _load_json(target)
        if existing != payload:
            raise ValueError("Existing execution budget snapshot differs")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def next_attempt_index(group_root: str | Path) -> int | None:
    """Return the next ledger index, rejecting retry 3 before launch."""
    root = Path(group_root)
    if (root / "accepted.json").is_file():
        return None
    summaries = sorted(
        root.glob("attempt-*/attempt_summary.json"),
        key=lambda path: int(path.parent.name.split("-")[-1]),
    )
    indices = [int(path.parent.name.split("-")[-1]) for path in summaries]
    if indices != list(range(len(indices))):
        raise ValueError("Attempt ledger is not contiguous")
    for path in summaries:
        summary = _load_json(path)
        if bool(summary.get("accepted")) or str(summary.get("status", "")).startswith(
            "completed_scientific"
        ):
            raise ValueError("Completed scientific attempt is missing accepted marker")
        category = str(summary.get("failure_category", ""))
        if category not in TECHNICAL_FAILURE_CATEGORIES:
            raise ValueError("Attempt ledger contains an unclassified technical failure")
    next_index = len(indices)
    if next_index > MAXIMUM_TECHNICAL_RETRIES:
        raise RuntimeError("Technical retry limit exhausted before environment launch")
    return next_index


def classify_failure_at_source(
    *, return_code: int, trace_path: str | Path
) -> tuple[str | None, dict[str, Any]]:
    event_types = _trace_event_types(Path(trace_path))
    signals = _structured_attempt_signals(
        {"process_return_code": return_code}, event_types
    )
    category, used = classify_structured_failure(
        signals, Round511ReconciliationPolicy()
    )
    return category, {name: signals[name] for name in used}


def recover_accepted_marker(
    output_root: str | Path, group_root: str | Path
) -> Mapping[str, Any] | None:
    """Recover a marker after a crash without rerunning the scientific attempt."""
    campaign_root = Path(output_root)
    root = Path(group_root)
    marker_path = root / "accepted.json"
    if marker_path.is_file():
        return _load_json(marker_path)
    accepted_summaries = []
    for summary_path in sorted(root.glob("attempt-*/attempt_summary.json")):
        summary = _load_json(summary_path)
        if bool(summary.get("accepted")):
            accepted_summaries.append((summary_path, summary))
    if not accepted_summaries:
        return None
    if len(accepted_summaries) != 1:
        raise ValueError("Multiple accepted attempts exist for one unit")
    summary_path, summary = accepted_summaries[0]
    attempt_root = summary_path.parent
    binding = _load_json(attempt_root / "run_binding.json")
    records = attempt_root / "development_decisions.jsonl"
    receipt = attempt_root / "bootstrap_receipt.json"
    budget = _load_json(attempt_root / "execution_budget_snapshot.json")
    if not records.is_file() or not receipt.is_file():
        raise ValueError("Accepted attempt is missing immutable output evidence")
    payload = {
        "run_id": str(summary["run_id"]),
        "attempt": int(summary["attempt"]),
        "role": str(binding["role"]),
        "group_id": str(binding["group_id"]),
        "task": str(binding["task"]),
        "seed": str(binding["seed"]),
        "task_completed": bool(summary.get("task_completed")),
        "status": str(summary.get("status", "")),
        "records": str(records.relative_to(campaign_root)),
        "receipt": str(receipt.relative_to(campaign_root)),
        "execution_budget_snapshot_id": str(budget["snapshot_id"]),
    }
    with marker_path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return payload


def materialize_accepted_datasets(output_root: str | Path) -> dict[str, Any]:
    """Rebuild role datasets from accepted markers and atomically publish a manifest."""
    root = Path(output_root)
    records_by_role: dict[str, list[dict[str, Any]]] = {
        "dev_train": [],
        "dev_tune": [],
    }
    seen_ids: set[str] = set()
    accepted_markers = sorted((root / "runs").glob("*/accepted.json"))
    for marker_path in accepted_markers:
        marker = _load_json(marker_path)
        role = str(marker.get("role", ""))
        if role not in records_by_role:
            raise ValueError("Accepted marker contains a protected role")
        relative_records = Path(str(marker.get("records", "")))
        if relative_records.is_absolute() or ".." in relative_records.parts:
            raise ValueError("Accepted records path escapes campaign root")
        records_path = root / relative_records
        for line in records_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("Decision record is not an object")
            record_id = str(record.get("record_id", ""))
            if not record_id or record_id in seen_ids:
                raise ValueError("Decision record ID is missing or duplicated")
            seen_ids.add(record_id)
            materialized = dict(record)
            materialized["execution_budget_snapshot_id"] = str(
                marker["execution_budget_snapshot_id"]
            )
            materialized["accepted_attempt_id"] = str(marker["run_id"])
            records_by_role[role].append(materialized)

    destination = root / "accepted_datasets"
    destination.mkdir(parents=True, exist_ok=True)
    published: dict[str, Any] = {}
    for role, rows in records_by_role.items():
        target = destination / f"{role}.jsonl"
        temporary = target.with_suffix(".jsonl.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        published[role] = {
            "record_count": len(rows),
            "sha256": sha256_file(target),
        }
    manifest = {
        "accepted_unit_count": len(accepted_markers),
        "roles": published,
        "schema_version": SCHEMA_VERSION,
    }
    manifest["manifest_id"] = _sha(manifest)
    manifest_path = destination / "manifest.json"
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    with temporary_manifest.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_manifest, manifest_path)
    return manifest
