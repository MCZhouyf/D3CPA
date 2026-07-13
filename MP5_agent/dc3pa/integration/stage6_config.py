from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

from ..errors import ContractValidationError
from ..memory.modes import MemoryMode


_RUNTIME_MODES = {"mp5_legacy", "reasoning_only", "dc3pa"}
_UNRESOLVED_POLICIES = {"block", "reasoning_only", "execute"}
_PLANNER_FAILURE_POLICIES = {"raise", "reasoning_only", "return_failure"}
_CONTROLLER_EXCEPTION_POLICIES = {"raise", "return_failure"}
_MEMORY_FAILURE_POLICIES = {"raise", "trace"}


def _strict_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ContractValidationError(f"{label} must be a bool")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractValidationError(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True)
class Stage6RuntimeConfig:
    """Closed-loop Stage-6 runtime policy.

    Defaults preserve commit 4ed2de4 behavior.  Paper acquisition must use a
    dedicated config that disables the legacy and online multimodal write paths.
    """

    mode: str = "dc3pa"
    max_execution_attempts: int = 30
    unresolved_plan_policy: str = "block"
    planner_failure_policy: str = "reasoning_only"
    controller_exception_policy: str = "return_failure"
    goal_check_exception_policy: str = "return_failure"
    memory_failure_policy: str = "trace"
    require_goal_check: bool = True
    record_legacy_workflow_memory: bool = True
    record_multimodal_memory: bool = True
    capture_initial_scene: bool = True
    capture_final_scene: bool = True

    memory_mode: str = MemoryMode.ACQUIRE.value
    telemetry_enabled: bool = False
    acquisition_log_dir: str = ""
    calibration_log_dir: str = ""
    memory_snapshot_manifest: str = ""

    def validate(self) -> None:
        if self.mode not in _RUNTIME_MODES:
            raise ContractValidationError(
                f"mode must be one of {sorted(_RUNTIME_MODES)}, got {self.mode!r}"
            )
        _positive_int(self.max_execution_attempts, "max_execution_attempts")
        if self.unresolved_plan_policy not in _UNRESOLVED_POLICIES:
            raise ContractValidationError(
                "unresolved_plan_policy must be 'block', 'reasoning_only', or 'execute'"
            )
        if self.planner_failure_policy not in _PLANNER_FAILURE_POLICIES:
            raise ContractValidationError(
                "planner_failure_policy must be 'raise', 'reasoning_only', or 'return_failure'"
            )
        if self.controller_exception_policy not in _CONTROLLER_EXCEPTION_POLICIES:
            raise ContractValidationError(
                "controller_exception_policy must be 'raise' or 'return_failure'"
            )
        if self.goal_check_exception_policy not in _CONTROLLER_EXCEPTION_POLICIES:
            raise ContractValidationError(
                "goal_check_exception_policy must be 'raise' or 'return_failure'"
            )
        if self.memory_failure_policy not in _MEMORY_FAILURE_POLICIES:
            raise ContractValidationError(
                "memory_failure_policy must be 'raise' or 'trace'"
            )

        for label in (
            "require_goal_check",
            "record_legacy_workflow_memory",
            "record_multimodal_memory",
            "capture_initial_scene",
            "capture_final_scene",
            "telemetry_enabled",
        ):
            _strict_bool(getattr(self, label), label)

        try:
            memory_mode = MemoryMode.parse(self.memory_mode)
        except ValueError as exc:
            raise ContractValidationError(str(exc)) from exc

        if memory_mode is not MemoryMode.ACQUIRE and (
            self.record_legacy_workflow_memory or self.record_multimodal_memory
        ):
            raise ContractValidationError(
                "calibrate/evaluate_readonly/disabled modes must set both "
                "record_legacy_workflow_memory=false and "
                "record_multimodal_memory=false"
            )

        if memory_mode.requires_frozen_snapshot and not self.memory_snapshot_manifest:
            raise ContractValidationError(
                f"memory_mode={memory_mode.value!r} requires memory_snapshot_manifest"
            )

        if self.acquisition_log_dir and memory_mode is not MemoryMode.ACQUIRE:
            raise ContractValidationError(
                "acquisition_log_dir is only valid in memory_mode='acquire'"
            )

        if self.calibration_log_dir and memory_mode not in {
            MemoryMode.ACQUIRE,
            MemoryMode.CALIBRATE,
        }:
            raise ContractValidationError(
                "calibration_log_dir is only valid in memory_mode='acquire' or 'calibrate'"
            )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Stage6RuntimeConfig":
        allowed = set(cls.__dataclass_fields__)
        unknown = set(data) - allowed
        if unknown:
            raise ContractValidationError(
                f"Unknown Stage6RuntimeConfig fields: {sorted(unknown)}"
            )
        config = cls(**dict(data))
        config.validate()
        return config

    @classmethod
    def from_json_file(cls, path: str | Path) -> "Stage6RuntimeConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ContractValidationError("Stage-6 config JSON must be an object")
        runtime_payload = payload.get("runtime", payload)
        if not isinstance(runtime_payload, Mapping):
            raise ContractValidationError("runtime config must be an object")
        return cls.from_mapping(runtime_payload)

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return asdict(self)
