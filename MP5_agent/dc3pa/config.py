from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .errors import ContractValidationError


@dataclass(frozen=True)
class FeatureFlags:
    """Research controls that must be explicit in every run manifest."""

    legacy_task_hacks: bool = True
    controller_low_level_recovery: bool = True
    legacy_workflow_memory: bool = True
    dc3pa_memory: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "FeatureFlags":
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        unknown = set(data) - allowed
        if unknown:
            raise ContractValidationError(f"Unknown feature flags: {sorted(unknown)}")
        for key, value in data.items():
            if not isinstance(value, bool):
                raise ContractValidationError(
                    f"Feature flag {key!r} must be a JSON boolean, got {type(value).__name__}"
                )
        return cls(**dict(data))

    def to_environment(self) -> Dict[str, str]:
        truth = lambda value: "1" if value else "0"
        return {
            "DC3PA_LEGACY_TASK_HACKS": truth(self.legacy_task_hacks),
            "DC3PA_CONTROLLER_LOW_LEVEL_RECOVERY": truth(
                self.controller_low_level_recovery
            ),
            "MP5_DISABLE_MEMORY": truth(not self.legacy_workflow_memory),
            "DC3PA_MEMORY_ENABLED": truth(self.dc3pa_memory),
        }


@dataclass(frozen=True)
class DC3PAConfig:
    schema_version: int = 1
    mode: str = "mp5_legacy"
    task_file: Optional[str] = None
    model_name: Optional[str] = None
    seeds: List[int] = field(default_factory=lambda: [3])
    output_dir: str = "runs/dc3pa"
    feature_flags: FeatureFlags = field(default_factory=FeatureFlags)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ContractValidationError(
                f"Unsupported config schema_version={self.schema_version}"
            )
        if self.mode not in {"mp5_legacy", "reasoning_only", "dc3pa"}:
            raise ContractValidationError(f"Unsupported mode: {self.mode}")
        if not self.seeds:
            raise ContractValidationError("At least one seed is required")
        if any(not isinstance(seed, int) or seed < 0 for seed in self.seeds):
            raise ContractValidationError("Seeds must be non-negative integers")
        if not self.output_dir:
            raise ContractValidationError("output_dir cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def stable_hash(self) -> str:
        payload = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def load_config(path: str | Path) -> DC3PAConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    flags = FeatureFlags.from_mapping(data.pop("feature_flags", {}))
    config = DC3PAConfig(feature_flags=flags, **data)
    config.validate()
    return config


def dump_config(config: DC3PAConfig, path: str | Path) -> None:
    config.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(config.to_dict(), handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
