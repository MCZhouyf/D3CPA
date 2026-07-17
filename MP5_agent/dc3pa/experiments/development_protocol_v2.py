"""Pressure-plate canonical development split validation.

Round 5.11 may materialize and execute only ``dev_train`` and ``dev_tune``.
``dev_holdout`` remains sealed and its assignment hash may be bound, but its
plain task/seed records and outcomes must not be read by Round 5.11 tools.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
ROLES = ("dev_train", "dev_tune", "dev_holdout")
ACTIVE_ROLES_ROUND511 = frozenset({"dev_train", "dev_tune"})


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
class DevelopmentAssignment:
    group_id: str
    task: str
    seed: str
    difficulty: str
    role: str
    sequence_index: int

    def __post_init__(self) -> None:
        if not all((self.group_id, self.task, self.seed, self.difficulty)):
            raise ValueError("Development assignment identity is incomplete")
        if self.role not in ROLES:
            raise ValueError(f"Unknown development role {self.role!r}")
        if self.sequence_index < 0:
            raise ValueError("Development sequence index cannot be negative")
        if self.task == "mine sand":
            raise ValueError("Active development assignment contains mine sand")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DevelopmentSplitProtocol:
    protocol_name: str
    source_commit: str
    active_taskset_release_id: str
    final_exclusion_id: str
    assignment_count: int
    role_counts: Mapping[str, int]
    assignment_hash: str
    train_tune_manifest_hash: str
    holdout_sealed_manifest_hash: str
    group_disjoint: bool
    task_seed_disjoint: bool
    final_heldout_contamination_count: int
    final_seed_contamination_count: int
    pressure_plate_assignment_count: int
    mine_sand_assignment_count: int
    outcome_selected: bool
    holdout_plaintext_materialized_for_round511: bool
    holdout_outcomes_observed: bool
    eligible: bool
    schema_version: int = SCHEMA_VERSION
    protocol_id: str = ""

    def __post_init__(self) -> None:
        if not self.eligible:
            raise ValueError("Cannot freeze an ineligible development protocol")
        if set(self.role_counts) != set(ROLES):
            raise ValueError("Development protocol must contain all three roles")
        if sum(self.role_counts.values()) != self.assignment_count:
            raise ValueError("Development role counts do not sum")
        if not self.group_disjoint or not self.task_seed_disjoint:
            raise ValueError("Development roles are not disjoint")
        if self.final_heldout_contamination_count:
            raise ValueError("Development protocol contains final-held-out tasks")
        if self.final_seed_contamination_count:
            raise ValueError("Development protocol contains final task-seeds")
        if self.mine_sand_assignment_count:
            raise ValueError("Development protocol still contains mine sand")
        if self.pressure_plate_assignment_count <= 0:
            raise ValueError("Pressure-plate task is absent from development protocol")
        if self.outcome_selected:
            raise ValueError("Development split cannot be selected from outcomes")
        if self.holdout_plaintext_materialized_for_round511:
            raise ValueError("Round 5.11 may not materialize holdout plaintext")
        if self.holdout_outcomes_observed:
            raise ValueError("Round 5.11 may not observe holdout outcomes")
        expected = self.compute_protocol_id()
        if self.protocol_id and self.protocol_id != expected:
            raise ValueError("Development protocol hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("protocol_id", None)
        payload["role_counts"] = dict(sorted(self.role_counts.items()))
        return payload

    def compute_protocol_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "DevelopmentSplitProtocol":
        return replace(self, protocol_id=self.compute_protocol_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.protocol_id else self.with_id()
        payload = item.payload_without_id()
        payload["protocol_id"] = item.protocol_id
        return payload


def audit_development_protocol(
    *,
    protocol_name: str,
    source_commit: str,
    active_taskset_release_id: str,
    final_exclusion_id: str,
    assignments: Sequence[DevelopmentAssignment],
    final_heldout_tasks: Sequence[str],
    final_task_seed_pairs: Sequence[tuple[str, str]],
    holdout_sealed_manifest_hash: str,
) -> DevelopmentSplitProtocol:
    if not assignments:
        raise ValueError("Development assignments are empty")
    ordered = sorted(assignments, key=lambda item: item.sequence_index)
    if [item.sequence_index for item in ordered] != list(range(len(ordered))):
        raise ValueError("Development sequence indices are not contiguous")

    groups_by_role: dict[str, set[str]] = {role: set() for role in ROLES}
    pairs_by_role: dict[str, set[tuple[str, str]]] = {
        role: set() for role in ROLES
    }
    role_counts = Counter(item.role for item in ordered)
    for role in ROLES:
        if role_counts[role] <= 0:
            raise ValueError(f"Development role {role!r} is empty")
    for item in ordered:
        if item.group_id in groups_by_role[item.role]:
            raise ValueError(
                f"Duplicate group within {item.role}: {item.group_id}"
            )
        groups_by_role[item.role].add(item.group_id)
        pair = (item.task, item.seed)
        if pair in pairs_by_role[item.role]:
            raise ValueError(
                f"Duplicate task-seed within {item.role}: {pair}"
            )
        pairs_by_role[item.role].add(pair)

    group_disjoint = all(
        groups_by_role[left].isdisjoint(groups_by_role[right])
        for index, left in enumerate(ROLES)
        for right in ROLES[index + 1 :]
    )
    pair_disjoint = all(
        pairs_by_role[left].isdisjoint(pairs_by_role[right])
        for index, left in enumerate(ROLES)
        for right in ROLES[index + 1 :]
    )

    heldout = set(final_heldout_tasks)
    final_pairs = {(str(task), str(seed)) for task, seed in final_task_seed_pairs}
    heldout_contamination = sum(item.task in heldout for item in ordered)
    seed_contamination = sum(
        (item.task, item.seed) in final_pairs for item in ordered
    )

    train_tune = [
        item.to_dict() for item in ordered if item.role in ACTIVE_ROLES_ROUND511
    ]
    all_payload = [item.to_dict() for item in ordered]
    return DevelopmentSplitProtocol(
        protocol_name=protocol_name,
        source_commit=source_commit,
        active_taskset_release_id=active_taskset_release_id,
        final_exclusion_id=final_exclusion_id,
        assignment_count=len(ordered),
        role_counts={role: role_counts[role] for role in ROLES},
        assignment_hash=_sha(all_payload),
        train_tune_manifest_hash=_sha(train_tune),
        holdout_sealed_manifest_hash=holdout_sealed_manifest_hash,
        group_disjoint=group_disjoint,
        task_seed_disjoint=pair_disjoint,
        final_heldout_contamination_count=heldout_contamination,
        final_seed_contamination_count=seed_contamination,
        pressure_plate_assignment_count=sum(
            item.task == "craft wooden pressure plate" for item in ordered
        ),
        mine_sand_assignment_count=sum(
            item.task == "mine sand" for item in ordered
        ),
        outcome_selected=False,
        holdout_plaintext_materialized_for_round511=False,
        holdout_outcomes_observed=False,
        eligible=(
            group_disjoint
            and pair_disjoint
            and not heldout_contamination
            and not seed_contamination
            and all(item.task != "mine sand" for item in ordered)
        ),
    ).with_id()
