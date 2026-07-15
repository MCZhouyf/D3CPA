"""Immutable exclusion manifest protecting final evaluation tasks and seeds."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence


FINAL_EXCLUSION_SCHEMA_VERSION = 1
FINAL_GOAL_STATUSES = frozenset(
    {"experience_covered", "final_heldout_terminal_goal"}
)
DEVELOPMENT_GOAL_STATUSES = frozenset(
    {"experience_covered", "development_novel_goal"}
)


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class FinalEvaluationTask:
    task: str
    difficulty: str
    goal_status: str
    test_seeds: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task.strip():
            raise ValueError("task is required")
        if not self.difficulty.strip():
            raise ValueError("difficulty is required")
        if self.goal_status not in FINAL_GOAL_STATUSES:
            raise ValueError(
                f"goal_status must be one of {sorted(FINAL_GOAL_STATUSES)}"
            )
        if not self.test_seeds:
            raise ValueError("At least one final test seed is required")
        if len(set(self.test_seeds)) != len(self.test_seeds):
            raise ValueError(f"Duplicate test seed for task {self.task!r}")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["test_seeds"] = list(self.test_seeds)
        payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class FinalTestExclusionManifest:
    manifest_name: str
    tasks: tuple[FinalEvaluationTask, ...]
    created_from_commit: str
    notes: str = ""
    schema_version: int = FINAL_EXCLUSION_SCHEMA_VERSION
    manifest_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != FINAL_EXCLUSION_SCHEMA_VERSION:
            raise ValueError("Unsupported final-test exclusion schema")
        if not self.manifest_name.strip() or not self.created_from_commit.strip():
            raise ValueError("manifest_name and created_from_commit are required")
        if not self.tasks:
            raise ValueError("Final evaluation tasks are required")
        names = [item.task for item in self.tasks]
        if len(names) != len(set(names)):
            raise ValueError("Final task names must be unique")
        expected = self.compute_manifest_id()
        if self.manifest_id and self.manifest_id != expected:
            raise ValueError("Final-test exclusion manifest hash mismatch")

    @property
    def final_heldout_tasks(self) -> frozenset[str]:
        return frozenset(
            item.task
            for item in self.tasks
            if item.goal_status == "final_heldout_terminal_goal"
        )

    @property
    def final_task_seed_pairs(self) -> frozenset[tuple[str, str]]:
        return frozenset(
            (item.task, seed)
            for item in self.tasks
            for seed in item.test_seeds
        )

    def task_map(self) -> dict[str, FinalEvaluationTask]:
        return {item.task: item for item in self.tasks}

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("manifest_id", None)
        payload["tasks"] = [
            item.to_dict()
            for item in sorted(self.tasks, key=lambda item: item.task)
        ]
        return payload

    def compute_manifest_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "FinalTestExclusionManifest":
        return replace(self, manifest_id=self.compute_manifest_id())

    def to_dict(self) -> dict[str, Any]:
        manifest = self if self.manifest_id else self.with_id()
        payload = manifest.payload_without_id()
        payload["manifest_id"] = manifest.manifest_id
        return payload

    def validate_development_item(
        self,
        *,
        task: str,
        seed: str,
        goal_status: str = "",
    ) -> None:
        if task in self.final_heldout_tasks:
            raise ValueError(
                f"Final-held-out terminal goal {task!r} cannot enter development"
            )
        if (task, str(seed)) in self.final_task_seed_pairs:
            raise ValueError(
                f"Final test task-seed pair {(task, str(seed))!r} entered development"
            )
        if goal_status:
            if goal_status not in DEVELOPMENT_GOAL_STATUSES:
                raise ValueError(
                    f"Development goal_status must be one of "
                    f"{sorted(DEVELOPMENT_GOAL_STATUSES)}, got {goal_status!r}"
                )
            if (
                goal_status == "development_novel_goal"
                and task in self.task_map()
            ):
                raise ValueError(
                    "development_novel_goal must not reuse a final evaluation task"
                )

    def validate_assignments(self, assignments: Sequence[Any]) -> None:
        for item in assignments:
            self.validate_development_item(
                task=str(getattr(item, "task")),
                seed=str(getattr(item, "seed")),
                goal_status=str(getattr(item, "goal_status", "")),
            )


def save_final_test_exclusion(
    path: str | Path,
    manifest: FinalTestExclusionManifest,
) -> str:
    manifest = manifest.with_id()
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return manifest.manifest_id


def load_final_test_exclusion(path: str | Path) -> FinalTestExclusionManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["tasks"] = tuple(
        FinalEvaluationTask(
            **{
                **item,
                "test_seeds": tuple(str(seed) for seed in item["test_seeds"]),
            }
        )
        for item in payload["tasks"]
    )
    return FinalTestExclusionManifest(**payload)
