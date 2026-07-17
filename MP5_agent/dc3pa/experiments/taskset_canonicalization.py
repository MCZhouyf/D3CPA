"""Canonical active taskset release for the pressure-plate benchmark.

The active benchmark fully replaces `mine sand` with
`craft wooden pressure plate`. Immutable historical artifacts are not edited in
place; instead, a new active artifact tree and release supersede them.

This module scans only explicitly listed active artifacts. Git history and
archived historical evidence may retain the previous task name, but no artifact
used by subsequent experiments may do so.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
OLD_TASK = "mine sand"
NEW_TASK = "craft wooden pressure plate"
EXPECTED_TASK_COUNT = 50
DIFFICULTIES = ("basic", "easy", "medium", "hard", "complex")
EXPECTED_PRESSURE_PLATE_ACQUISITION_SUCCESSES = 4

SUPPORTED_SUFFIXES = frozenset(
    {".json", ".jsonl", ".csv", ".md", ".txt", ".yaml", ".yml"}
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


def _walk_exact_strings(value: Any, *, pointer: str = "$"):
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk_exact_strings(item, pointer=f"{pointer}.{key}")
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, item in enumerate(value):
            yield from _walk_exact_strings(item, pointer=f"{pointer}[{index}]")


@dataclass(frozen=True)
class ActiveArtifactDescriptor:
    label: str
    path: str
    artifact_kind: str
    required_new_task_presence: bool
    immutable_historical_archive: bool = False

    def __post_init__(self) -> None:
        if not self.label or not self.path or not self.artifact_kind:
            raise ValueError("Active artifact descriptor is incomplete")
        if self.immutable_historical_archive:
            raise ValueError(
                "Historical archives cannot be listed as active artifacts"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskReferenceScan:
    label: str
    path: str
    artifact_kind: str
    file_sha256: str
    old_task_exact_occurrences: int
    new_task_exact_occurrences: int
    old_task_locations: tuple[str, ...]
    new_task_locations: tuple[str, ...]
    parser: str
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["old_task_locations"] = list(self.old_task_locations)
        payload["new_task_locations"] = list(self.new_task_locations)
        return payload


def scan_artifact(
    descriptor: ActiveArtifactDescriptor,
    *,
    root: str | Path,
) -> TaskReferenceScan:
    base = Path(root).resolve()
    path = (base / descriptor.path).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Artifact escapes active root: {path}") from exc
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported active artifact format: {path}")

    old_locations: list[str] = []
    new_locations: list[str] = []
    parser = suffix.lstrip(".")

    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        for pointer, value in _walk_exact_strings(payload):
            if value == OLD_TASK:
                old_locations.append(pointer)
            elif value == NEW_TASK:
                new_locations.append(pointer)
    elif suffix == ".jsonl":
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            payload = json.loads(line)
            for pointer, value in _walk_exact_strings(
                payload, pointer=f"$line[{line_number}]"
            ):
                if value == OLD_TASK:
                    old_locations.append(pointer)
                elif value == NEW_TASK:
                    new_locations.append(pointer)
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for row_index, row in enumerate(reader, start=1):
                for column_index, value in enumerate(row, start=1):
                    stripped = value.strip()
                    if stripped == OLD_TASK:
                        old_locations.append(f"row={row_index},col={column_index}")
                    elif stripped == NEW_TASK:
                        new_locations.append(f"row={row_index},col={column_index}")
    else:
        # Text formats are scanned for exact phrase occurrences. These are
        # documentation/config formats, not structured scientific records.
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            old_count = line.count(OLD_TASK)
            new_count = line.count(NEW_TASK)
            old_locations.extend([f"line={line_number}"] * old_count)
            new_locations.extend([f"line={line_number}"] * new_count)

    return TaskReferenceScan(
        label=descriptor.label,
        path=descriptor.path,
        artifact_kind=descriptor.artifact_kind,
        file_sha256=sha256_file(path),
        old_task_exact_occurrences=len(old_locations),
        new_task_exact_occurrences=len(new_locations),
        old_task_locations=tuple(old_locations),
        new_task_locations=tuple(new_locations),
        parser=parser,
    )


def load_catalog(path: str | Path) -> tuple[dict[str, Any], ...]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = {"task", "difficulty", "minimum_subgoals"}
        if set(reader.fieldnames or ()) != expected:
            raise ValueError(
                f"Catalog columns must be exactly {sorted(expected)}"
            )
        rows = []
        for row in reader:
            rows.append(
                {
                    "task": str(row["task"]).strip(),
                    "difficulty": str(row["difficulty"]).strip().lower(),
                    "minimum_subgoals": int(row["minimum_subgoals"]),
                }
            )
    if len(rows) != EXPECTED_TASK_COUNT:
        raise ValueError(f"Expected 50 tasks, found {len(rows)}")
    if len({row["task"] for row in rows}) != EXPECTED_TASK_COUNT:
        raise ValueError("Task catalog contains duplicate names")
    if sum(row["task"] == OLD_TASK for row in rows):
        raise ValueError("Active catalog still contains mine sand")
    if sum(row["task"] == NEW_TASK for row in rows) != 1:
        raise ValueError(
            "Active catalog must contain craft wooden pressure plate exactly once"
        )
    counts = {
        difficulty: sum(row["difficulty"] == difficulty for row in rows)
        for difficulty in DIFFICULTIES
    }
    if counts != {difficulty: 10 for difficulty in DIFFICULTIES}:
        raise ValueError(f"Difficulty matrix is not 10×5: {counts}")
    return tuple(rows)


@dataclass(frozen=True)
class PressurePlateCanonicalizationReport:
    source_commit: str
    acquisition_source_commit: str
    active_root_sha256: str
    catalog_sha256: str
    active_artifact_count: int
    old_task_total_occurrences: int
    new_task_total_occurrences: int
    required_artifacts_with_new_task: int
    required_artifact_count: int
    task_count: int
    difficulty_counts: Mapping[str, int]
    pressure_plate_acquisition_successes: int
    scans: tuple[TaskReferenceScan, ...]
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    report_id: str = ""

    def __post_init__(self) -> None:
        expected = self.compute_report_id()
        if self.report_id and self.report_id != expected:
            raise ValueError("Canonicalization report hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("report_id", None)
        payload["difficulty_counts"] = dict(sorted(self.difficulty_counts.items()))
        payload["scans"] = [item.to_dict() for item in self.scans]
        payload["errors"] = list(self.errors)
        payload["warnings"] = list(self.warnings)
        return payload

    def compute_report_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "PressurePlateCanonicalizationReport":
        return replace(self, report_id=self.compute_report_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.report_id else self.with_id()
        payload = item.payload_without_id()
        payload["report_id"] = item.report_id
        return payload


def audit_active_taskset(
    *,
    source_commit: str,
    acquisition_source_commit: str,
    active_root: str | Path,
    catalog_path: str | Path,
    descriptors: Sequence[ActiveArtifactDescriptor],
    acquisition_audit_path: str | Path,
) -> PressurePlateCanonicalizationReport:
    errors: list[str] = []
    warnings: list[str] = []
    catalog = load_catalog(catalog_path)
    scans = tuple(
        scan_artifact(descriptor, root=active_root)
        for descriptor in descriptors
    )

    old_total = sum(item.old_task_exact_occurrences for item in scans)
    new_total = sum(item.new_task_exact_occurrences for item in scans)
    required_count = sum(
        descriptor.required_new_task_presence for descriptor in descriptors
    )
    required_with_new = 0
    descriptor_map = {descriptor.label: descriptor for descriptor in descriptors}
    for scan in scans:
        descriptor = descriptor_map[scan.label]
        if scan.old_task_exact_occurrences:
            errors.append(
                f"{scan.label}: active artifact contains {OLD_TASK!r} at "
                f"{list(scan.old_task_locations)}"
            )
        if descriptor.required_new_task_presence:
            if scan.new_task_exact_occurrences <= 0:
                errors.append(
                    f"{scan.label}: required pressure-plate task is absent"
                )
            else:
                required_with_new += 1

    audit = json.loads(Path(acquisition_audit_path).read_text(encoding="utf-8"))
    if not isinstance(audit, Mapping):
        raise ValueError("Acquisition audit must contain a JSON object")
    success_by_task = audit.get("success_by_task", {})
    if not isinstance(success_by_task, Mapping):
        errors.append("Acquisition audit success_by_task is malformed")
        pressure_plate_successes = -1
    else:
        pressure_plate_successes = int(success_by_task.get(NEW_TASK, 0) or 0)
        if OLD_TASK in success_by_task:
            errors.append("Acquisition audit still contains mine sand")
        if (
            pressure_plate_successes
            != EXPECTED_PRESSURE_PLATE_ACQUISITION_SUCCESSES
        ):
            errors.append(
                "Pressure-plate acquisition success count differs from the "
                f"frozen result: {pressure_plate_successes}"
            )

    counts = {
        difficulty: sum(row["difficulty"] == difficulty for row in catalog)
        for difficulty in DIFFICULTIES
    }
    file_hashes = {
        item.path: item.file_sha256 for item in sorted(scans, key=lambda x: x.path)
    }
    active_root_hash = _sha(file_hashes)

    if not descriptors:
        errors.append("No active artifacts were supplied")
    if old_total:
        errors.append("Active artifact set still contains mine sand")
    if required_with_new != required_count:
        errors.append("Not all required artifacts contain pressure plate")

    return PressurePlateCanonicalizationReport(
        source_commit=source_commit,
        acquisition_source_commit=acquisition_source_commit,
        active_root_sha256=active_root_hash,
        catalog_sha256=sha256_file(catalog_path),
        active_artifact_count=len(scans),
        old_task_total_occurrences=old_total,
        new_task_total_occurrences=new_total,
        required_artifacts_with_new_task=required_with_new,
        required_artifact_count=required_count,
        task_count=len(catalog),
        difficulty_counts=counts,
        pressure_plate_acquisition_successes=pressure_plate_successes,
        scans=scans,
        eligible=not errors,
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(dict.fromkeys(warnings)),
    ).with_id()


@dataclass(frozen=True)
class ActivePressurePlateTasksetRelease:
    release_name: str
    source_commit: str
    acquisition_source_commit: str
    canonicalization_report_id: str
    active_root_sha256: str
    catalog_sha256: str
    acquisition_audit_id: str
    acquisition_root_sha256: str
    pressure_plate_task_name: str
    old_task_name: str
    pressure_plate_acquisition_successes: int
    active_task_count: int
    active_difficulty_counts: Mapping[str, int]
    historical_artifacts_mutated: bool
    active_artifacts_fully_replaced: bool
    eligible: bool
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        if not self.eligible:
            raise ValueError("Cannot freeze an ineligible taskset release")
        if self.pressure_plate_task_name != NEW_TASK:
            raise ValueError("Canonical task name is incorrect")
        if self.old_task_name != OLD_TASK:
            raise ValueError("Superseded task name is incorrect")
        if self.historical_artifacts_mutated:
            raise ValueError("Immutable historical artifacts must not be edited")
        if not self.active_artifacts_fully_replaced:
            raise ValueError("Active artifact replacement is incomplete")
        if self.active_task_count != EXPECTED_TASK_COUNT:
            raise ValueError("Active task count is not 50")
        if dict(self.active_difficulty_counts) != {
            difficulty: 10 for difficulty in DIFFICULTIES
        }:
            raise ValueError("Active difficulty matrix is invalid")
        if (
            self.pressure_plate_acquisition_successes
            != EXPECTED_PRESSURE_PLATE_ACQUISITION_SUCCESSES
        ):
            raise ValueError("Pressure-plate acquisition result is inconsistent")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("Active taskset release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        payload["active_difficulty_counts"] = dict(
            sorted(self.active_difficulty_counts.items())
        )
        return payload

    def compute_release_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "ActivePressurePlateTasksetRelease":
        return replace(self, release_id=self.compute_release_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.release_id else self.with_id()
        payload = item.payload_without_id()
        payload["release_id"] = item.release_id
        return payload
