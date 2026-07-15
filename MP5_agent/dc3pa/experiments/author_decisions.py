"""Compile author-supplied CSV/JSON decisions into Round 5.6 manifests.

This module does not choose tasks, seeds, budgets, models, prompts, statistical
margins, or data sufficiency thresholds. It only validates and compiles values
that the authors explicitly provide outside Git.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from dc3pa.experiments.blueprint import (
    AcquisitionAssignment,
    AuthorApproval,
    EnvironmentSearchSpace,
    PhaseBudget,
    RealExperimentBlueprint,
)
from dc3pa.reliability.activation_policy import load_activation_policy
from dc3pa.reliability.development_protocol import GroupAssignment
from dc3pa.reliability.final_test_exclusion import (
    FinalEvaluationTask,
    FinalTestExclusionManifest,
    save_final_test_exclusion,
)


AUTHOR_PACK_SCHEMA_VERSION = 1
PAPER_DIFFICULTIES = ("basic", "easy", "medium", "hard", "complex")
PLACEHOLDER_PATTERN = re.compile(
    r"(?:^|[^a-z0-9])(replace|pending|tbd|todo|example_only|fill_me|changeme)"
    r"(?:$|[^a-z0-9])",
    re.IGNORECASE,
)

FINAL_TASK_COLUMNS = ("task", "difficulty", "goal_status")
FINAL_SEED_COLUMNS = ("task", "seed", "seed_index")
ACQUISITION_COLUMNS = (
    "group_id",
    "task",
    "seed",
    "task_kind",
    "difficulty",
    "sequence_index",
)
DEVELOPMENT_COLUMNS = (
    "group_id",
    "task",
    "seed",
    "role",
    "difficulty",
    "goal_status",
)
BUDGET_COLUMNS = (
    "phase",
    "maximum_episodes",
    "maximum_high_level_steps_per_episode",
    "maximum_llm_calls_per_episode",
    "maximum_replans_per_episode",
    "timeout_seconds_per_episode",
    "temperature",
    "top_p",
    "notes",
)


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


def contains_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    return not text or bool(PLACEHOLDER_PATTERN.search(text))


def require_final_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if contains_placeholder(text):
        raise ValueError(f"{label} is empty or contains a placeholder: {text!r}")
    return text


def _read_csv(path: str | Path, required_columns: Sequence[str]) -> list[dict[str, str]]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        missing = [name for name in required_columns if name not in fieldnames]
        extra = [name for name in fieldnames if name not in required_columns]
        if missing or extra:
            raise ValueError(
                f"{source.name} columns mismatch; missing={missing}, extra={extra}"
            )
        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            cleaned = {name: str(row.get(name, "")).strip() for name in required_columns}
            if not any(cleaned.values()):
                continue
            cleaned["_line_number"] = str(line_number)
            rows.append(cleaned)
    if not rows:
        raise ValueError(f"{source.name} has no data rows")
    return rows


def _int(value: str, label: str, *, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except Exception as exc:
        raise ValueError(f"{label} must be an integer: {value!r}") from exc
    if parsed < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    return parsed


def _float(value: str, label: str, *, minimum: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception as exc:
        raise ValueError(f"{label} must be numeric: {value!r}") from exc
    if parsed < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    return parsed


def read_final_tasks(path: str | Path) -> list[dict[str, str]]:
    rows = _read_csv(path, FINAL_TASK_COLUMNS)
    seen: set[str] = set()
    for row in rows:
        line = row["_line_number"]
        task = require_final_text(row["task"], f"final_tasks.csv:{line}:task")
        difficulty = row["difficulty"].lower()
        if difficulty not in PAPER_DIFFICULTIES:
            raise ValueError(f"Invalid difficulty {difficulty!r} at line {line}")
        if row["goal_status"] not in {
            "experience_covered",
            "final_heldout_terminal_goal",
        }:
            raise ValueError(f"Invalid goal_status at line {line}")
        if task in seen:
            raise ValueError(f"Duplicate final task {task!r}")
        seen.add(task)
        row["task"] = task
        row["difficulty"] = difficulty
    return rows


def read_final_seeds(path: str | Path) -> list[dict[str, str]]:
    rows = _read_csv(path, FINAL_SEED_COLUMNS)
    seen: set[tuple[str, str]] = set()
    indices: dict[str, set[int]] = {}
    for row in rows:
        line = row["_line_number"]
        task = require_final_text(row["task"], f"final_seeds.csv:{line}:task")
        seed = require_final_text(row["seed"], f"final_seeds.csv:{line}:seed")
        index = _int(row["seed_index"], f"final_seeds.csv:{line}:seed_index", minimum=1)
        pair = (task, seed)
        if pair in seen:
            raise ValueError(f"Duplicate final task-seed {pair!r}")
        if index in indices.setdefault(task, set()):
            raise ValueError(f"Duplicate seed_index {index} for {task!r}")
        seen.add(pair)
        indices[task].add(index)
        row["task"] = task
        row["seed"] = seed
        row["seed_index"] = str(index)
    return rows


def read_acquisition(path: str | Path) -> tuple[AcquisitionAssignment, ...]:
    rows = _read_csv(path, ACQUISITION_COLUMNS)
    assignments: list[AcquisitionAssignment] = []
    for row in rows:
        line = row["_line_number"]
        assignments.append(
            AcquisitionAssignment(
                group_id=require_final_text(
                    row["group_id"], f"acquisition.csv:{line}:group_id"
                ),
                task=require_final_text(row["task"], f"acquisition.csv:{line}:task"),
                seed=require_final_text(row["seed"], f"acquisition.csv:{line}:seed"),
                task_kind=require_final_text(
                    row["task_kind"], f"acquisition.csv:{line}:task_kind"
                ),
                difficulty=row["difficulty"].lower(),
                sequence_index=_int(
                    row["sequence_index"],
                    f"acquisition.csv:{line}:sequence_index",
                    minimum=0,
                ),
            )
        )
    return tuple(assignments)


def read_development(path: str | Path) -> tuple[GroupAssignment, ...]:
    rows = _read_csv(path, DEVELOPMENT_COLUMNS)
    assignments: list[GroupAssignment] = []
    for row in rows:
        line = row["_line_number"]
        assignments.append(
            GroupAssignment(
                group_id=require_final_text(
                    row["group_id"], f"development.csv:{line}:group_id"
                ),
                task=require_final_text(row["task"], f"development.csv:{line}:task"),
                seed=require_final_text(row["seed"], f"development.csv:{line}:seed"),
                role=require_final_text(row["role"], f"development.csv:{line}:role"),
                difficulty=row["difficulty"].lower(),
                goal_status=require_final_text(
                    row["goal_status"], f"development.csv:{line}:goal_status"
                ),
            )
        )
    return tuple(assignments)


def read_phase_budgets(path: str | Path) -> tuple[PhaseBudget, ...]:
    rows = _read_csv(path, BUDGET_COLUMNS)
    budgets: list[PhaseBudget] = []
    for row in rows:
        line = row["_line_number"]
        budgets.append(
            PhaseBudget(
                phase=require_final_text(row["phase"], f"budgets.csv:{line}:phase"),
                maximum_episodes=_int(
                    row["maximum_episodes"],
                    f"budgets.csv:{line}:maximum_episodes",
                ),
                maximum_high_level_steps_per_episode=_int(
                    row["maximum_high_level_steps_per_episode"],
                    f"budgets.csv:{line}:maximum_high_level_steps_per_episode",
                ),
                maximum_llm_calls_per_episode=_int(
                    row["maximum_llm_calls_per_episode"],
                    f"budgets.csv:{line}:maximum_llm_calls_per_episode",
                ),
                maximum_replans_per_episode=_int(
                    row["maximum_replans_per_episode"],
                    f"budgets.csv:{line}:maximum_replans_per_episode",
                ),
                timeout_seconds_per_episode=_float(
                    row["timeout_seconds_per_episode"],
                    f"budgets.csv:{line}:timeout_seconds_per_episode",
                    minimum=0.000001,
                ),
                temperature=_float(
                    row["temperature"],
                    f"budgets.csv:{line}:temperature",
                ),
                top_p=_float(
                    row["top_p"],
                    f"budgets.csv:{line}:top_p",
                    minimum=0.000001,
                ),
                notes=row["notes"],
            )
        )
    return tuple(budgets)


def build_final_exclusion(
    final_task_rows: Sequence[Mapping[str, str]],
    final_seed_rows: Sequence[Mapping[str, str]],
    *,
    manifest_name: str,
    source_commit: str,
) -> FinalTestExclusionManifest:
    seeds_by_task: dict[str, list[tuple[int, str]]] = {}
    for row in final_seed_rows:
        seeds_by_task.setdefault(row["task"], []).append(
            (int(row["seed_index"]), row["seed"])
        )
    tasks = []
    final_names = {row["task"] for row in final_task_rows}
    extra_seed_tasks = set(seeds_by_task) - final_names
    if extra_seed_tasks:
        raise ValueError(f"Seeds reference unknown final tasks: {sorted(extra_seed_tasks)}")
    for row in final_task_rows:
        seed_items = sorted(seeds_by_task.get(row["task"], []))
        if len(seed_items) != 30:
            raise ValueError(
                f"Final task {row['task']!r} needs exactly 30 seeds, "
                f"found {len(seed_items)}"
            )
        if [index for index, _ in seed_items] != list(range(1, 31)):
            raise ValueError(
                f"Final task {row['task']!r} seed_index must be exactly 1..30"
            )
        tasks.append(
            FinalEvaluationTask(
                task=row["task"],
                difficulty=row["difficulty"],
                goal_status=row["goal_status"],
                test_seeds=tuple(seed for _, seed in seed_items),
            )
        )
    return FinalTestExclusionManifest(
        manifest_name=require_final_text(manifest_name, "manifest_name"),
        tasks=tuple(tasks),
        created_from_commit=require_final_text(source_commit, "source_commit"),
        notes="Compiled from an author-supplied Round 5.7 decision pack.",
    ).with_id()


def _load_settings(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("draft_only") is True:
        raise ValueError("settings.json is still marked draft_only")
    required = (
        "blueprint_name",
        "source_commit",
        "collector_mode",
        "controller_profile",
        "planner_model_id",
        "confidence_model_id",
        "environment_search_space",
    )
    for name in required:
        if name not in payload:
            raise ValueError(f"settings.json missing {name}")
    for name in (
        "blueprint_name",
        "source_commit",
        "controller_profile",
        "planner_model_id",
        "confidence_model_id",
    ):
        require_final_text(payload[name], f"settings.json:{name}")
    return payload


def prompt_hashes(prompt_files: Mapping[str, str | Path]) -> dict[str, str]:
    if not prompt_files:
        raise ValueError("At least one prompt file is required")
    hashes: dict[str, str] = {}
    for name, path in sorted(prompt_files.items()):
        key = require_final_text(name, "prompt name")
        source = Path(path)
        if not source.is_file():
            raise ValueError(f"Prompt file does not exist: {source}")
        if source.stat().st_size == 0:
            raise ValueError(f"Prompt file is empty: {source}")
        hashes[key] = sha256_file(source)
    return hashes


@dataclass(frozen=True)
class AuthorDecisionPackManifest:
    pack_name: str
    source_commit: str
    input_sha256: Mapping[str, str]
    output_sha256: Mapping[str, str]
    prompt_hashes: Mapping[str, str]
    activation_policy_id: str
    final_test_exclusion_id: str
    schema_version: int = AUTHOR_PACK_SCHEMA_VERSION
    pack_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != AUTHOR_PACK_SCHEMA_VERSION:
            raise ValueError("Unsupported author decision pack schema")
        for value in (self.pack_name, self.source_commit, self.activation_policy_id,
                      self.final_test_exclusion_id):
            require_final_text(value, "pack manifest field")
        expected = self.compute_pack_id()
        if self.pack_id and self.pack_id != expected:
            raise ValueError("Author decision pack hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("pack_id", None)
        for name in ("input_sha256", "output_sha256", "prompt_hashes"):
            payload[name] = dict(sorted(payload[name].items()))
        return payload

    def compute_pack_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "AuthorDecisionPackManifest":
        return replace(self, pack_id=self.compute_pack_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.pack_id else self.with_id()
        payload = item.payload_without_id()
        payload["pack_id"] = item.pack_id
        return payload


def render_author_review(
    *,
    final_exclusion: FinalTestExclusionManifest,
    acquisition: Sequence[AcquisitionAssignment],
    development: Sequence[GroupAssignment],
    budgets: Sequence[PhaseBudget],
    settings: Mapping[str, Any],
    prompt_hash_map: Mapping[str, str],
) -> str:
    lines = [
        f"# Author Review — {settings['blueprint_name']}",
        "",
        "This report contains design inputs only. It contains no experimental outcomes.",
        "",
        "## Final evaluation matrix",
        "",
        "| Difficulty | Covered | Final-held-out | Tasks |",
        "|---|---:|---:|---:|",
    ]
    for difficulty in PAPER_DIFFICULTIES:
        items = [
            item for item in final_exclusion.tasks
            if item.difficulty.lower() == difficulty
        ]
        covered = sum(item.goal_status == "experience_covered" for item in items)
        heldout = sum(
            item.goal_status == "final_heldout_terminal_goal" for item in items
        )
        lines.append(f"| {difficulty} | {covered} | {heldout} | {len(items)} |")
    lines.extend(
        [
            "",
            f"- Total final tasks: **{len(final_exclusion.tasks)}**",
            "- Final seeds per task: **30**",
            f"- Acquisition task–seed groups: **{len(acquisition)}**",
            f"- Development task–seed groups: **{len(development)}**",
            "",
            "## Development roles",
            "",
        ]
    )
    for role in ("dev_train", "dev_tune", "dev_holdout"):
        lines.append(
            f"- `{role}`: {sum(item.role == role for item in development)} groups"
        )
    lines.extend(["", "## Phase budgets", ""])
    for budget in sorted(budgets, key=lambda item: item.phase):
        lines.append(
            f"- `{budget.phase}`: episodes={budget.maximum_episodes}, "
            f"steps={budget.maximum_high_level_steps_per_episode}, "
            f"LLM calls={budget.maximum_llm_calls_per_episode}, "
            f"replans={budget.maximum_replans_per_episode}, "
            f"timeout={budget.timeout_seconds_per_episode}s"
        )
    lines.extend(
        [
            "",
            "## Frozen identities",
            "",
            f"- Source commit: `{settings['source_commit']}`",
            f"- Controller profile: `{settings['controller_profile']}`",
            f"- Planner model: `{settings['planner_model_id']}`",
            f"- Confidence model: `{settings['confidence_model_id']}`",
        ]
    )
    for name, value in sorted(prompt_hash_map.items()):
        lines.append(f"- Prompt `{name}` SHA-256: `{value}`")
    lines.extend(
        [
            "",
            "## Required author action",
            "",
            "1. Inspect every task, seed, role, budget, model ID, prompt hash, "
            "candidate grid, and statistical policy.",
            "2. Run the existing blueprint builder in `--print-content-sha-for-approval` mode.",
            "3. Record approval outside Git, insert the exact content SHA, and freeze the blueprint.",
            "4. Any later design change requires a new approval and Blueprint ID.",
            "",
        ]
    )
    return "\n".join(lines)


def compile_author_decision_pack(
    *,
    final_tasks_csv: str | Path,
    final_seeds_csv: str | Path,
    acquisition_csv: str | Path,
    development_csv: str | Path,
    budgets_csv: str | Path,
    settings_json: str | Path,
    activation_policy_json: str | Path,
    data_sufficiency_policy_json: str | Path,
    prompt_files: Mapping[str, str | Path],
    output_dir: str | Path,
) -> AuthorDecisionPackManifest:
    settings = _load_settings(settings_json)
    policy = load_activation_policy(activation_policy_json)
    # Parse sufficiency JSON now so malformed or still-placeholder policy fails
    # before output files are written. Its full semantics are enforced by the
    # existing audit tool.
    sufficiency = json.loads(
        Path(data_sufficiency_policy_json).read_text(encoding="utf-8")
    )
    if not isinstance(sufficiency, Mapping) or not sufficiency:
        raise ValueError("data_sufficiency_policy.json must be a nonempty object")

    final_rows = read_final_tasks(final_tasks_csv)
    seed_rows = read_final_seeds(final_seeds_csv)
    acquisition = read_acquisition(acquisition_csv)
    development = read_development(development_csv)
    budgets = read_phase_budgets(budgets_csv)
    prompt_map = prompt_hashes(prompt_files)

    exclusion = build_final_exclusion(
        final_rows,
        seed_rows,
        manifest_name=f"{settings['blueprint_name']}-final-test",
        source_commit=settings["source_commit"],
    )

    # Construct an unapproved blueprint solely to run all Round 5.6 partition
    # validation. The placeholder approval can print the pre-approval content
    # SHA but cannot freeze a Blueprint ID.
    pending_approval = AuthorApproval(
        approval_record_id="PENDING_AUTHOR_APPROVAL",
        approved_at="PENDING_AUTHOR_APPROVAL",
        approved_blueprint_content_sha256="PENDING_AUTHOR_APPROVAL",
        notes="Replace only after author review of the generated report.",
    )
    search = EnvironmentSearchSpace(
        top_k_values=tuple(settings["environment_search_space"]["top_k_values"]),
        text_threshold_values=tuple(
            settings["environment_search_space"]["text_threshold_values"]
        ),
        match_threshold_values=tuple(
            settings["environment_search_space"]["match_threshold_values"]
        ),
        environment_scope=settings["environment_search_space"][
            "environment_scope"
        ],
    )
    RealExperimentBlueprint(
        blueprint_name=settings["blueprint_name"],
        profile="paper_minecraft_50",
        final_test_exclusion=exclusion,
        acquisition_assignments=tuple(acquisition),
        development_assignments=tuple(development),
        phase_budgets=tuple(budgets),
        environment_search_space=search,
        activation_policy_id=policy.policy_id,
        activation_policy_file_sha256=sha256_file(activation_policy_json),
        data_sufficiency_policy_file_sha256=sha256_file(
            data_sufficiency_policy_json
        ),
        collector_mode=settings["collector_mode"],
        collector_reads_growing_scene_memory=bool(
            settings["collector_reads_growing_scene_memory"]
        ),
        controller_profile=settings["controller_profile"],
        planner_model_id=settings["planner_model_id"],
        confidence_model_id=settings["confidence_model_id"],
        prompt_hashes=prompt_map,
        source_commit=settings["source_commit"],
        author_approval=pending_approval,
        notes=settings.get("notes", ""),
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Output directory must be empty")

    exclusion_path = output / "final_test_exclusion.json"
    save_final_test_exclusion(exclusion_path, exclusion)

    spec = {
        "draft_only": False,
        "blueprint_name": settings["blueprint_name"],
        "profile": "paper_minecraft_50",
        "source_commit": settings["source_commit"],
        "collector_mode": settings["collector_mode"],
        "collector_reads_growing_scene_memory": bool(
            settings["collector_reads_growing_scene_memory"]
        ),
        "controller_profile": settings["controller_profile"],
        "planner_model_id": settings["planner_model_id"],
        "confidence_model_id": settings["confidence_model_id"],
        "prompt_hashes": prompt_map,
        "environment_search_space": search.to_dict(),
        "acquisition_assignments": [item.to_dict() for item in acquisition],
        "development_assignments": [item.to_dict() for item in development],
        "phase_budgets": [item.to_dict() for item in budgets],
        "author_approval": pending_approval.to_dict(),
        "notes": settings.get("notes", ""),
    }
    spec_path = output / "author_experiment_spec.preapproval.json"
    spec_path.write_text(
        json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    review_path = output / "author_review.md"
    review_path.write_text(
        render_author_review(
            final_exclusion=exclusion,
            acquisition=acquisition,
            development=development,
            budgets=budgets,
            settings=settings,
            prompt_hash_map=prompt_map,
        ),
        encoding="utf-8",
    )

    input_paths = {
        "final_tasks_csv": Path(final_tasks_csv),
        "final_seeds_csv": Path(final_seeds_csv),
        "acquisition_csv": Path(acquisition_csv),
        "development_csv": Path(development_csv),
        "budgets_csv": Path(budgets_csv),
        "settings_json": Path(settings_json),
        "activation_policy_json": Path(activation_policy_json),
        "data_sufficiency_policy_json": Path(data_sufficiency_policy_json),
        **{f"prompt:{name}": Path(path) for name, path in prompt_files.items()},
    }
    output_paths = {
        "final_test_exclusion": exclusion_path,
        "author_spec_preapproval": spec_path,
        "author_review": review_path,
    }
    manifest = AuthorDecisionPackManifest(
        pack_name=f"{settings['blueprint_name']}-author-decision-pack",
        source_commit=settings["source_commit"],
        input_sha256={
            name: sha256_file(path) for name, path in sorted(input_paths.items())
        },
        output_sha256={
            name: sha256_file(path) for name, path in sorted(output_paths.items())
        },
        prompt_hashes=prompt_map,
        activation_policy_id=policy.policy_id,
        final_test_exclusion_id=exclusion.manifest_id,
    ).with_id()
    manifest_path = output / "author_decision_pack_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
