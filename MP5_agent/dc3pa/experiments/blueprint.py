"""Author-approved blueprint for DC3PA's real Minecraft experiments.

The blueprint freezes task/seed partitions, collection policy, parameter-search
space, budgets, and policy file hashes before real development data are used.

It intentionally does not contain measured outcomes or fitted artifact values.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from dc3pa.reliability.development_protocol import (
    DEVELOPMENT_ROLES,
    GroupAssignment,
)
from dc3pa.reliability.final_test_exclusion import (
    FinalTestExclusionManifest,
)


BLUEPRINT_SCHEMA_VERSION = 1
BLUEPRINT_PROFILES = frozenset({"paper_minecraft_50", "synthetic_test"})
ACQUISITION_TASK_KINDS = frozenset(
    {"experience_covered_final_goal", "auxiliary_technology_tree"}
)
PHASE_NAMES = (
    "dry_run",
    "experience_acquisition",
    "memory_construction",
    "confidence_collection",
    "confidence_calibration",
    "environment_tuning",
    "fusion_feature_generation",
    "fusion_fitting",
    "development_holdout",
    "final_evaluation",
)
PAPER_DIFFICULTIES = ("basic", "easy", "medium", "hard", "complex")


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric, not bool")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return number


@dataclass(frozen=True)
class AcquisitionAssignment:
    group_id: str
    task: str
    seed: str
    task_kind: str
    difficulty: str = ""
    sequence_index: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.group_id.strip() or not self.task.strip() or not self.seed.strip():
            raise ValueError("Acquisition group_id, task, and seed are required")
        if self.task_kind not in ACQUISITION_TASK_KINDS:
            raise ValueError(
                f"task_kind must be one of {sorted(ACQUISITION_TASK_KINDS)}"
            )
        if isinstance(self.sequence_index, bool) or self.sequence_index < 0:
            raise ValueError("sequence_index must be a nonnegative integer")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class PhaseBudget:
    phase: str
    maximum_episodes: int
    maximum_high_level_steps_per_episode: int
    maximum_llm_calls_per_episode: int
    maximum_replans_per_episode: int
    timeout_seconds_per_episode: float
    temperature: float
    top_p: float = 1.0
    notes: str = ""

    def __post_init__(self) -> None:
        if self.phase not in PHASE_NAMES:
            raise ValueError(f"Unknown phase {self.phase!r}")
        integer_fields = (
            ("maximum_episodes", self.maximum_episodes),
            (
                "maximum_high_level_steps_per_episode",
                self.maximum_high_level_steps_per_episode,
            ),
            ("maximum_llm_calls_per_episode", self.maximum_llm_calls_per_episode),
            ("maximum_replans_per_episode", self.maximum_replans_per_episode),
        )
        for name, value in integer_fields:
            if isinstance(value, bool) or int(value) < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.phase not in {"memory_construction", "confidence_calibration",
                              "environment_tuning", "fusion_feature_generation",
                              "fusion_fitting"}:
            if self.maximum_episodes <= 0:
                raise ValueError(f"{self.phase} needs a positive episode budget")
        if _finite_nonnegative(
            self.timeout_seconds_per_episode, "timeout_seconds_per_episode"
        ) <= 0:
            raise ValueError("timeout_seconds_per_episode must be positive")
        temperature = _finite_nonnegative(self.temperature, "temperature")
        top_p = _finite_nonnegative(self.top_p, "top_p")
        if temperature > 2:
            raise ValueError("temperature is unexpectedly above 2")
        if not 0 < top_p <= 1:
            raise ValueError("top_p must be in (0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnvironmentSearchSpace:
    top_k_values: tuple[int, ...]
    text_threshold_values: tuple[float, ...]
    match_threshold_values: tuple[float, ...]
    environment_scope: str = "current_context_only"

    def __post_init__(self) -> None:
        if not self.top_k_values:
            raise ValueError("At least one top_k candidate is required")
        if any(isinstance(value, bool) or int(value) <= 0 for value in self.top_k_values):
            raise ValueError("top_k candidates must be positive integers")
        if len(set(self.top_k_values)) != len(self.top_k_values):
            raise ValueError("top_k candidates must be unique")
        for field_name, values in (
            ("text_threshold_values", self.text_threshold_values),
            ("match_threshold_values", self.match_threshold_values),
        ):
            if not values:
                raise ValueError(f"{field_name} cannot be empty")
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} candidates must be unique")
            for value in values:
                number = _finite_nonnegative(value, field_name)
                if not 0 <= number <= 1:
                    raise ValueError(f"{field_name} must be in [0, 1]")
        if self.environment_scope != "current_context_only":
            raise ValueError(
                "Paper blueprint must use current_context_only environment scope"
            )

    def contains(self, selected: Mapping[str, Any]) -> bool:
        try:
            return (
                int(selected["top_k"]) in set(self.top_k_values)
                and float(selected["text_threshold"])
                in set(float(v) for v in self.text_threshold_values)
                and float(selected["match_threshold"])
                in set(float(v) for v in self.match_threshold_values)
                and str(selected["environment_scope"]) == self.environment_scope
            )
        except (KeyError, TypeError, ValueError):
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "top_k_values": list(self.top_k_values),
            "text_threshold_values": list(self.text_threshold_values),
            "match_threshold_values": list(self.match_threshold_values),
            "environment_scope": self.environment_scope,
        }


@dataclass(frozen=True)
class AuthorApproval:
    approval_record_id: str
    approved_at: str
    approved_blueprint_content_sha256: str
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.approval_record_id.strip():
            raise ValueError("approval_record_id is required")
        if not self.approved_at.strip():
            raise ValueError("approved_at is required")
        if not self.approved_blueprint_content_sha256.strip():
            raise ValueError("approved_blueprint_content_sha256 is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealExperimentBlueprint:
    blueprint_name: str
    profile: str
    final_test_exclusion: FinalTestExclusionManifest
    acquisition_assignments: tuple[AcquisitionAssignment, ...]
    development_assignments: tuple[GroupAssignment, ...]
    phase_budgets: tuple[PhaseBudget, ...]
    environment_search_space: EnvironmentSearchSpace
    activation_policy_id: str
    activation_policy_file_sha256: str
    data_sufficiency_policy_file_sha256: str
    collector_mode: str
    collector_reads_growing_scene_memory: bool
    controller_profile: str
    planner_model_id: str
    confidence_model_id: str
    prompt_hashes: Mapping[str, str]
    source_commit: str
    author_approval: AuthorApproval
    notes: str = ""
    schema_version: int = BLUEPRINT_SCHEMA_VERSION
    blueprint_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != BLUEPRINT_SCHEMA_VERSION:
            raise ValueError("Unsupported blueprint schema")
        if self.profile not in BLUEPRINT_PROFILES:
            raise ValueError(f"profile must be one of {sorted(BLUEPRINT_PROFILES)}")
        required = (
            self.blueprint_name,
            self.activation_policy_id,
            self.activation_policy_file_sha256,
            self.data_sufficiency_policy_file_sha256,
            self.collector_mode,
            self.controller_profile,
            self.planner_model_id,
            self.confidence_model_id,
            self.source_commit,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Blueprint identifiers cannot be empty")
        if self.collector_mode != "single_chain_reactive":
            raise ValueError(
                "Paper acquisition must use single_chain_reactive collector"
            )
        if not self.acquisition_assignments:
            raise ValueError("Acquisition assignments are required")
        if not self.development_assignments:
            raise ValueError("Development assignments are required")
        if not self.phase_budgets:
            raise ValueError("Phase budgets are required")
        if not self.prompt_hashes:
            raise ValueError("Prompt hashes are required")
        self.validate_partitions()
        if self.blueprint_id:
            expected = self.compute_blueprint_id()
            if self.blueprint_id != expected:
                raise ValueError("Blueprint hash mismatch")

    def validate_partitions(self) -> None:
        final_manifest = self.final_test_exclusion
        final_id = (
            final_manifest.manifest_id or final_manifest.compute_manifest_id()
        )
        if not final_id:
            raise ValueError("Final-test exclusion manifest must be hashable")

        if self.profile == "paper_minecraft_50":
            tasks = tuple(final_manifest.tasks)
            if len(tasks) != 50:
                raise ValueError("Paper profile requires exactly 50 final tasks")
            by_difficulty: dict[str, list[Any]] = {
                difficulty: [] for difficulty in PAPER_DIFFICULTIES
            }
            for task in tasks:
                difficulty = task.difficulty.strip().lower()
                if difficulty not in by_difficulty:
                    raise ValueError(f"Unexpected difficulty {task.difficulty!r}")
                by_difficulty[difficulty].append(task)
                if len(task.test_seeds) != 30:
                    raise ValueError(
                        f"{task.task!r} must have exactly 30 final test seeds"
                    )
                if len(set(task.test_seeds)) != 30:
                    raise ValueError(
                        f"{task.task!r} must have 30 unique final test seeds"
                    )
            for difficulty, items in by_difficulty.items():
                if len(items) != 10:
                    raise ValueError(
                        f"{difficulty} must contain exactly 10 final tasks"
                    )
                covered = sum(
                    item.goal_status == "experience_covered" for item in items
                )
                heldout = sum(
                    item.goal_status == "final_heldout_terminal_goal"
                    for item in items
                )
                if (covered, heldout) != (5, 5):
                    raise ValueError(
                        f"{difficulty} must contain 5 covered and 5 held-out goals"
                    )

        acquisition_ids: set[str] = set()
        acquisition_pairs: set[tuple[str, str]] = set()
        sequence_indices: set[int] = set()
        final_map = final_manifest.task_map()
        for item in self.acquisition_assignments:
            if item.group_id in acquisition_ids:
                raise ValueError(f"Duplicate acquisition group {item.group_id!r}")
            acquisition_ids.add(item.group_id)
            pair = (item.task, str(item.seed))
            if pair in acquisition_pairs:
                raise ValueError(f"Duplicate acquisition task-seed {pair!r}")
            acquisition_pairs.add(pair)
            if item.sequence_index in sequence_indices:
                raise ValueError(
                    f"Duplicate acquisition sequence_index {item.sequence_index}"
                )
            sequence_indices.add(item.sequence_index)
            final_manifest.validate_development_item(
                task=item.task,
                seed=str(item.seed),
                goal_status=(
                    "experience_covered"
                    if item.task_kind == "experience_covered_final_goal"
                    else ""
                ),
            )
            if item.task_kind == "experience_covered_final_goal":
                final_task = final_map.get(item.task)
                if final_task is None:
                    raise ValueError(
                        f"Covered acquisition task {item.task!r} is not final task"
                    )
                if final_task.goal_status != "experience_covered":
                    raise ValueError(
                        f"Acquisition cannot use final-held-out goal {item.task!r}"
                    )
            elif item.task in final_map:
                raise ValueError(
                    "auxiliary_technology_tree task must not reuse a final task"
                )

        development_pairs: set[tuple[str, str]] = set()
        development_ids: set[str] = set()
        roles: set[str] = set()
        for item in self.development_assignments:
            if item.group_id in development_ids:
                raise ValueError(f"Duplicate development group {item.group_id!r}")
            development_ids.add(item.group_id)
            roles.add(item.role)
            pair = (item.task, str(item.seed))
            if pair in development_pairs:
                raise ValueError(f"Duplicate development task-seed {pair!r}")
            development_pairs.add(pair)
            if pair in acquisition_pairs:
                raise ValueError(
                    f"Acquisition and development share task-seed {pair!r}"
                )
            final_manifest.validate_development_item(
                task=item.task,
                seed=str(item.seed),
                goal_status=item.goal_status,
            )
        if roles != set(DEVELOPMENT_ROLES):
            raise ValueError(
                f"Development roles must be exactly {sorted(DEVELOPMENT_ROLES)}"
            )

        budget_phases = [item.phase for item in self.phase_budgets]
        if len(budget_phases) != len(set(budget_phases)):
            raise ValueError("Each phase may have only one budget")
        required_phases = {
            "dry_run",
            "experience_acquisition",
            "confidence_collection",
            "development_holdout",
            "final_evaluation",
        }
        missing = required_phases - set(budget_phases)
        if missing:
            raise ValueError(f"Missing phase budgets: {sorted(missing)}")

    def payload_without_id(self, *, include_approval: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("blueprint_id", None)
        payload["final_test_exclusion"] = self.final_test_exclusion.to_dict()
        payload["acquisition_assignments"] = [
            item.to_dict()
            for item in sorted(
                self.acquisition_assignments,
                key=lambda item: (item.sequence_index, item.group_id),
            )
        ]
        payload["development_assignments"] = [
            item.to_dict()
            for item in sorted(
                self.development_assignments,
                key=lambda item: (
                    item.role,
                    item.task,
                    item.seed,
                    item.group_id,
                ),
            )
        ]
        payload["phase_budgets"] = [
            item.to_dict()
            for item in sorted(self.phase_budgets, key=lambda item: item.phase)
        ]
        payload["environment_search_space"] = self.environment_search_space.to_dict()
        payload["prompt_hashes"] = dict(sorted(self.prompt_hashes.items()))
        if include_approval:
            payload["author_approval"] = self.author_approval.to_dict()
        else:
            payload.pop("author_approval", None)
        return payload

    def content_sha256_before_approval(self) -> str:
        return hashlib.sha256(
            _canonical_json(self.payload_without_id(include_approval=False))
        ).hexdigest()

    def validate_author_approval(self) -> None:
        expected = self.content_sha256_before_approval()
        if self.author_approval.approved_blueprint_content_sha256 != expected:
            raise ValueError(
                "Author approval hash does not match blueprint content"
            )

    def compute_blueprint_id(self) -> str:
        self.validate_author_approval()
        return hashlib.sha256(
            _canonical_json(self.payload_without_id(include_approval=True))
        ).hexdigest()

    def with_id(self) -> "RealExperimentBlueprint":
        return replace(self, blueprint_id=self.compute_blueprint_id())

    def to_dict(self) -> dict[str, Any]:
        blueprint = self if self.blueprint_id else self.with_id()
        payload = blueprint.payload_without_id(include_approval=True)
        payload["blueprint_id"] = blueprint.blueprint_id
        return payload


def save_blueprint(path: str | Path, blueprint: RealExperimentBlueprint) -> str:
    blueprint = blueprint.with_id()
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite blueprint: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(blueprint.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return blueprint.blueprint_id


def _load_final_manifest(payload: Mapping[str, Any]) -> FinalTestExclusionManifest:
    from dc3pa.reliability.final_test_exclusion import FinalEvaluationTask

    data = dict(payload)
    data["tasks"] = tuple(
        FinalEvaluationTask(
            **{
                **item,
                "test_seeds": tuple(str(seed) for seed in item["test_seeds"]),
            }
        )
        for item in data["tasks"]
    )
    return FinalTestExclusionManifest(**data)


def load_blueprint(path: str | Path) -> RealExperimentBlueprint:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["final_test_exclusion"] = _load_final_manifest(
        payload["final_test_exclusion"]
    )
    payload["acquisition_assignments"] = tuple(
        AcquisitionAssignment(**item)
        for item in payload["acquisition_assignments"]
    )
    payload["development_assignments"] = tuple(
        GroupAssignment(**item) for item in payload["development_assignments"]
    )
    payload["phase_budgets"] = tuple(
        PhaseBudget(**item) for item in payload["phase_budgets"]
    )
    payload["environment_search_space"] = EnvironmentSearchSpace(
        top_k_values=tuple(payload["environment_search_space"]["top_k_values"]),
        text_threshold_values=tuple(
            payload["environment_search_space"]["text_threshold_values"]
        ),
        match_threshold_values=tuple(
            payload["environment_search_space"]["match_threshold_values"]
        ),
        environment_scope=payload["environment_search_space"][
            "environment_scope"
        ],
    )
    payload["author_approval"] = AuthorApproval(**payload["author_approval"])
    return RealExperimentBlueprint(**payload)
