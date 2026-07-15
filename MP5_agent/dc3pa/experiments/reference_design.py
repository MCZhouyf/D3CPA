"""Deterministic reference design for the DC3PA major-revision experiments.

The generator removes manual cherry-picking while preserving the final
held-out boundary. It requires the authors' existing 50-task catalog; it does
not invent Minecraft tasks.

Reference choices:
- author-selected GPT-5.1 model identifier is configured separately;
- five covered and five final-held-out tasks per difficulty;
- horizon-balanced paired assignment with a frozen hash salt;
- thirty deterministic final seeds per task;
- four acquisition seeds for every covered task;
- task-level development split: three covered tasks for train, one for tune,
  one for locked holdout per difficulty;
- three development seeds per assigned task.

Changing a salt, task catalog, count, or policy creates a new design ID and
requires a new Blueprint approval. Final task status and final seeds must not
be changed after final evaluation starts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from dc3pa.experiments.blueprint import (
    AcquisitionAssignment,
    EnvironmentSearchSpace,
    PhaseBudget,
)
from dc3pa.reliability.activation_policy import ActivationPolicy
from dc3pa.reliability.development_protocol import GroupAssignment
from dc3pa.reliability.final_test_exclusion import (
    FinalEvaluationTask,
    FinalTestExclusionManifest,
)


REFERENCE_DESIGN_SCHEMA_VERSION = 2
DIFFICULTIES = ("basic", "easy", "medium", "hard", "complex")
MODEL_ID = "gpt-5.1"

DEFAULT_SPLIT_SALT = "dc3pa-ipm-major-revision-task-split-v1"
DEFAULT_FINAL_SEED_SALT = "dc3pa-ipm-major-revision-final-seeds-v1"
DEFAULT_ACQUISITION_SEED_SALT = "dc3pa-ipm-major-revision-acquisition-seeds-v1"
DEFAULT_DEVELOPMENT_SEED_SALT = "dc3pa-ipm-major-revision-development-seeds-v1"
DEFAULT_ROLE_SALT = "dc3pa-ipm-major-revision-development-roles-v1"


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_hex(*parts: Any) -> str:
    return hashlib.sha256(
        "\x1f".join(str(part) for part in parts).encode("utf-8")
    ).hexdigest()


def _positive_seed(
    *,
    namespace: str,
    task: str,
    index: int,
    salt: str,
    used: set[int],
) -> int:
    """Create a deterministic positive 31-bit seed with collision resolution."""

    nonce = 0
    while True:
        digest = hashlib.sha256(
            f"{salt}\x1f{namespace}\x1f{task}\x1f{index}\x1f{nonce}".encode(
                "utf-8"
            )
        ).digest()
        value = int.from_bytes(digest[:8], "big") % 2_147_483_646 + 1
        if value not in used:
            used.add(value)
            return value
        nonce += 1


@dataclass(frozen=True)
class TaskCatalogEntry:
    task: str
    difficulty: str
    minimum_subgoals: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task.strip():
            raise ValueError("task is required")
        difficulty = self.difficulty.strip().lower()
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"Unknown difficulty {self.difficulty!r}")
        object.__setattr__(self, "difficulty", difficulty)
        if isinstance(self.minimum_subgoals, bool) or self.minimum_subgoals <= 0:
            raise ValueError("minimum_subgoals must be positive")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class ReferenceDesignConfig:
    design_name: str = "dc3pa-ipm-major-revision-reference-v2"
    split_salt: str = DEFAULT_SPLIT_SALT
    final_seed_salt: str = DEFAULT_FINAL_SEED_SALT
    acquisition_seed_salt: str = DEFAULT_ACQUISITION_SEED_SALT
    development_seed_salt: str = DEFAULT_DEVELOPMENT_SEED_SALT
    role_salt: str = DEFAULT_ROLE_SALT
    final_seed_count: int = 30
    acquisition_seeds_per_covered_task: int = 4
    development_seeds_per_task: int = 3
    model_id: str = MODEL_ID
    source_commit: str = ""
    schema_version: int = REFERENCE_DESIGN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REFERENCE_DESIGN_SCHEMA_VERSION:
            raise ValueError("Unsupported reference design schema")
        for name in (
            "design_name",
            "split_salt",
            "final_seed_salt",
            "acquisition_seed_salt",
            "development_seed_salt",
            "role_salt",
            "model_id",
            "source_commit",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if self.model_id != MODEL_ID:
            raise ValueError(
                f"Reference profile uses author-selected model {MODEL_ID!r}"
            )
        if self.final_seed_count != 30:
            raise ValueError("Paper reference design requires 30 final seeds")
        if self.acquisition_seeds_per_covered_task != 4:
            raise ValueError("Reference acquisition uses four seeds per covered task")
        if self.development_seeds_per_task != 3:
            raise ValueError("Reference development uses three seeds per task")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReferenceExperimentDesign:
    config: ReferenceDesignConfig
    task_catalog: tuple[TaskCatalogEntry, ...]
    final_test_exclusion: FinalTestExclusionManifest
    acquisition_assignments: tuple[AcquisitionAssignment, ...]
    development_assignments: tuple[GroupAssignment, ...]
    phase_budgets: tuple[PhaseBudget, ...]
    environment_search_space: EnvironmentSearchSpace
    activation_policy: ActivationPolicy
    data_sufficiency_policy: Mapping[str, Any]
    model_profile: Mapping[str, Any]
    dry_run_group_ids: tuple[str, ...]
    schema_version: int = REFERENCE_DESIGN_SCHEMA_VERSION
    design_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != REFERENCE_DESIGN_SCHEMA_VERSION:
            raise ValueError("Unsupported design schema")
        expected = self.compute_design_id()
        if self.design_id and self.design_id != expected:
            raise ValueError("Reference design hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "config": self.config.to_dict(),
            "task_catalog": [item.to_dict() for item in self.task_catalog],
            "final_test_exclusion": self.final_test_exclusion.to_dict(),
            "acquisition_assignments": [
                item.to_dict() for item in self.acquisition_assignments
            ],
            "development_assignments": [
                item.to_dict() for item in self.development_assignments
            ],
            "phase_budgets": [item.to_dict() for item in self.phase_budgets],
            "environment_search_space": self.environment_search_space.to_dict(),
            "activation_policy": self.activation_policy.to_dict(),
            "data_sufficiency_policy": dict(self.data_sufficiency_policy),
            "model_profile": dict(self.model_profile),
            "dry_run_group_ids": list(self.dry_run_group_ids),
        }

    def compute_design_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "ReferenceExperimentDesign":
        return replace(self, design_id=self.compute_design_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.design_id else self.with_id()
        payload = item.payload_without_id()
        payload["design_id"] = item.design_id
        return payload


def load_task_catalog(path: str | Path) -> tuple[TaskCatalogEntry, ...]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"task", "difficulty", "minimum_subgoals"}
        if set(reader.fieldnames or ()) != required:
            raise ValueError(
                f"Task catalog columns must be exactly {sorted(required)}"
            )
        entries: list[TaskCatalogEntry] = []
        for line_number, row in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in row.values()):
                continue
            try:
                subgoals = int(str(row["minimum_subgoals"]).strip())
            except Exception as exc:
                raise ValueError(
                    f"Line {line_number}: invalid minimum_subgoals"
                ) from exc
            entries.append(
                TaskCatalogEntry(
                    task=str(row["task"]).strip(),
                    difficulty=str(row["difficulty"]).strip(),
                    minimum_subgoals=subgoals,
                )
            )
    if len(entries) != 50:
        raise ValueError(f"Expected exactly 50 tasks, found {len(entries)}")
    if len({item.task for item in entries}) != 50:
        raise ValueError("Task names must be unique")
    for difficulty in DIFFICULTIES:
        count = sum(item.difficulty == difficulty for item in entries)
        if count != 10:
            raise ValueError(f"{difficulty} must contain exactly 10 tasks")
    return tuple(entries)


def _balanced_status_assignment(
    items: Sequence[TaskCatalogEntry],
    *,
    split_salt: str,
) -> dict[str, str]:
    """Assign one covered and one held-out task inside each horizon-adjacent pair."""

    ordered = sorted(items, key=lambda item: (item.minimum_subgoals, item.task))
    if len(ordered) != 10:
        raise ValueError("Each difficulty needs ten tasks")
    status: dict[str, str] = {}
    for pair_index in range(5):
        pair = ordered[pair_index * 2 : pair_index * 2 + 2]
        ranked = sorted(
            pair,
            key=lambda item: _digest_hex(
                split_salt,
                item.difficulty,
                pair_index,
                item.task,
                item.minimum_subgoals,
            ),
        )
        status[ranked[0].task] = "experience_covered"
        status[ranked[1].task] = "final_heldout_terminal_goal"
    return status


def _role_assignment(
    covered: Sequence[TaskCatalogEntry],
    *,
    role_salt: str,
) -> dict[str, str]:
    if len(covered) != 5:
        raise ValueError("Each difficulty needs five covered tasks")
    ranked = sorted(
        covered,
        key=lambda item: _digest_hex(
            role_salt, item.difficulty, item.task, item.minimum_subgoals
        ),
    )
    return {
        **{item.task: "dev_train" for item in ranked[:3]},
        ranked[3].task: "dev_tune",
        ranked[4].task: "dev_holdout",
    }


def _reference_budgets(
    *,
    acquisition_episode_count: int,
    development_episode_count: int,
    holdout_episode_count: int,
) -> tuple[PhaseBudget, ...]:
    common = dict(
        maximum_high_level_steps_per_episode=60,
        maximum_llm_calls_per_episode=30,
        maximum_replans_per_episode=3,
        timeout_seconds_per_episode=1800.0,
        temperature=0.0,
        top_p=1.0,
    )
    return (
        PhaseBudget("dry_run", 6, **common, notes="Pipeline-only; excluded."),
        PhaseBudget(
            "experience_acquisition",
            acquisition_episode_count,
            **common,
            notes="Single-chain reactive collector.",
        ),
        PhaseBudget("memory_construction", 0, **common, notes="Offline."),
        PhaseBudget(
            "confidence_collection",
            development_episode_count,
            **common,
            notes="Passive development collection.",
        ),
        PhaseBudget("confidence_calibration", 0, **common, notes="Offline."),
        PhaseBudget("environment_tuning", 0, **common, notes="Offline dev only."),
        PhaseBudget("fusion_feature_generation", 0, **common, notes="Offline."),
        PhaseBudget("fusion_fitting", 0, **common, notes="Offline train/tune."),
        PhaseBudget(
            "development_holdout",
            holdout_episode_count,
            **common,
            notes="Locked development holdout.",
        ),
        PhaseBudget(
            "final_evaluation",
            1500,
            **common,
            notes="50 tasks x 30 frozen final seeds.",
        ),
    )


def _activation_policy() -> ActivationPolicy:
    return ActivationPolicy(
        policy_name="dc3pa-reference-fusion-activation-v1",
        noninferiority_margins={
            "brier": 0.01,
            "nll": 0.02,
            "ece": 0.02,
        },
        primary_metrics=("brier", "nll"),
        calibration_metrics=("ece",),
        minimum_primary_improvements=1,
        minimum_effects={
            "brier": 0.005,
            "nll": 0.01,
            "ece": 0.0,
        },
        require_improvement_ci_upper_at_most_zero=True,
        confidence_level=0.95,
        bootstrap_replicates=2000,
        bootstrap_seed=5102026,
        bootstrap_grouping="task",
        ece_bins=10,
    ).with_id()


def _sufficiency_policy() -> dict[str, Any]:
    return {
        "minimum_examples_per_role": {
            "dev_train": 250,
            "dev_tune": 75,
            "dev_holdout": 75,
        },
        "minimum_positive_per_role": {
            "dev_train": 125,
            "dev_tune": 35,
            "dev_holdout": 35,
        },
        "minimum_negative_per_role": {
            "dev_train": 40,
            "dev_tune": 12,
            "dev_holdout": 12,
        },
        "minimum_groups_per_role": {
            "dev_train": 30,
            "dev_tune": 10,
            "dev_holdout": 10,
        },
        "minimum_tasks_per_role": {
            "dev_train": 12,
            "dev_tune": 5,
            "dev_holdout": 5,
        },
        "required_metadata_strata": {
            "difficulty": list(DIFFICULTIES),
            "goal_status": ["experience_covered"],
        },
        "uniform_extension_rule": {
            "enabled_before_holdout_lock_only": True,
            "add_one_seed_to_every_task_in_insufficient_role": True,
            "maximum_extension_rounds": 2,
            "requires_new_blueprint_approval": True,
        },
    }


def _model_profile() -> dict[str, Any]:
    return {
        "provider": "openai_responses",
        "model": MODEL_ID,
        "reasoning_effort": "low",
        "store": False,
        "request_timeout_seconds": 180,
        "maximum_retries": 3,
        "sampling_parameters_sent": False,
        "purpose_max_output_tokens": {
            "planning": 8192,
            "dc3pa_confidence_and_evaluation": 4096,
            "reflection": 4096,
        },
        "same_model_and_effort_for_all_agentic_roles": True,
        "mutable_alias_author_approved": True,
        "api_key_environment_variable": "OPENAI_API_KEY",
        "base_url_environment_variable": "OPENAI_BASE_URL",
    }


def build_reference_design(
    task_catalog: Sequence[TaskCatalogEntry],
    *,
    config: ReferenceDesignConfig,
) -> ReferenceExperimentDesign:
    catalog = tuple(task_catalog)
    if len(catalog) != 50:
        raise ValueError("Reference design requires exactly 50 tasks")

    status: dict[str, str] = {}
    role: dict[str, str] = {}
    for difficulty in DIFFICULTIES:
        group = [item for item in catalog if item.difficulty == difficulty]
        group_status = _balanced_status_assignment(
            group, split_salt=config.split_salt
        )
        status.update(group_status)
        covered = [item for item in group if group_status[item.task] == "experience_covered"]
        role.update(_role_assignment(covered, role_salt=config.role_salt))

    used_seeds: set[int] = set()
    final_tasks: list[FinalEvaluationTask] = []
    for item in sorted(catalog, key=lambda x: (DIFFICULTIES.index(x.difficulty), x.task)):
        seeds = tuple(
            str(
                _positive_seed(
                    namespace="final",
                    task=item.task,
                    index=index,
                    salt=config.final_seed_salt,
                    used=used_seeds,
                )
            )
            for index in range(1, config.final_seed_count + 1)
        )
        final_tasks.append(
            FinalEvaluationTask(
                task=item.task,
                difficulty=item.difficulty,
                goal_status=status[item.task],
                test_seeds=seeds,
                metadata={"minimum_subgoals": item.minimum_subgoals},
            )
        )
    final_manifest = FinalTestExclusionManifest(
        manifest_name=f"{config.design_name}-final-50x30",
        tasks=tuple(final_tasks),
        created_from_commit=config.source_commit,
        notes=(
            "Covered/held-out assignments are horizon-balanced and selected "
            "by a frozen SHA-256 salt, not by observed performance."
        ),
    ).with_id()

    acquisition: list[AcquisitionAssignment] = []
    sequence_index = 0
    for item in sorted(
        (entry for entry in catalog if status[entry.task] == "experience_covered"),
        key=lambda x: (DIFFICULTIES.index(x.difficulty), x.minimum_subgoals, x.task),
    ):
        for index in range(1, config.acquisition_seeds_per_covered_task + 1):
            seed = _positive_seed(
                namespace="acquisition",
                task=item.task,
                index=index,
                salt=config.acquisition_seed_salt,
                used=used_seeds,
            )
            acquisition.append(
                AcquisitionAssignment(
                    group_id=f"acq:{item.difficulty}:{item.task}:{index}",
                    task=item.task,
                    seed=str(seed),
                    task_kind="experience_covered_final_goal",
                    difficulty=item.difficulty,
                    sequence_index=sequence_index,
                    metadata={"minimum_subgoals": item.minimum_subgoals},
                )
            )
            sequence_index += 1

    development: list[GroupAssignment] = []
    role_counts = {"dev_train": 0, "dev_tune": 0, "dev_holdout": 0}
    for item in sorted(
        (entry for entry in catalog if status[entry.task] == "experience_covered"),
        key=lambda x: (DIFFICULTIES.index(x.difficulty), x.task),
    ):
        item_role = role[item.task]
        for index in range(1, config.development_seeds_per_task + 1):
            seed = _positive_seed(
                namespace=item_role,
                task=item.task,
                index=index,
                salt=config.development_seed_salt,
                used=used_seeds,
            )
            development.append(
                GroupAssignment(
                    group_id=f"{item_role}:{item.difficulty}:{item.task}:{index}",
                    task=item.task,
                    seed=str(seed),
                    role=item_role,
                    difficulty=item.difficulty,
                    goal_status="experience_covered",
                    metadata={"minimum_subgoals": item.minimum_subgoals},
                )
            )
            role_counts[item_role] += 1

    train_by_difficulty: dict[str, list[GroupAssignment]] = {}
    for assignment in development:
        if assignment.role == "dev_train":
            train_by_difficulty.setdefault(assignment.difficulty, []).append(assignment)
    dry_run_ids: list[str] = []
    for difficulty in ("basic", "medium", "complex"):
        candidates = sorted(
            train_by_difficulty[difficulty],
            key=lambda item: (item.task, item.seed),
        )
        # Two seeds from the first task in each selected difficulty = six entries.
        first_task = candidates[0].task
        selected = [
            item.group_id for item in candidates if item.task == first_task
        ]
        dry_run_ids.extend(selected[:2])

    environment = EnvironmentSearchSpace(
        top_k_values=(1, 3, 5),
        text_threshold_values=(0.4, 0.5, 0.6),
        match_threshold_values=(0.35, 0.5, 0.65),
        environment_scope="current_context_only",
    )
    budgets = _reference_budgets(
        acquisition_episode_count=len(acquisition),
        development_episode_count=len(development),
        holdout_episode_count=role_counts["dev_holdout"],
    )
    design = ReferenceExperimentDesign(
        config=config,
        task_catalog=catalog,
        final_test_exclusion=final_manifest,
        acquisition_assignments=tuple(acquisition),
        development_assignments=tuple(development),
        phase_budgets=budgets,
        environment_search_space=environment,
        activation_policy=_activation_policy(),
        data_sufficiency_policy=_sufficiency_policy(),
        model_profile=_model_profile(),
        dry_run_group_ids=tuple(dry_run_ids),
    )
    return design.with_id()
