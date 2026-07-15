"""Deterministic block-interleaved method schedule."""

from __future__ import annotations
import hashlib, json
from dataclasses import asdict, dataclass, replace
from typing import Any, Sequence

SCHEMA_VERSION = 1
DEFAULT_SALT = "dc3pa-gpt51-interleaved-method-schedule-v1"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def hint(*parts: Any) -> int:
    return int.from_bytes(
        hashlib.sha256("\x1f".join(str(x) for x in parts).encode()).digest()[:8],
        "big",
    )


@dataclass(frozen=True)
class MethodSpec:
    method_id: str
    display_name: str
    provider_profile_id: str
    controller_profile: str
    memory_policy: str
    cognitive_control_mode: str
    implementation_commit: str
    ready: bool
    readiness_artifact_id: str = ""
    notes: str = ""

    def __post_init__(self):
        if not self.method_id or not self.display_name:
            raise ValueError("Method identity is required")
        if self.ready and not self.readiness_artifact_id:
            raise ValueError("Ready method needs a readiness artifact")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class EvaluationUnit:
    task: str
    seed: str
    difficulty: str
    block_id: str

    def __post_init__(self):
        if not self.task or not self.seed or not self.block_id:
            raise ValueError("Evaluation unit identity is required")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ScheduledRun:
    run_index: int
    block_id: str
    position_in_block: int
    task: str
    seed: str
    difficulty: str
    method_id: str

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ExecutionSchedule:
    schedule_name: str
    blueprint_id: str
    source_commit: str
    model_profile_id: str
    methods: tuple[MethodSpec, ...]
    units: tuple[EvaluationUnit, ...]
    runs: tuple[ScheduledRun, ...]
    schedule_salt: str = DEFAULT_SALT
    schema_version: int = SCHEMA_VERSION
    schedule_id: str = ""

    def __post_init__(self):
        if not self.methods or not self.units or not self.runs:
            raise ValueError("Schedule is incomplete")
        if any(not item.ready for item in self.methods):
            raise ValueError("Unready methods cannot be scheduled")
        ids = [item.method_id for item in self.methods]
        if len(ids) != len(set(ids)):
            raise ValueError("Method IDs must be unique")
        self.validate_balance()
        expected = self.compute_id()
        if self.schedule_id and self.schedule_id != expected:
            raise ValueError("Schedule hash mismatch")

    def validate_balance(self):
        expected = {item.method_id for item in self.methods}
        blocks = {}
        for run in self.runs:
            blocks.setdefault(run.block_id, []).append(run)
        if set(blocks) != {item.block_id for item in self.units}:
            raise ValueError("Block set mismatch")
        for block_id, runs in blocks.items():
            if {item.method_id for item in runs} != expected:
                raise ValueError(f"{block_id}: method imbalance")
            if sorted(item.position_in_block for item in runs) != list(range(len(expected))):
                raise ValueError(f"{block_id}: invalid positions")
            if len({(item.task, item.seed) for item in runs}) != 1:
                raise ValueError(f"{block_id}: mixed task-seed")
        if [item.run_index for item in self.runs] != list(range(len(self.runs))):
            raise ValueError("Run indices are not contiguous")

    def payload(self):
        return {
            "schedule_name": self.schedule_name,
            "blueprint_id": self.blueprint_id,
            "source_commit": self.source_commit,
            "model_profile_id": self.model_profile_id,
            "methods": [item.to_dict() for item in
                        sorted(self.methods, key=lambda x: x.method_id)],
            "units": [item.to_dict() for item in
                      sorted(self.units, key=lambda x: x.block_id)],
            "runs": [item.to_dict() for item in self.runs],
            "schedule_salt": self.schedule_salt,
            "schema_version": self.schema_version,
        }

    def compute_id(self):
        return hashlib.sha256(canonical(self.payload())).hexdigest()

    def with_id(self):
        return replace(self, schedule_id=self.compute_id())

    def to_dict(self):
        value = self.payload()
        value["schedule_id"] = self.schedule_id or self.compute_id()
        return value


def build_schedule(*, schedule_name: str, blueprint_id: str,
                   source_commit: str, model_profile_id: str,
                   methods: Sequence[MethodSpec],
                   units: Sequence[EvaluationUnit],
                   schedule_salt: str = DEFAULT_SALT) -> ExecutionSchedule:
    method_items = tuple(sorted(methods, key=lambda x: x.method_id))
    unit_items = tuple(sorted(units, key=lambda x: x.block_id))
    base = sorted(
        (item.method_id for item in method_items),
        key=lambda method: hint(schedule_salt, "base", method),
    )
    runs = []
    run_index = 0
    for unit in unit_items:
        rotation = hint(schedule_salt, unit.task, unit.seed, unit.block_id) % len(base)
        order = base[rotation:] + base[:rotation]
        if hint(schedule_salt, "reverse", unit.block_id) % 2:
            order = list(reversed(order))
        for position, method_id in enumerate(order):
            runs.append(ScheduledRun(
                run_index=run_index,
                block_id=unit.block_id,
                position_in_block=position,
                task=unit.task,
                seed=unit.seed,
                difficulty=unit.difficulty,
                method_id=method_id,
            ))
            run_index += 1
    return ExecutionSchedule(
        schedule_name=schedule_name,
        blueprint_id=blueprint_id,
        source_commit=source_commit,
        model_profile_id=model_profile_id,
        methods=method_items,
        units=unit_items,
        runs=tuple(runs),
        schedule_salt=schedule_salt,
    ).with_id()
