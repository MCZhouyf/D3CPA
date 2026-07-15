"""Development-data sufficiency audit without outcome tuning."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from .fusion_dataset import FusionExample


@dataclass(frozen=True)
class DataSufficiencyPolicy:
    minimum_examples_per_role: Mapping[str, int]
    minimum_positive_per_role: Mapping[str, int]
    minimum_negative_per_role: Mapping[str, int]
    minimum_groups_per_role: Mapping[str, int]
    minimum_tasks_per_role: Mapping[str, int]
    required_metadata_strata: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class DataAuditResult:
    eligible: bool
    reasons: tuple[str, ...]
    summary: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "reasons": list(self.reasons),
            "summary": dict(self.summary),
        }


def audit_role(
    examples: Sequence[FusionExample],
    *,
    role: str,
    policy: DataSufficiencyPolicy,
) -> DataAuditResult:
    positives = sum(item.label for item in examples)
    negatives = len(examples) - positives
    groups = {item.group_id for item in examples}
    tasks = {item.task for item in examples}
    reasons: list[str] = []

    checks = {
        "examples": (len(examples), policy.minimum_examples_per_role.get(role, 0)),
        "positive": (positives, policy.minimum_positive_per_role.get(role, 0)),
        "negative": (negatives, policy.minimum_negative_per_role.get(role, 0)),
        "groups": (len(groups), policy.minimum_groups_per_role.get(role, 0)),
        "tasks": (len(tasks), policy.minimum_tasks_per_role.get(role, 0)),
    }
    for name, (actual, minimum) in checks.items():
        if actual < minimum:
            reasons.append(f"{role}: {name} {actual} < required {minimum}")

    strata_summary: dict[str, Any] = {}
    for field_name, required_values in policy.required_metadata_strata.items():
        counts: dict[str, int] = {}
        for item in examples:
            value = str(item.metadata.get(field_name, "unknown"))
            counts[value] = counts.get(value, 0) + 1
        strata_summary[field_name] = counts
        missing = [value for value in required_values if counts.get(value, 0) == 0]
        if missing:
            reasons.append(
                f"{role}: metadata stratum {field_name} missing {missing}"
            )

    return DataAuditResult(
        eligible=not reasons,
        reasons=tuple(reasons),
        summary={
            "role": role,
            "examples": len(examples),
            "positive": positives,
            "negative": negatives,
            "groups": len(groups),
            "tasks": len(tasks),
            "strata": strata_summary,
        },
    )
