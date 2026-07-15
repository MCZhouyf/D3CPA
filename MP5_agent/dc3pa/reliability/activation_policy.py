"""Pre-specified noninferiority and activation policy.

No default paper margins are silently invented. A policy file must be created
and hashed before the development holdout labels are evaluated.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping


ACTIVATION_POLICY_SCHEMA_VERSION = 1
SUPPORTED_METRICS = frozenset({"brier", "nll", "ece", "auroc", "average_precision"})


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric, not bool")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


@dataclass(frozen=True)
class ActivationPolicy:
    policy_name: str
    noninferiority_margins: Mapping[str, float]
    primary_metrics: tuple[str, ...] = ("brier", "nll")
    calibration_metrics: tuple[str, ...] = ("ece",)
    minimum_primary_improvements: int = 1
    minimum_effects: Mapping[str, float] = field(default_factory=dict)
    require_improvement_ci_upper_at_most_zero: bool = True
    confidence_level: float = 0.95
    bootstrap_replicates: int = 2000
    bootstrap_seed: int = 20260715
    bootstrap_grouping: str = "task"
    ece_bins: int = 10
    schema_version: int = ACTIVATION_POLICY_SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVATION_POLICY_SCHEMA_VERSION:
            raise ValueError("Unsupported activation policy schema")
        if not self.policy_name.strip():
            raise ValueError("policy_name is required")
        metrics = set(self.primary_metrics) | set(self.calibration_metrics)
        unknown = metrics - SUPPORTED_METRICS
        if unknown:
            raise ValueError(f"Unsupported metrics: {sorted(unknown)}")
        if not self.primary_metrics:
            raise ValueError("At least one primary metric is required")
        if self.minimum_primary_improvements < 0:
            raise ValueError("minimum_primary_improvements must be nonnegative")
        if self.minimum_primary_improvements > len(self.primary_metrics):
            raise ValueError("minimum_primary_improvements exceeds primary metrics")
        if not 0.0 < float(self.confidence_level) < 1.0:
            raise ValueError("confidence_level must be in (0, 1)")
        if self.bootstrap_replicates < 200:
            raise ValueError("bootstrap_replicates must be at least 200")
        if self.bootstrap_grouping not in {"task", "group_id"}:
            raise ValueError("bootstrap_grouping must be task or group_id")
        if self.ece_bins <= 0:
            raise ValueError("ece_bins must be positive")
        for metric in metrics:
            if metric not in self.noninferiority_margins:
                raise ValueError(f"Missing noninferiority margin for {metric}")
            if _finite(self.noninferiority_margins[metric], metric) < 0:
                raise ValueError("Noninferiority margins must be nonnegative")
            if _finite(self.minimum_effects.get(metric, 0.0), metric) < 0:
                raise ValueError("Minimum effects must be nonnegative")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("Activation policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["noninferiority_margins"] = dict(
            sorted(self.noninferiority_margins.items())
        )
        payload["minimum_effects"] = dict(sorted(self.minimum_effects.items()))
        return payload

    def compute_policy_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "ActivationPolicy":
        return replace(self, policy_id=self.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        policy = self if self.policy_id else self.with_id()
        payload = policy.payload_without_id()
        payload["policy_id"] = policy.policy_id
        return payload


def save_activation_policy(path: str | Path, policy: ActivationPolicy) -> str:
    policy = policy.with_id()
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(policy.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return policy.policy_id


def load_activation_policy(path: str | Path) -> ActivationPolicy:
    return ActivationPolicy(**json.loads(Path(path).read_text(encoding="utf-8")))
