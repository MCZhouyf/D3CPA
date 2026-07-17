"""Read-only lineage audit for deduplicated Scene Exemplars.

This audit explains successful covered tasks that have no task-owned Scene
Exemplar after deterministic deduplication. It never changes the frozen V5
snapshot.

A successful task without a task-owned Scene can be explained only by:
- ``cross_task_dedup``: at least one valid source candidate maps to a retained
  Scene whose canonical owner is another task; or
- ``no_valid_scene_candidate``: successful episodes produced no candidate that
  satisfied the frozen local-success evidence contract.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
ALLOWED_REASONS = frozenset(
    {"task_owned_scene", "cross_task_dedup", "no_valid_scene_candidate"}
)


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
class SuccessfulTaskEvidence:
    task: str
    successful_episode_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.task or not self.successful_episode_ids:
            raise ValueError("Successful task evidence is incomplete")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "successful_episode_ids": list(self.successful_episode_ids),
        }


@dataclass(frozen=True)
class SceneCandidateLineage:
    candidate_id: str
    deterministic_dedup_key: str
    source_task: str
    source_episode_id: str
    valid_local_success_candidate: bool
    retained_scene_id: str
    retained_scene_owner_task: str

    def __post_init__(self) -> None:
        if not (
            self.candidate_id
            and self.deterministic_dedup_key
            and self.source_task
            and self.source_episode_id
        ):
            raise ValueError("Scene candidate lineage is incomplete")
        if bool(self.retained_scene_id) != bool(self.retained_scene_owner_task):
            raise ValueError("Retained Scene ID/owner must appear together")
        if self.retained_scene_id and not self.valid_local_success_candidate:
            raise ValueError("Invalid candidate cannot map to a retained Scene")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskSceneLineageResult:
    task: str
    successful_episode_ids: tuple[str, ...]
    valid_candidate_ids: tuple[str, ...]
    retained_scene_ids: tuple[str, ...]
    task_owned_scene_ids: tuple[str, ...]
    cross_task_scene_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.reason not in ALLOWED_REASONS:
            raise ValueError("Unknown Scene-lineage reason")
        if self.reason == "task_owned_scene" and not self.task_owned_scene_ids:
            raise ValueError("Task-owned reason needs a task-owned Scene")
        if self.reason == "cross_task_dedup":
            if self.task_owned_scene_ids or not self.cross_task_scene_ids:
                raise ValueError("Cross-task dedup classification is inconsistent")
        if self.reason == "no_valid_scene_candidate":
            if self.valid_candidate_ids or self.retained_scene_ids:
                raise ValueError("No-candidate classification is inconsistent")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "successful_episode_ids",
            "valid_candidate_ids",
            "retained_scene_ids",
            "task_owned_scene_ids",
            "cross_task_scene_ids",
        ):
            payload[key] = list(payload[key])
        return payload


@dataclass(frozen=True)
class SceneLineageAudit:
    paper_memory_release_id: str
    acquisition_audit_id: str
    successful_task_count: int
    task_owned_scene_count: int
    cross_task_dedup_count: int
    no_valid_scene_candidate_count: int
    results: tuple[TaskSceneLineageResult, ...]
    snapshot_modified: bool
    new_minedojo_episode_count: int
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    def __post_init__(self) -> None:
        if self.snapshot_modified:
            raise ValueError("Scene lineage audit may not modify the snapshot")
        if self.new_minedojo_episode_count != 0:
            raise ValueError("Scene lineage audit may not run MineDojo")
        if self.successful_task_count != len(self.results):
            raise ValueError("Successful-task count/result count mismatch")
        if (
            self.task_owned_scene_count
            + self.cross_task_dedup_count
            + self.no_valid_scene_candidate_count
            != self.successful_task_count
        ):
            raise ValueError("Scene-lineage classifications do not sum")
        if self.eligible and self.errors:
            raise ValueError("Eligible Scene-lineage audit cannot contain errors")
        expected = self.compute_audit_id()
        if self.audit_id and self.audit_id != expected:
            raise ValueError("Scene-lineage audit hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("audit_id", None)
        payload["results"] = [item.to_dict() for item in self.results]
        payload["errors"] = list(self.errors)
        payload["warnings"] = list(self.warnings)
        return payload

    def compute_audit_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "SceneLineageAudit":
        return replace(self, audit_id=self.compute_audit_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.audit_id else self.with_id()
        payload = item.payload_without_id()
        payload["audit_id"] = item.audit_id
        return payload


def audit_scene_lineage(
    *,
    paper_memory_release_id: str,
    acquisition_audit_id: str,
    successful_tasks: Sequence[SuccessfulTaskEvidence],
    candidate_lineage: Sequence[SceneCandidateLineage],
) -> SceneLineageAudit:
    errors: list[str] = []
    warnings: list[str] = []
    by_task: dict[str, list[SceneCandidateLineage]] = {}
    for item in candidate_lineage:
        by_task.setdefault(item.source_task, []).append(item)

    results: list[TaskSceneLineageResult] = []
    seen_tasks: set[str] = set()
    for evidence in sorted(successful_tasks, key=lambda item: item.task):
        if evidence.task in seen_tasks:
            errors.append(f"duplicate successful-task evidence: {evidence.task}")
            continue
        seen_tasks.add(evidence.task)
        episode_ids = set(evidence.successful_episode_ids)
        candidates = [
            item
            for item in by_task.get(evidence.task, ())
            if item.source_episode_id in episode_ids
        ]
        valid = [item for item in candidates if item.valid_local_success_candidate]
        retained = [item for item in valid if item.retained_scene_id]
        owned = [
            item
            for item in retained
            if item.retained_scene_owner_task == evidence.task
        ]
        cross = [
            item
            for item in retained
            if item.retained_scene_owner_task != evidence.task
        ]
        if owned:
            reason = "task_owned_scene"
        elif cross:
            reason = "cross_task_dedup"
            warnings.append(
                f"{evidence.task}: Scene coverage is represented by a "
                "cross-task deduplicated Scene"
            )
        elif not valid:
            reason = "no_valid_scene_candidate"
            warnings.append(
                f"{evidence.task}: successful episode has no valid local Scene candidate"
            )
        else:
            reason = "no_valid_scene_candidate"
            errors.append(
                f"{evidence.task}: valid candidates exist but none are retained "
                "and no cross-task dedup lineage is recorded"
            )
        results.append(
            TaskSceneLineageResult(
                task=evidence.task,
                successful_episode_ids=tuple(sorted(episode_ids)),
                valid_candidate_ids=tuple(sorted(item.candidate_id for item in valid)),
                retained_scene_ids=tuple(
                    sorted({item.retained_scene_id for item in retained})
                ),
                task_owned_scene_ids=tuple(
                    sorted({item.retained_scene_id for item in owned})
                ),
                cross_task_scene_ids=tuple(
                    sorted({item.retained_scene_id for item in cross})
                ),
                reason=reason,
            )
        )

    unknown_tasks = sorted(set(by_task) - seen_tasks)
    if unknown_tasks:
        errors.append(
            f"candidate lineage contains tasks without successful evidence: {unknown_tasks}"
        )

    counts = {
        reason: sum(item.reason == reason for item in results)
        for reason in ALLOWED_REASONS
    }
    return SceneLineageAudit(
        paper_memory_release_id=paper_memory_release_id,
        acquisition_audit_id=acquisition_audit_id,
        successful_task_count=len(results),
        task_owned_scene_count=counts["task_owned_scene"],
        cross_task_dedup_count=counts["cross_task_dedup"],
        no_valid_scene_candidate_count=counts["no_valid_scene_candidate"],
        results=tuple(results),
        snapshot_modified=False,
        new_minedojo_episode_count=0,
        eligible=not errors,
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(dict.fromkeys(warnings)),
    ).with_id()
