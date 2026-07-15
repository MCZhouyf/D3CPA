"""Compile and validate the author-approved 50-task asset set.

The module produces:
- current creative-task JSON files matching the repository's existing schema;
- formal task descriptors for the current Evaluator/Stage6 adapter;
- a registry-resolution report.

Candidate names and recipes are not treated as runtime truth. In paper mode,
every target/tool/platform/material name must resolve uniquely through the
actual environment registry and every formal descriptor must pass the current
Evaluator/task loader. Zero or multiple matches fail closed.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence


TASK_ASSET_SCHEMA_VERSION = 1
EXPECTED_DIFFICULTIES = ("basic", "easy", "medium", "hard", "complex")
CREATIVE_FIELDS = ("task", "quantity", "material", "tool", "platform")
APPROVED_SOURCE_COMMIT = "57ab59d8cb99edb448fabc7cb74aea8d587e9341"


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


def verify_author_input_manifest(root: str | Path) -> Mapping[str, Any]:
    source = Path(root)
    manifest_path = source / "author_input_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("author_team") != "ZYF":
        raise ValueError("Author input manifest is not approved by ZYF")
    if manifest.get("source_commit") != APPROVED_SOURCE_COMMIT:
        raise ValueError("Author input manifest source commit mismatch")
    if manifest.get("task_count") != 50:
        raise ValueError("Author input manifest must declare 50 tasks")
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("Author input manifest has no file records")
    declared = {str(item.get("path", "")) for item in records}
    actual = {
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if declared != actual:
        raise ValueError(
            "Author input file set mismatch; "
            f"missing={sorted(declared-actual)}, extra={sorted(actual-declared)}"
        )
    for item in records:
        path = source / str(item["path"])
        if path.stat().st_size != int(item["size_bytes"]):
            raise ValueError(f"Author input size mismatch: {item['path']}")
        if sha256_file(path) != str(item["sha256"]):
            raise ValueError(f"Author input SHA-256 mismatch: {item['path']}")
    return manifest


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).replace("_", " ").strip().lower())


@dataclass(frozen=True)
class CatalogTask:
    task_name: str
    difficulty: str
    minimum_subgoals: int
    creative_file: str
    formal_spec_file: str

    def __post_init__(self) -> None:
        if not self.task_name.strip():
            raise ValueError("task_name is required")
        if self.difficulty not in EXPECTED_DIFFICULTIES:
            raise ValueError(f"Unknown difficulty {self.difficulty!r}")
        if isinstance(self.minimum_subgoals, bool) or self.minimum_subgoals <= 0:
            raise ValueError("minimum_subgoals must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegistryResolution:
    source_name: str
    normalized_name: str
    match_count: int
    matched_runtime_names: tuple[str, ...]
    resolved_runtime_name: str = ""
    resolved_runtime_id: str = ""
    status: str = "unresolved"

    def __post_init__(self) -> None:
        if self.status not in {"resolved", "unresolved", "ambiguous"}:
            raise ValueError("Invalid resolution status")
        if self.status == "resolved":
            if self.match_count != 1:
                raise ValueError("Resolved status needs one match")
            if not self.resolved_runtime_name:
                raise ValueError("Resolved runtime name is required")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["matched_runtime_names"] = list(self.matched_runtime_names)
        return payload


@dataclass(frozen=True)
class TaskAssetValidationReport:
    task_count: int
    difficulty_counts: Mapping[str, int]
    creative_schema_valid: bool
    formal_schema_valid: bool
    registry_resolution_count: int
    registry_ambiguous_count: int
    registry_unresolved_count: int
    evaluator_load_count: int
    environment_construction_count: int
    expected_task_count: int
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    catalog_sha256: str
    creative_tree_sha256: str
    formal_tree_sha256: str
    runtime_registry_sha256: str = ""
    runtime_task_tree_sha256: str = ""
    source_commit: str = APPROVED_SOURCE_COMMIT
    schema_version: int = TASK_ASSET_SCHEMA_VERSION
    report_id: str = ""

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("report_id", None)
        payload["difficulty_counts"] = dict(sorted(self.difficulty_counts.items()))
        payload["errors"] = list(self.errors)
        payload["warnings"] = list(self.warnings)
        return payload

    def compute_report_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "TaskAssetValidationReport":
        return replace(self, report_id=self.compute_report_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.report_id else self.with_id()
        payload = item.payload_without_id()
        payload["report_id"] = item.report_id
        return payload


def load_catalog(
    catalog_path: str | Path,
    mapping_manifest_path: str | Path,
) -> tuple[CatalogTask, ...]:
    mapping = json.loads(Path(mapping_manifest_path).read_text(encoding="utf-8"))
    by_name = {
        item["task_name"]: item for item in mapping.get("tasks", [])
    }
    result: list[CatalogTask] = []
    with Path(catalog_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != (
            "task",
            "difficulty",
            "minimum_subgoals",
        ):
            raise ValueError("Unexpected task catalog columns")
        for row in reader:
            task_name = str(row["task"]).strip()
            mapped = by_name.get(task_name)
            if mapped is None:
                raise ValueError(f"Missing mapping entry for {task_name!r}")
            result.append(
                CatalogTask(
                    task_name=task_name,
                    difficulty=str(row["difficulty"]).strip().lower(),
                    minimum_subgoals=int(row["minimum_subgoals"]),
                    creative_file=str(mapped["creative_file"]),
                    formal_spec_file=str(mapped["formal_spec"]),
                )
            )
    if len(result) != 50 or len({item.task_name for item in result}) != 50:
        raise ValueError("Formal catalog must contain exactly 50 unique tasks")
    counts = {
        difficulty: sum(item.difficulty == difficulty for item in result)
        for difficulty in EXPECTED_DIFFICULTIES
    }
    if any(counts[difficulty] != 10 for difficulty in EXPECTED_DIFFICULTIES):
        raise ValueError(f"Expected 10 tasks per difficulty, found {counts}")
    return tuple(result)


def validate_creative_payload(payload: Any, *, label: str) -> None:
    if not isinstance(payload, list) or len(payload) != 1:
        raise ValueError(f"{label}: creative payload must contain one object")
    item = payload[0]
    if not isinstance(item, Mapping):
        raise ValueError(f"{label}: creative entry must be an object")
    if tuple(item.keys()) != CREATIVE_FIELDS:
        raise ValueError(
            f"{label}: creative fields must be exactly {CREATIVE_FIELDS}"
        )
    if not normalize_name(item["task"]):
        raise ValueError(f"{label}: task target is empty")
    quantity = item["quantity"]
    if isinstance(quantity, bool) or int(quantity) <= 0:
        raise ValueError(f"{label}: quantity must be positive")
    material = item["material"]
    if material is not None:
        if not isinstance(material, Mapping) or not material:
            raise ValueError(f"{label}: material must be null or nonempty object")
        for name, count in material.items():
            if not normalize_name(name):
                raise ValueError(f"{label}: material name is empty")
            if isinstance(count, bool) or int(count) <= 0:
                raise ValueError(f"{label}: material count must be positive")
    for field in ("tool", "platform"):
        value = item[field]
        if value is not None and not normalize_name(value):
            raise ValueError(f"{label}: {field} is empty")


def validate_formal_payload(payload: Any, *, label: str) -> None:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label}: formal task spec must be an object")
    required = {
        "schema_version",
        "task_id",
        "task_name",
        "difficulty",
        "minimum_subgoals",
        "operation",
        "target",
        "success_condition",
        "creative_task_file",
        "registry_validation_required",
        "source",
    }
    if set(payload) != required:
        raise ValueError(
            f"{label}: formal fields mismatch; "
            f"missing={sorted(required-set(payload))}, "
            f"extra={sorted(set(payload)-required)}"
        )
    if payload["difficulty"] not in EXPECTED_DIFFICULTIES:
        raise ValueError(f"{label}: invalid difficulty")
    if not payload["registry_validation_required"]:
        raise ValueError(f"{label}: registry validation must be required")
    target = payload["target"]
    if not isinstance(target, Mapping) or not normalize_name(
        target.get("candidate_item_name", "")
    ):
        raise ValueError(f"{label}: target candidate is invalid")
    success = payload["success_condition"]
    if not isinstance(success, Mapping) or not success.get(
        "must_be_resolved_against_current_evaluator"
    ):
        raise ValueError(f"{label}: success condition must require resolution")


def tree_sha256(root: str | Path) -> str:
    root_path = Path(root)
    records = []
    for path in sorted(root_path.rglob("*.json")):
        records.append(
            {
                "path": str(path.relative_to(root_path)),
                "sha256": sha256_file(path),
            }
        )
    return _sha(records)


def collect_referenced_names(
    creative_payloads: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    names: set[str] = set()
    for item in creative_payloads:
        names.add(normalize_name(item["task"]))
        for field in ("tool", "platform"):
            if item.get(field):
                names.add(normalize_name(item[field]))
        for name in (item.get("material") or {}):
            names.add(normalize_name(name))
    return tuple(sorted(names))


def resolve_registry_names(
    referenced_names: Sequence[str],
    runtime_entries: Sequence[Mapping[str, Any]],
) -> tuple[RegistryResolution, ...]:
    """Resolve names against runtime registry entries.

    Each runtime entry must include `name`; optional `id` is recorded. Exact
    normalized equality is required in paper mode. Fuzzy matching is forbidden.
    """

    normalized_runtime: dict[str, list[Mapping[str, Any]]] = {}
    for entry in runtime_entries:
        name = normalize_name(entry.get("name", ""))
        if not name:
            continue
        normalized_runtime.setdefault(name, []).append(entry)

    resolutions: list[RegistryResolution] = []
    for source in referenced_names:
        normalized = normalize_name(source)
        matches = normalized_runtime.get(normalized, [])
        if len(matches) == 1:
            match = matches[0]
            resolutions.append(
                RegistryResolution(
                    source_name=source,
                    normalized_name=normalized,
                    match_count=1,
                    matched_runtime_names=(str(match["name"]),),
                    resolved_runtime_name=str(match["name"]),
                    resolved_runtime_id=str(match.get("id", "")),
                    status="resolved",
                )
            )
        elif not matches:
            resolutions.append(
                RegistryResolution(
                    source_name=source,
                    normalized_name=normalized,
                    match_count=0,
                    matched_runtime_names=(),
                    status="unresolved",
                )
            )
        else:
            resolutions.append(
                RegistryResolution(
                    source_name=source,
                    normalized_name=normalized,
                    match_count=len(matches),
                    matched_runtime_names=tuple(str(item["name"]) for item in matches),
                    status="ambiguous",
                )
            )
    return tuple(resolutions)


def validate_task_assets(
    *,
    catalog_path: str | Path,
    mapping_manifest_path: str | Path,
    asset_root: str | Path,
    runtime_registry_entries: Optional[Sequence[Mapping[str, Any]]] = None,
    evaluator_loader: Optional[Callable[[Path], Any]] = None,
    environment_smoke: Optional[Callable[[Path], Any]] = None,
) -> tuple[TaskAssetValidationReport, tuple[RegistryResolution, ...]]:
    catalog = load_catalog(catalog_path, mapping_manifest_path)
    root = Path(asset_root)
    errors: list[str] = []
    warnings: list[str] = []
    creative_entries: list[Mapping[str, Any]] = []
    evaluator_load_count = 0
    environment_construction_count = 0
    loaded_runtime_tasks: list[Mapping[str, Any]] = []
    formal_paths: list[Path] = []

    for task in catalog:
        creative_path = root / task.creative_file
        formal_path = root / task.formal_spec_file
        try:
            creative = json.loads(creative_path.read_text(encoding="utf-8"))
            validate_creative_payload(creative, label=task.task_name)
            creative_entries.append(creative[0])
        except Exception as exc:
            errors.append(f"{task.task_name}: creative validation failed: {exc}")
        try:
            formal = json.loads(formal_path.read_text(encoding="utf-8"))
            validate_formal_payload(formal, label=task.task_name)
            if formal["task_name"] != task.task_name:
                errors.append(f"{task.task_name}: formal task name mismatch")
            if formal["difficulty"] != task.difficulty:
                errors.append(f"{task.task_name}: formal difficulty mismatch")
            if int(formal["minimum_subgoals"]) != task.minimum_subgoals:
                errors.append(f"{task.task_name}: formal subgoal mismatch")
            if evaluator_loader is not None:
                loaded = evaluator_loader(formal_path)
                loaded_runtime_tasks.append(
                    {"task_name": task.task_name, "payload": loaded}
                )
                evaluator_load_count += 1
                formal_paths.append(formal_path)
        except Exception as exc:
            errors.append(f"{task.task_name}: formal validation/load failed: {exc}")

    resolutions: tuple[RegistryResolution, ...] = ()
    registry_sha = ""
    if runtime_registry_entries is None:
        warnings.append(
            "Runtime registry was not supplied; formal readiness remains ineligible"
        )
    else:
        registry_sha = _sha(list(runtime_registry_entries))
        resolutions = resolve_registry_names(
            collect_referenced_names(creative_entries),
            runtime_registry_entries,
        )
        for item in resolutions:
            if item.status != "resolved":
                errors.append(
                    f"registry {item.status}: {item.source_name!r}; "
                    f"matches={list(item.matched_runtime_names)}"
                )

    if environment_smoke is None:
        warnings.append(
            "Environment construction smoke was not supplied; formal readiness "
            "remains ineligible"
        )
    elif resolutions and all(item.status == "resolved" for item in resolutions):
        for formal_path in formal_paths:
            try:
                environment_smoke(formal_path)
                environment_construction_count += 1
            except Exception as exc:
                errors.append(
                    f"{formal_path.stem}: environment construction failed: {exc}"
                )

    counts = {
        difficulty: sum(item.difficulty == difficulty for item in catalog)
        for difficulty in EXPECTED_DIFFICULTIES
    }
    unresolved = sum(item.status == "unresolved" for item in resolutions)
    ambiguous = sum(item.status == "ambiguous" for item in resolutions)
    resolved = sum(item.status == "resolved" for item in resolutions)
    report = TaskAssetValidationReport(
        task_count=len(catalog),
        difficulty_counts=counts,
        creative_schema_valid=not any(
            "creative validation" in item for item in errors
        ),
        formal_schema_valid=not any(
            "formal validation" in item for item in errors
        ),
        registry_resolution_count=resolved,
        registry_ambiguous_count=ambiguous,
        registry_unresolved_count=unresolved,
        evaluator_load_count=evaluator_load_count,
        environment_construction_count=environment_construction_count,
        expected_task_count=50,
        eligible=(
            not errors
            and runtime_registry_entries is not None
            and resolved > 0
            and evaluator_loader is not None
            and evaluator_load_count == 50
            and environment_smoke is not None
            and environment_construction_count == 50
        ),
        errors=tuple(errors),
        warnings=tuple(warnings),
        catalog_sha256=sha256_file(catalog_path),
        creative_tree_sha256=tree_sha256(root / "creative_task_jsons"),
        formal_tree_sha256=tree_sha256(root / "formal_task_specs"),
        runtime_registry_sha256=registry_sha,
        runtime_task_tree_sha256=_sha(loaded_runtime_tasks),
    ).with_id()
    return report, resolutions
