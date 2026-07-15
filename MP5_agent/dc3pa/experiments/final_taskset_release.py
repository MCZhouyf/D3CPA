"""Freeze the final author-approved 50-task set before design generation.

This contract binds:
- the runtime-validated 50-task catalog;
- the runtime task tree and exact registry resolution;
- a pre-design ZYF compatibility amendment;
- critical end-to-end task-semantics smoke evidence.

It does not replace task_assets.py. It sits after task-asset validation and
before reconstructed-v1/schema-v2 design generation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
DIFFICULTIES = ("basic", "easy", "medium", "hard", "complex")
REQUIRED_CRITICAL_TASKS = frozenset(
    {
        "craft fence",
        "craft wooden door",
        "craft shears",
        "craft diamond axe",
        "mine coal ore",
        "mine iron ore",
    }
)
EXPECTED_REMOVED = frozenset(
    {
        "craft wooden pressure plate",
        "craft barrel",
        "craft carpentry table",
        "craft raw gold block",
    }
)
EXPECTED_ADDED = frozenset(
    {
        "craft fence",
        "craft wooden door",
        "craft shears",
        "craft diamond axe",
    }
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


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class TasksetAmendment:
    approval_record_id: str
    approved_by: str
    approval_effective_date: str
    source_commit_prefix: str
    source_commit: str
    change_type: str
    reason: str
    removed_tasks: tuple[str, ...]
    added_tasks: tuple[str, ...]
    final_task_count: int
    difficulty_counts: Mapping[str, int]
    before_reconstructed_v1: bool
    before_schema_v2_design: bool
    before_blueprint: bool
    before_holdout_lock: bool
    before_formal_acquisition: bool
    outcome_selected: bool
    schema_version: int = SCHEMA_VERSION
    amendment_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported taskset amendment schema")
        required = (
            self.approval_record_id,
            self.approved_by,
            self.approval_effective_date,
            self.source_commit_prefix,
            self.source_commit,
            self.change_type,
            self.reason,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Taskset amendment identity is incomplete")
        if self.approved_by != "ZYF":
            raise ValueError("Taskset amendment must be approved by ZYF")
        if len(self.source_commit) != 40 or not all(
            character in "0123456789abcdef" for character in self.source_commit
        ):
            raise ValueError("Taskset amendment must bind a full lowercase Git SHA")
        if not self.source_commit.startswith(self.source_commit_prefix):
            raise ValueError("Taskset amendment source commit prefix mismatch")
        if self.final_task_count != 50:
            raise ValueError("Final taskset must contain 50 tasks")
        expected_counts = {difficulty: 10 for difficulty in DIFFICULTIES}
        if dict(self.difficulty_counts) != expected_counts:
            raise ValueError(
                f"Expected ten tasks per difficulty, got {self.difficulty_counts}"
            )
        if set(self.removed_tasks) != EXPECTED_REMOVED:
            raise ValueError("Removed-task set differs from approved amendment")
        if set(self.added_tasks) != EXPECTED_ADDED:
            raise ValueError("Added-task set differs from approved amendment")
        if not all(
            (
                self.before_reconstructed_v1,
                self.before_schema_v2_design,
                self.before_blueprint,
                self.before_holdout_lock,
                self.before_formal_acquisition,
            )
        ):
            raise ValueError("Amendment must occur before all formal design gates")
        if self.outcome_selected:
            raise ValueError("Runtime compatibility amendment cannot use outcomes")
        expected = self.compute_amendment_id()
        if self.amendment_id and self.amendment_id != expected:
            raise ValueError("Taskset amendment hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("amendment_id", None)
        payload["removed_tasks"] = sorted(self.removed_tasks)
        payload["added_tasks"] = sorted(self.added_tasks)
        payload["difficulty_counts"] = dict(sorted(self.difficulty_counts.items()))
        return payload

    def compute_amendment_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "TasksetAmendment":
        return replace(self, amendment_id=self.compute_amendment_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.amendment_id else self.with_id()
        payload = item.payload_without_id()
        payload["amendment_id"] = item.amendment_id
        return payload


@dataclass(frozen=True)
class TaskSemanticReceipt:
    receipt_id: str
    task_name: str
    difficulty: str
    source_commit: str
    task_asset_validation_report_id: str
    semantic_validation_mode: str
    requested_seed: str
    effective_seed: str
    effective_simulator_seed: str
    process_exit_code: int
    environment_started: bool
    controller_started: bool
    actual_runtime_task_loaded: bool
    agent_target_name: str
    environment_target_name: str
    spawned_block_name: str
    controller_success_target_name: str
    evaluator_success_target_name: str
    inventory_name_field: str
    inventory_quantity_field: str
    evaluator_delegates_to_controller: bool
    success_condition_observed: bool
    controller_success_observed: bool
    evaluator_success_observed: bool
    controller_evaluator_agree: bool
    task_completed: bool
    provider_call_count: int
    formal_memory_used: bool
    excluded_from_formal_fitting: bool
    technical_failure_count: int
    trace_sha256: str
    observation_sha256: str
    notes: str = ""

    def __post_init__(self) -> None:
        if self.semantic_validation_mode not in {
            "controlled_success_fixture",
            "end_to_end_controller",
        }:
            raise ValueError("Unknown semantic validation mode")
        if self.difficulty not in DIFFICULTIES:
            raise ValueError("Unknown task difficulty")
        for value in (
            self.process_exit_code,
            self.provider_call_count,
            self.technical_failure_count,
        ):
            if isinstance(value, bool) or value < 0:
                raise ValueError("Receipt counts cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskSemanticSmokeReport:
    source_commit: str
    task_asset_validation_report_id: str
    required_tasks: tuple[str, ...]
    receipt_ids: tuple[str, ...]
    receipt_count: int
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    report_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported semantic-smoke schema")
        expected = self.compute_report_id()
        if self.report_id and self.report_id != expected:
            raise ValueError("Semantic-smoke report hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("report_id", None)
        payload["required_tasks"] = sorted(self.required_tasks)
        payload["receipt_ids"] = list(self.receipt_ids)
        payload["errors"] = list(self.errors)
        payload["warnings"] = list(self.warnings)
        return payload

    def compute_report_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "TaskSemanticSmokeReport":
        return replace(self, report_id=self.compute_report_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.report_id else self.with_id()
        payload = item.payload_without_id()
        payload["report_id"] = item.report_id
        return payload


def audit_task_semantics(
    receipts: Sequence[TaskSemanticReceipt],
    *,
    source_commit: str,
    task_asset_validation_report_id: str,
    required_tasks: Sequence[str] = tuple(sorted(REQUIRED_CRITICAL_TASKS)),
) -> TaskSemanticSmokeReport:
    errors: list[str] = []
    warnings: list[str] = []
    required = frozenset(required_tasks)
    by_task: dict[str, TaskSemanticReceipt] = {}

    for receipt in receipts:
        if receipt.task_name in by_task:
            errors.append(f"duplicate receipt for {receipt.task_name!r}")
        by_task[receipt.task_name] = receipt
        prefix = receipt.task_name
        if receipt.source_commit != source_commit:
            errors.append(f"{prefix}: source commit mismatch")
        if receipt.task_asset_validation_report_id != (
            task_asset_validation_report_id
        ):
            errors.append(f"{prefix}: task-asset report mismatch")
        if receipt.requested_seed != receipt.effective_seed:
            errors.append(f"{prefix}: requested/effective seed mismatch")
        if receipt.requested_seed != receipt.effective_simulator_seed:
            errors.append(f"{prefix}: requested/simulator seed mismatch")
        if receipt.process_exit_code != 0:
            errors.append(f"{prefix}: process exit code is nonzero")
        if not receipt.environment_started or not receipt.controller_started:
            errors.append(f"{prefix}: environment/controller did not start")
        if not receipt.actual_runtime_task_loaded:
            errors.append(f"{prefix}: actual runtime task did not load")
        if not all(
            (
                receipt.agent_target_name,
                receipt.environment_target_name,
                receipt.spawned_block_name,
                receipt.controller_success_target_name,
                receipt.evaluator_success_target_name,
                receipt.inventory_name_field,
                receipt.inventory_quantity_field,
            )
        ):
            errors.append(f"{prefix}: target identity is incomplete")
        if receipt.controller_success_target_name != receipt.evaluator_success_target_name:
            errors.append(f"{prefix}: Controller/Evaluator success targets differ")
        if receipt.inventory_name_field != "inventory.name":
            errors.append(f"{prefix}: unexpected inventory name field")
        if receipt.inventory_quantity_field != "inventory.quantity":
            errors.append(f"{prefix}: unexpected inventory quantity field")
        if not receipt.success_condition_observed:
            errors.append(f"{prefix}: success condition was not observed")
        if not receipt.controller_success_observed:
            errors.append(f"{prefix}: Controller success was not observed")
        if not receipt.evaluator_success_observed:
            errors.append(f"{prefix}: Evaluator success was not observed")
        if not receipt.controller_evaluator_agree:
            errors.append(f"{prefix}: Controller/Evaluator disagree")
        if not receipt.task_completed:
            errors.append(f"{prefix}: semantic harness did not complete the task")
        if receipt.formal_memory_used:
            errors.append(f"{prefix}: formal memory was used")
        if not receipt.excluded_from_formal_fitting:
            errors.append(f"{prefix}: semantic smoke was not excluded")
        if receipt.technical_failure_count:
            errors.append(f"{prefix}: technical failures recorded")
        if not receipt.trace_sha256 or not receipt.observation_sha256:
            errors.append(f"{prefix}: trace/observation hash is missing")
        if (
            receipt.semantic_validation_mode == "controlled_success_fixture"
            and receipt.provider_call_count != 0
        ):
            errors.append(
                f"{prefix}: controlled semantic fixture made provider calls"
            )
        if receipt.semantic_validation_mode == "end_to_end_controller":
            warnings.append(
                f"{prefix}: semantic evidence depends on Controller execution"
            )

    missing = required - set(by_task)
    extra = set(by_task) - required
    if missing:
        errors.append(f"missing critical task receipts: {sorted(missing)}")
    if extra:
        errors.append(f"unexpected task receipts: {sorted(extra)}")

    return TaskSemanticSmokeReport(
        source_commit=source_commit,
        task_asset_validation_report_id=task_asset_validation_report_id,
        required_tasks=tuple(sorted(required)),
        receipt_ids=tuple(
            by_task[name].receipt_id for name in sorted(by_task)
        ),
        receipt_count=len(receipts),
        eligible=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    ).with_id()


@dataclass(frozen=True)
class FinalTasksetRelease:
    release_name: str
    source_commit: str
    amendment_id: str
    task_asset_validation_report_id: str
    task_asset_validation_report_sha256: str
    task_semantic_smoke_report_id: str
    task_semantic_smoke_report_sha256: str
    catalog_sha256: str
    runtime_task_tree_sha256: str
    resolution_report_sha256: str
    task_count: int
    difficulty_counts: Mapping[str, int]
    environment_construction_count: int
    critical_task_count: int
    eligible: bool
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported final-taskset release schema")
        if not self.eligible:
            raise ValueError("Cannot freeze an ineligible final taskset")
        if self.task_count != 50 or self.environment_construction_count != 50:
            raise ValueError("Final taskset requires 50 tasks and 50 env smokes")
        if dict(self.difficulty_counts) != {
            difficulty: 10 for difficulty in DIFFICULTIES
        }:
            raise ValueError("Final taskset difficulty matrix is invalid")
        if self.critical_task_count != len(REQUIRED_CRITICAL_TASKS):
            raise ValueError("Critical semantic-smoke count is incomplete")
        required = (
            self.release_name,
            self.source_commit,
            self.amendment_id,
            self.task_asset_validation_report_id,
            self.task_asset_validation_report_sha256,
            self.task_semantic_smoke_report_id,
            self.task_semantic_smoke_report_sha256,
            self.catalog_sha256,
            self.runtime_task_tree_sha256,
            self.resolution_report_sha256,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Final-taskset release identity is incomplete")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("Final-taskset release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        payload["difficulty_counts"] = dict(sorted(self.difficulty_counts.items()))
        return payload

    def compute_release_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FinalTasksetRelease":
        return replace(self, release_id=self.compute_release_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.release_id else self.with_id()
        payload = item.payload_without_id()
        payload["release_id"] = item.release_id
        return payload


def build_final_taskset_release(
    *,
    release_name: str,
    source_commit: str,
    amendment: TasksetAmendment,
    task_asset_validation: Mapping[str, Any],
    task_asset_validation_path: str | Path,
    semantic_smoke: TaskSemanticSmokeReport,
    semantic_smoke_path: str | Path,
    resolution_report_path: str | Path,
) -> FinalTasksetRelease:
    amendment = amendment if amendment.amendment_id else amendment.with_id()
    semantic_smoke = (
        semantic_smoke if semantic_smoke.report_id else semantic_smoke.with_id()
    )
    if not task_asset_validation.get("eligible", False):
        raise ValueError("Task-asset validation is not eligible")
    if not semantic_smoke.eligible:
        raise ValueError("Critical task-semantic smoke is not eligible")
    if task_asset_validation.get("source_commit") != source_commit:
        raise ValueError("Task-asset source commit mismatch")
    if semantic_smoke.source_commit != source_commit:
        raise ValueError("Semantic-smoke source commit mismatch")
    if amendment.source_commit != source_commit:
        raise ValueError("Taskset amendment source commit mismatch")
    report_id = str(task_asset_validation.get("report_id", ""))
    if semantic_smoke.task_asset_validation_report_id != report_id:
        raise ValueError("Semantic-smoke/task-asset binding mismatch")

    return FinalTasksetRelease(
        release_name=release_name,
        source_commit=source_commit,
        amendment_id=amendment.amendment_id,
        task_asset_validation_report_id=report_id,
        task_asset_validation_report_sha256=sha256_file(
            task_asset_validation_path
        ),
        task_semantic_smoke_report_id=semantic_smoke.report_id,
        task_semantic_smoke_report_sha256=sha256_file(semantic_smoke_path),
        catalog_sha256=str(task_asset_validation.get("catalog_sha256", "")),
        runtime_task_tree_sha256=str(
            task_asset_validation.get("runtime_task_tree_sha256", "")
        ),
        resolution_report_sha256=sha256_file(resolution_report_path),
        task_count=int(task_asset_validation.get("task_count", 0)),
        difficulty_counts=dict(
            task_asset_validation.get("difficulty_counts", {})
        ),
        environment_construction_count=int(
            task_asset_validation.get("environment_construction_count", 0)
        ),
        critical_task_count=semantic_smoke.receipt_count,
        eligible=True,
    ).with_id()


def load_amendment(path: str | Path) -> TasksetAmendment:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["removed_tasks"] = tuple(payload["removed_tasks"])
    payload["added_tasks"] = tuple(payload["added_tasks"])
    return TasksetAmendment(**payload)


def load_semantic_receipt(path: str | Path) -> TaskSemanticReceipt:
    return TaskSemanticReceipt(
        **json.loads(Path(path).read_text(encoding="utf-8"))
    )


def load_semantic_report(path: str | Path) -> TaskSemanticSmokeReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    for name in ("required_tasks", "receipt_ids", "errors", "warnings"):
        payload[name] = tuple(payload.get(name, ()))
    return TaskSemanticSmokeReport(**payload)


def load_taskset_release(path: str | Path) -> FinalTasksetRelease:
    return FinalTasksetRelease(
        **json.loads(Path(path).read_text(encoding="utf-8"))
    )


def save_immutable(path: str | Path, payload: Mapping[str, Any]) -> None:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite immutable file: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
