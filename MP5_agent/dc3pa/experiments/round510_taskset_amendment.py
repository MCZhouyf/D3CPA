"""Immutable Round 5.10 task replacement layered over the prior taskset.

The historical Round 5.9.2 release remains valid. This contract records the
author-directed replacement of ``mine sand`` with
``craft wooden pressure plate`` before restarting formal acquisition.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
REMOVED_TASK = "mine sand"
ADDED_TASK = "craft wooden pressure plate"
REPLACEMENT_DIFFICULTY = "basic"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class Round510TasksetAmendment:
    approval_record_id: str
    approved_by: str
    approved_at: str
    source_commit: str
    prior_taskset_release_id: str
    superseded_campaign_id: str
    removed_task: str
    added_task: str
    replacement_difficulty: str
    creative_payload_sha256: str
    formal_task_spec_sha256: str
    acquisition_seeds_reused: bool
    acquisition_order_preserved: bool
    prior_campaign_results_excluded: bool
    before_restarted_formal_acquisition: bool
    outcome_selected: bool
    reason: str
    schema_version: int = SCHEMA_VERSION
    amendment_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported Round 5.10 taskset amendment schema")
        required = (
            self.approval_record_id,
            self.approved_by,
            self.approved_at,
            self.source_commit,
            self.prior_taskset_release_id,
            self.superseded_campaign_id,
            self.creative_payload_sha256,
            self.formal_task_spec_sha256,
            self.reason,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Round 5.10 taskset amendment is incomplete")
        if self.approved_by != "ZYF":
            raise ValueError("Task replacement must be approved by ZYF")
        if len(self.source_commit) != 40:
            raise ValueError("Task replacement must bind a full source commit")
        if self.removed_task != REMOVED_TASK or self.added_task != ADDED_TASK:
            raise ValueError("Task replacement differs from author approval")
        if self.replacement_difficulty != REPLACEMENT_DIFFICULTY:
            raise ValueError("Replacement must retain the Basic task slot")
        if any(
            len(value) != 64
            for value in (
                self.creative_payload_sha256,
                self.formal_task_spec_sha256,
            )
        ):
            raise ValueError("Task asset SHA-256 is invalid")
        if not all(
            (
                self.acquisition_seeds_reused,
                self.acquisition_order_preserved,
                self.prior_campaign_results_excluded,
                self.before_restarted_formal_acquisition,
            )
        ):
            raise ValueError("Task replacement safeguards are incomplete")
        if self.outcome_selected:
            raise ValueError("Replacement cannot be selected from outcome tuning")
        expected = self.compute_amendment_id()
        if self.amendment_id and self.amendment_id != expected:
            raise ValueError("Round 5.10 taskset amendment hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("amendment_id", None)
        return payload

    def compute_amendment_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "Round510TasksetAmendment":
        return replace(self, amendment_id=self.compute_amendment_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.amendment_id else self.with_id()
        payload = item.payload_without_id()
        payload["amendment_id"] = item.amendment_id
        return payload


def validate_catalog_replacement(
    prior_rows: Sequence[Mapping[str, Any]],
    amended_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Verify an exact one-for-one task replacement with stable ordering."""
    errors: list[str] = []
    if len(prior_rows) != 50 or len(amended_rows) != 50:
        errors.append("Both task catalogs must contain exactly 50 rows")
        return tuple(errors)

    changed_indices = [
        index
        for index, (before, after) in enumerate(zip(prior_rows, amended_rows))
        if dict(before) != dict(after)
    ]
    if len(changed_indices) != 1:
        errors.append("Task catalog must contain exactly one changed row")
        return tuple(errors)

    index = changed_indices[0]
    before = prior_rows[index]
    after = amended_rows[index]
    if str(before.get("task", "")) != REMOVED_TASK:
        errors.append("Changed row does not remove mine sand")
    if str(after.get("task", "")) != ADDED_TASK:
        errors.append("Changed row does not add craft wooden pressure plate")
    if str(before.get("difficulty", "")) != REPLACEMENT_DIFFICULTY:
        errors.append("Removed task was not in the Basic slot")
    if str(after.get("difficulty", "")) != REPLACEMENT_DIFFICULTY:
        errors.append("Replacement did not retain the Basic slot")
    if int(after.get("minimum_subgoals", 0)) <= 0:
        errors.append("Replacement minimum_subgoals must be positive")

    counts = {
        difficulty: sum(
            str(row.get("difficulty", "")) == difficulty
            for row in amended_rows
        )
        for difficulty in ("basic", "easy", "medium", "hard", "complex")
    }
    if set(counts.values()) != {10}:
        errors.append(f"Amended difficulty counts are invalid: {counts}")
    if len({str(row.get("task", "")) for row in amended_rows}) != 50:
        errors.append("Amended task catalog contains duplicate tasks")
    return tuple(errors)
