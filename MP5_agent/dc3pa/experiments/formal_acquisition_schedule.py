"""Formal 100-episode acquisition schedule under the log-bootstrap condition."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
EXPECTED_EPISODES = 100
ACQUISITION_METHOD_ID = "single_chain_reactive_acquisition"


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
class FormalAcquisitionEntry:
    episode_index: int
    group_id: str
    task: str
    seed: str
    difficulty: str
    method_id: str
    bootstrap_policy_id: str
    scope: str = "formal_acquisition"

    def __post_init__(self) -> None:
        if self.episode_index < 0:
            raise ValueError("Episode index cannot be negative")
        if not all(
            (
                self.group_id,
                self.task,
                self.seed,
                self.difficulty,
                self.method_id,
                self.bootstrap_policy_id,
            )
        ):
            raise ValueError("Acquisition entry identity is incomplete")
        if self.method_id != ACQUISITION_METHOD_ID:
            raise ValueError("Formal acquisition must use the single-chain method")
        if self.scope != "formal_acquisition":
            raise ValueError("Acquisition entry uses the wrong scope")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FormalAcquisitionSchedule:
    schedule_name: str
    source_commit: str
    blueprint_id: str
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    method_id: str
    entries: tuple[FormalAcquisitionEntry, ...]
    all_methods_share_policy: bool
    memory_records_bootstrap_metadata: bool
    acquisition_writes_enabled: bool
    dual_chain_enabled: bool
    fusion_enabled: bool
    adaptive_trigger_enabled: bool
    log_bootstrap_enabled: bool
    schema_version: int = SCHEMA_VERSION
    schedule_id: str = ""

    def __post_init__(self) -> None:
        required = (
            self.schedule_name,
            self.source_commit,
            self.blueprint_id,
            self.bootstrap_policy_id,
            self.bootstrap_amendment_id,
            self.method_id,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Formal acquisition schedule identity is incomplete")
        if self.method_id != ACQUISITION_METHOD_ID:
            raise ValueError("Formal acquisition method is incorrect")
        if len(self.entries) != EXPECTED_EPISODES:
            raise ValueError(
                f"Formal acquisition requires {EXPECTED_EPISODES} entries"
            )
        if [item.episode_index for item in self.entries] != list(
            range(EXPECTED_EPISODES)
        ):
            raise ValueError("Acquisition episode indices are not contiguous")
        pairs = {(item.task, item.seed) for item in self.entries}
        if len(pairs) != EXPECTED_EPISODES:
            raise ValueError("Formal acquisition task-seed pairs are not unique")
        task_counts = Counter(item.task for item in self.entries)
        if len(task_counts) != 25 or set(task_counts.values()) != {4}:
            raise ValueError(
                "Formal acquisition requires 25 goals with four seeds each"
            )
        if any(item.bootstrap_policy_id != self.bootstrap_policy_id for item in self.entries):
            raise ValueError("Acquisition entries mix bootstrap policies")
        if any(item.method_id != self.method_id for item in self.entries):
            raise ValueError("Acquisition entries mix methods")
        if not all(
            (
                self.all_methods_share_policy,
                self.memory_records_bootstrap_metadata,
                self.acquisition_writes_enabled,
                self.log_bootstrap_enabled,
            )
        ):
            raise ValueError("Formal acquisition safeguards are incomplete")
        if any(
            (
                self.dual_chain_enabled,
                self.fusion_enabled,
                self.adaptive_trigger_enabled,
            )
        ):
            raise ValueError("Formal experience acquisition must remain single-chain")
        expected = self.compute_schedule_id()
        if self.schedule_id and self.schedule_id != expected:
            raise ValueError("Formal acquisition schedule hash mismatch")

    @property
    def episode_count(self) -> int:
        return len(self.entries)

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("schedule_id", None)
        payload["entries"] = [item.to_dict() for item in self.entries]
        payload["episode_count"] = self.episode_count
        return payload

    def compute_schedule_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalAcquisitionSchedule":
        return replace(self, schedule_id=self.compute_schedule_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.schedule_id else self.with_id()
        payload = item.payload_without_id()
        payload["schedule_id"] = item.schedule_id
        return payload


def build_formal_acquisition_schedule(
    acquisition_assignments: Sequence[Mapping[str, Any]],
    *,
    schedule_name: str,
    source_commit: str,
    blueprint_id: str,
    bootstrap_policy_id: str,
    bootstrap_amendment_id: str,
) -> FormalAcquisitionSchedule:
    ordered = sorted(
        acquisition_assignments,
        key=lambda item: (
            int(item.get("sequence_index", 0)),
            str(item.get("group_id", "")),
        ),
    )
    entries = tuple(
        FormalAcquisitionEntry(
            episode_index=index,
            group_id=str(item["group_id"]),
            task=str(item["task"]),
            seed=str(item["seed"]),
            difficulty=str(item["difficulty"]),
            method_id=ACQUISITION_METHOD_ID,
            bootstrap_policy_id=bootstrap_policy_id,
        )
        for index, item in enumerate(ordered)
    )
    return FormalAcquisitionSchedule(
        schedule_name=schedule_name,
        source_commit=source_commit,
        blueprint_id=blueprint_id,
        bootstrap_policy_id=bootstrap_policy_id,
        bootstrap_amendment_id=bootstrap_amendment_id,
        method_id=ACQUISITION_METHOD_ID,
        entries=entries,
        all_methods_share_policy=True,
        memory_records_bootstrap_metadata=True,
        acquisition_writes_enabled=True,
        dual_chain_enabled=False,
        fusion_enabled=False,
        adaptive_trigger_enabled=False,
        log_bootstrap_enabled=True,
    ).with_id()
