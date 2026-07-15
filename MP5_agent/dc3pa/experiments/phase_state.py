"""Append-only phase state for DC3PA's real experiment execution."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


STATE_SCHEMA_VERSION = 1
PHASE_ORDER = (
    "blueprint_frozen",
    "dry_run_completed",
    "acquisition_completed",
    "memory_frozen",
    "confidence_frozen",
    "environment_frozen",
    "development_data_validated",
    "fusion_candidate_frozen",
    "holdout_locked",
    "holdout_evaluated",
    "paper_release_frozen",
    "final_test_started",
)
PHASE_INDEX = {name: index for index, name in enumerate(PHASE_ORDER)}


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PhaseRecord:
    phase: str
    completed_at: str
    source_commit: str
    artifact_ids: Mapping[str, str] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.phase not in PHASE_INDEX:
            raise ValueError(f"Unknown phase {self.phase!r}")
        if not self.completed_at.strip() or not self.source_commit.strip():
            raise ValueError("completed_at and source_commit are required")
        if any(not str(key).strip() or not str(value).strip()
               for key, value in self.artifact_ids.items()):
            raise ValueError("Artifact IDs cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["artifact_ids"] = dict(sorted(self.artifact_ids.items()))
        return payload


@dataclass(frozen=True)
class ExperimentPhaseState:
    experiment_id: str
    records: tuple[PhaseRecord, ...]
    schema_version: int = STATE_SCHEMA_VERSION
    state_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != STATE_SCHEMA_VERSION:
            raise ValueError("Unsupported phase-state schema")
        if not self.experiment_id.strip():
            raise ValueError("experiment_id is required")
        seen: set[str] = set()
        last_index = -1
        for record in self.records:
            if record.phase in seen:
                raise ValueError(f"Phase {record.phase!r} appears more than once")
            seen.add(record.phase)
            index = PHASE_INDEX[record.phase]
            if index <= last_index:
                raise ValueError("Phase records must follow the declared order")
            if index != last_index + 1:
                missing = PHASE_ORDER[last_index + 1:index]
                raise ValueError(
                    f"Cannot skip experiment phases: {list(missing)}"
                )
            last_index = index
        expected = self.compute_state_id()
        if self.state_id and self.state_id != expected:
            raise ValueError("Phase-state hash mismatch")

    @property
    def completed_phases(self) -> tuple[str, ...]:
        return tuple(record.phase for record in self.records)

    @property
    def next_phase(self) -> Optional[str]:
        if len(self.records) >= len(PHASE_ORDER):
            return None
        return PHASE_ORDER[len(self.records)]

    def payload_without_id(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "records": [record.to_dict() for record in self.records],
            "schema_version": self.schema_version,
        }

    def compute_state_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "ExperimentPhaseState":
        return replace(self, state_id=self.compute_state_id())

    def to_dict(self) -> dict[str, Any]:
        state = self if self.state_id else self.with_id()
        payload = state.payload_without_id()
        payload["state_id"] = state.state_id
        payload["next_phase"] = state.next_phase
        return payload

    def advance(
        self,
        *,
        phase: str,
        source_commit: str,
        artifact_ids: Optional[Mapping[str, str]] = None,
        notes: str = "",
    ) -> "ExperimentPhaseState":
        if phase != self.next_phase:
            raise ValueError(
                f"Next permitted phase is {self.next_phase!r}, got {phase!r}"
            )
        record = PhaseRecord(
            phase=phase,
            completed_at=utc_now(),
            source_commit=source_commit,
            artifact_ids=dict(artifact_ids or {}),
            notes=notes,
        )
        return ExperimentPhaseState(
            experiment_id=self.experiment_id,
            records=self.records + (record,),
        ).with_id()


def save_state_atomic(path: str | Path, state: ExperimentPhaseState) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)
    return state.state_id


def load_state(path: str | Path) -> ExperimentPhaseState:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload.pop("next_phase", None)
    payload["records"] = tuple(PhaseRecord(**item) for item in payload["records"])
    return ExperimentPhaseState(**payload)
