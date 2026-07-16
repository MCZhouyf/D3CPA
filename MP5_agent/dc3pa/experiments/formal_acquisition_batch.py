"""Deterministic health-batch planning for formal acquisition.

Batches are fixed contiguous groups of ten schedule entries. A batch cannot be
marked complete while any entry is unresolved. Technical retries remain inside
their original batch; task outcomes never change the schedule order.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence

from .formal_acquisition_execution import (
    EntryAttemptLedger,
    EXPECTED_EPISODES,
    FormalAcquisitionCampaign,
    TechnicalRetryPolicy,
)


SCHEMA_VERSION = 1
BATCH_SIZE = 10


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
class BatchEntryRequest:
    episode_index: int
    group_id: str
    task: str
    seed: str
    difficulty: str
    next_attempt_index: int
    retry_of_attempt_id: str
    is_technical_retry: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FormalAcquisitionBatchPlan:
    campaign_id: str
    schedule_id: str
    batch_index: int
    first_episode_index: int
    last_episode_index: int
    requests: tuple[BatchEntryRequest, ...]
    resolved_before_batch_count: int
    unresolved_before_batch_count: int
    outcome_based_selection_used: bool = False
    schema_version: int = SCHEMA_VERSION
    batch_plan_id: str = ""

    def __post_init__(self) -> None:
        if not 0 <= self.batch_index < EXPECTED_EPISODES // BATCH_SIZE:
            raise ValueError("Batch index is out of range")
        if self.first_episode_index != self.batch_index * BATCH_SIZE:
            raise ValueError("Batch start is not deterministic")
        if self.last_episode_index != self.first_episode_index + BATCH_SIZE - 1:
            raise ValueError("Batch end is not deterministic")
        if self.outcome_based_selection_used:
            raise ValueError("Outcome-based batch selection is forbidden")
        if any(
            not self.first_episode_index
            <= request.episode_index
            <= self.last_episode_index
            for request in self.requests
        ):
            raise ValueError("Batch request escapes the fixed batch interval")
        expected = self.compute_batch_plan_id()
        if self.batch_plan_id and self.batch_plan_id != expected:
            raise ValueError("Batch plan hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("batch_plan_id", None)
        payload["requests"] = [item.to_dict() for item in self.requests]
        return payload

    def compute_batch_plan_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalAcquisitionBatchPlan":
        return replace(self, batch_plan_id=self.compute_batch_plan_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.batch_plan_id else self.with_id()
        payload = item.payload_without_id()
        payload["batch_plan_id"] = item.batch_plan_id
        return payload


def plan_batch(
    *,
    campaign: FormalAcquisitionCampaign,
    schedule: Mapping[str, Any],
    ledgers: Sequence[EntryAttemptLedger],
    retry_policy: TechnicalRetryPolicy,
    batch_index: int,
) -> FormalAcquisitionBatchPlan:
    campaign = campaign if campaign.campaign_id else campaign.with_id()
    retry_policy = (
        retry_policy if retry_policy.policy_id else retry_policy.with_id()
    )
    entries = schedule.get("entries", ())
    if len(entries) != EXPECTED_EPISODES:
        raise ValueError("Schedule does not contain 100 entries")
    if schedule.get("schedule_id") != campaign.schedule_id:
        raise ValueError("Campaign/schedule ID mismatch")
    by_index = {ledger.episode_index: ledger for ledger in ledgers}
    if len(by_index) != EXPECTED_EPISODES:
        raise ValueError("Expected exactly 100 attempt ledgers")

    first = batch_index * BATCH_SIZE
    last = first + BATCH_SIZE - 1
    # Earlier batches must already be fully resolved. This prevents skipping
    # difficult task outcomes or unresolved technical failures.
    unresolved_earlier = [
        index for index in range(first) if not by_index[index].resolved
    ]
    if unresolved_earlier:
        raise ValueError(
            f"Earlier schedule entries remain unresolved: {unresolved_earlier}"
        )

    requests: list[BatchEntryRequest] = []
    for index in range(first, last + 1):
        entry = entries[index]
        ledger = by_index[index]
        if ledger.resolved:
            continue
        next_attempt = len(ledger.attempts)
        retry_of = ""
        is_retry = False
        if ledger.attempts:
            previous = ledger.attempts[-1]
            if previous.status != "technical_failure":
                raise ValueError(
                    f"Episode {index} has a nonfinal nontechnical state"
                )
            if ledger.technical_retry_count >= (
                retry_policy.maximum_technical_retries_per_entry
            ):
                raise ValueError(
                    f"Episode {index} exhausted technical retries"
                )
            retry_of = previous.attempt_id
            is_retry = True
        if (
            ledger.group_id,
            ledger.task,
            ledger.seed,
        ) != (
            str(entry["group_id"]),
            str(entry["task"]),
            str(entry["seed"]),
        ):
            raise ValueError(f"Episode {index} ledger/schedule mismatch")
        requests.append(
            BatchEntryRequest(
                episode_index=index,
                group_id=ledger.group_id,
                task=ledger.task,
                seed=ledger.seed,
                difficulty=str(entry["difficulty"]),
                next_attempt_index=next_attempt,
                retry_of_attempt_id=retry_of,
                is_technical_retry=is_retry,
            )
        )

    return FormalAcquisitionBatchPlan(
        campaign_id=campaign.campaign_id,
        schedule_id=campaign.schedule_id,
        batch_index=batch_index,
        first_episode_index=first,
        last_episode_index=last,
        requests=tuple(requests),
        resolved_before_batch_count=sum(
            by_index[index].resolved for index in range(first, last + 1)
        ),
        unresolved_before_batch_count=len(requests),
    ).with_id()
