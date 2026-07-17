"""Coverage audit for the paper-candidate MineCLIP memory."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
EXPECTED_COVERED_TASKS = 25
EXPECTED_SUCCESSFUL_EPISODES = 40


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
class MemoryCoverageAudit:
    paper_memory_release_id: str
    active_taskset_release_id: str
    successful_episode_count: int
    covered_task_count: int
    covered_tasks_with_success: int
    covered_task_success_fraction: float
    scene_exemplar_count: int
    dependency_edge_count: int
    action_key_coverage: float
    success_by_task: Mapping[str, int]
    scene_exemplars_by_task: Mapping[str, int]
    success_by_difficulty: Mapping[str, int]
    scene_exemplars_by_difficulty: Mapping[str, int]
    dependency_support_histogram: Mapping[str, int]
    zero_success_covered_tasks: tuple[str, ...]
    zero_scene_covered_tasks: tuple[str, ...]
    final_heldout_contamination_count: int
    final_seed_contamination_count: int
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    def __post_init__(self) -> None:
        expected = self.compute_audit_id()
        if self.audit_id and self.audit_id != expected:
            raise ValueError("Memory coverage audit hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("audit_id", None)
        for key in (
            "success_by_task",
            "scene_exemplars_by_task",
            "success_by_difficulty",
            "scene_exemplars_by_difficulty",
            "dependency_support_histogram",
        ):
            payload[key] = dict(sorted(payload[key].items()))
        payload["zero_success_covered_tasks"] = list(
            self.zero_success_covered_tasks
        )
        payload["zero_scene_covered_tasks"] = list(
            self.zero_scene_covered_tasks
        )
        payload["errors"] = list(self.errors)
        payload["warnings"] = list(self.warnings)
        return payload

    def compute_audit_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "MemoryCoverageAudit":
        return replace(self, audit_id=self.compute_audit_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.audit_id else self.with_id()
        payload = item.payload_without_id()
        payload["audit_id"] = item.audit_id
        return payload


def build_coverage_audit(
    *,
    paper_memory_release: Mapping[str, Any],
    active_taskset_release: Mapping[str, Any],
    acquisition_audit: Mapping[str, Any],
    acquisition_records: Sequence[Mapping[str, Any]],
    snapshot_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    covered_tasks: Sequence[Mapping[str, Any]],
    final_heldout_tasks: Sequence[str],
    final_task_seed_pairs: Sequence[tuple[str, str]],
) -> MemoryCoverageAudit:
    errors: list[str] = []
    warnings: list[str] = []

    if not paper_memory_release.get("eligible", False):
        errors.append("paper memory release is ineligible")
    if not active_taskset_release.get("eligible", False):
        errors.append("active taskset release is ineligible")

    covered_names = {str(item["task"]) for item in covered_tasks}
    difficulty_by_task = {
        str(item["task"]): str(item["difficulty"]) for item in covered_tasks
    }
    if len(covered_names) != EXPECTED_COVERED_TASKS:
        errors.append(
            f"Expected 25 covered tasks, found {len(covered_names)}"
        )

    success_by_task = Counter(
        {
            str(task): int(count)
            for task, count in (
                acquisition_audit.get("success_by_task", {}) or {}
            ).items()
        }
    )
    success_count = int(
        acquisition_audit.get("successful_episode_count", 0) or 0
    )
    if success_count != EXPECTED_SUCCESSFUL_EPISODES:
        errors.append("Acquisition success count is not 40")

    scenes_by_task: Counter[str] = Counter()
    for row in snapshot_rows.get("scene_exemplars", ()):
        task = str(row.get("task_name", row.get("task", "")))
        if task:
            scenes_by_task[task] += 1

    success_by_difficulty: Counter[str] = Counter()
    scenes_by_difficulty: Counter[str] = Counter()
    for task, count in success_by_task.items():
        difficulty = difficulty_by_task.get(task, "unknown")
        success_by_difficulty[difficulty] += count
    for task, count in scenes_by_task.items():
        difficulty = difficulty_by_task.get(task, "unknown")
        scenes_by_difficulty[difficulty] += count

    support_histogram: Counter[str] = Counter()
    for edge in snapshot_rows.get("dependency_edges", ()):
        support = int(
            edge.get(
                "success_count",
                edge.get("support_count", edge.get("support", 0)),
            )
            or 0
        )
        support_histogram[str(support)] += 1

    zero_success = tuple(
        sorted(task for task in covered_names if success_by_task.get(task, 0) == 0)
    )
    zero_scene = tuple(
        sorted(task for task in covered_names if scenes_by_task.get(task, 0) == 0)
    )
    tasks_with_success = len(covered_names) - len(zero_success)
    success_fraction = (
        0.0
        if not covered_names
        else tasks_with_success / len(covered_names)
    )

    heldout = set(str(item) for item in final_heldout_tasks)
    final_pairs = {(str(task), str(seed)) for task, seed in final_task_seed_pairs}
    heldout_contamination = 0
    seed_contamination = 0
    for payload in acquisition_records:
        record = payload.get("record", payload)
        task = str(record.get("task_name", record.get("task", "")))
        seed = str(record.get("seed", ""))
        if task in heldout:
            heldout_contamination += 1
        if (task, seed) in final_pairs:
            seed_contamination += 1

    if heldout_contamination:
        errors.append("Final-held-out task contamination was detected")
    if seed_contamination:
        errors.append("Final task-seed contamination was detected")
    if zero_success:
        warnings.append(
            f"{len(zero_success)} covered tasks have no successful acquisition episode"
        )
    if zero_scene:
        warnings.append(
            f"{len(zero_scene)} covered tasks have no Scene Exemplar"
        )

    scene_count = int(
        paper_memory_release.get("scene_exemplar_count", 0) or 0
    )
    edge_count = int(
        paper_memory_release.get("dependency_edge_count", 0) or 0
    )
    action_coverage = float(
        paper_memory_release.get("structured_action_key_coverage", 0.0)
    )
    if scene_count <= 0:
        errors.append("Paper memory has no Scene Exemplars")
    if edge_count <= 0:
        errors.append("Paper memory has no Dependency Edges")
    if action_coverage < 0.95:
        errors.append("Structured action-key coverage is below 95%")

    return MemoryCoverageAudit(
        paper_memory_release_id=str(
            paper_memory_release.get("release_id", "")
        ),
        active_taskset_release_id=str(
            active_taskset_release.get("release_id", "")
        ),
        successful_episode_count=success_count,
        covered_task_count=len(covered_names),
        covered_tasks_with_success=tasks_with_success,
        covered_task_success_fraction=success_fraction,
        scene_exemplar_count=scene_count,
        dependency_edge_count=edge_count,
        action_key_coverage=action_coverage,
        success_by_task=dict(success_by_task),
        scene_exemplars_by_task=dict(scenes_by_task),
        success_by_difficulty=dict(success_by_difficulty),
        scene_exemplars_by_difficulty=dict(scenes_by_difficulty),
        dependency_support_histogram=dict(support_histogram),
        zero_success_covered_tasks=zero_success,
        zero_scene_covered_tasks=zero_scene,
        final_heldout_contamination_count=heldout_contamination,
        final_seed_contamination_count=seed_contamination,
        eligible=not errors,
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(dict.fromkeys(warnings)),
    ).with_id()
