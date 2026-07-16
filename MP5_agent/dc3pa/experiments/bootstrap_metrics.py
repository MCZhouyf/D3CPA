"""Aggregate planning-focused bootstrap results without natural-performance claims."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class BootstrapMetricSlice:
    scope: str
    method_id: str
    episode_count: int
    pipeline_pass_count: int
    task_completed_count: int
    natural_completion_count: int
    bootstrap_assisted_completion_count: int
    incomplete_count: int
    intervention_trigger_count: int
    total_injected_logs: int
    total_naturally_collected_logs: int
    planner_calls: int
    reflection_calls: int
    evaluation_chain_calls: int

    def __post_init__(self) -> None:
        integer_values = tuple(
            value
            for key, value in asdict(self).items()
            if key not in {"scope", "method_id"}
        )
        if any(isinstance(value, bool) or value < 0 for value in integer_values):
            raise ValueError("Metric counts cannot be negative")
        if self.task_completed_count != (
            self.natural_completion_count
            + self.bootstrap_assisted_completion_count
        ):
            raise ValueError("Completion classes do not sum to task completion")
        if self.episode_count != (
            self.task_completed_count + self.incomplete_count
        ):
            raise ValueError("Completed/incomplete counts do not sum to episodes")

    @property
    def bootstrap_condition_success_rate(self) -> float:
        return (
            0.0
            if self.episode_count == 0
            else self.task_completed_count / self.episode_count
        )

    @property
    def natural_completion_rate(self) -> float:
        return (
            0.0
            if self.episode_count == 0
            else self.natural_completion_count / self.episode_count
        )

    @property
    def intervention_trigger_rate(self) -> float:
        return (
            0.0
            if self.episode_count == 0
            else self.intervention_trigger_count / self.episode_count
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bootstrap_condition_success_rate"] = (
            self.bootstrap_condition_success_rate
        )
        payload["natural_completion_rate"] = self.natural_completion_rate
        payload["intervention_trigger_rate"] = self.intervention_trigger_rate
        return payload


@dataclass(frozen=True)
class BootstrapMetricsReport:
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    source_commit: str
    blueprint_id: str
    condition_name: str
    result_language: str
    slices: tuple[BootstrapMetricSlice, ...]
    paper_natural_performance_claim_permitted: bool
    schema_version: int = SCHEMA_VERSION
    report_id: str = ""

    def __post_init__(self) -> None:
        if self.paper_natural_performance_claim_permitted:
            raise ValueError("Bootstrap results cannot be natural-performance claims")
        required = (
            self.bootstrap_policy_id,
            self.bootstrap_amendment_id,
            self.source_commit,
            self.blueprint_id,
            self.condition_name,
            self.result_language,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Bootstrap metrics identity is incomplete")
        expected = self.compute_report_id()
        if self.report_id and self.report_id != expected:
            raise ValueError("Bootstrap metrics report hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("report_id", None)
        payload["slices"] = [item.to_dict() for item in self.slices]
        return payload

    def compute_report_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "BootstrapMetricsReport":
        return replace(self, report_id=self.compute_report_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.report_id else self.with_id()
        payload = item.payload_without_id()
        payload["report_id"] = item.report_id
        return payload


def aggregate_bootstrap_receipts(
    receipts: Sequence[Mapping[str, Any]],
    *,
    bootstrap_policy_id: str,
    bootstrap_amendment_id: str,
    source_commit: str,
    blueprint_id: str,
) -> BootstrapMetricsReport:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    data_binding_ids: set[str] = set()
    for item in receipts:
        if item.get("policy_id") != bootstrap_policy_id:
            raise ValueError("Receipt bootstrap policy mismatch")
        if item.get("source_commit") != source_commit:
            raise ValueError("Receipt source commit mismatch")
        if item.get("blueprint_id") != blueprint_id:
            raise ValueError("Receipt Blueprint mismatch")
        if item.get("bootstrap_amendment_id") != bootstrap_amendment_id:
            raise ValueError("Receipt bootstrap amendment mismatch")
        binding_id = str(item.get("bootstrap_data_binding_id", ""))
        if not binding_id:
            raise ValueError("Receipt bootstrap data binding is missing")
        data_binding_ids.add(binding_id)
        key = (str(item.get("scope", "")), str(item.get("method_id", "")))
        if not all(key):
            raise ValueError("Receipt scope/method identity is missing")
        grouped.setdefault(key, []).append(item)
    if len(data_binding_ids) > 1:
        raise ValueError("Receipts mix bootstrap data bindings")

    slices: list[BootstrapMetricSlice] = []
    for (scope, method_id), items in sorted(grouped.items()):
        completed = sum(bool(item.get("task_completed", False)) for item in items)
        natural = sum(
            bool(item.get("natural_completion", False)) for item in items
        )
        assisted = sum(
            bool(item.get("bootstrap_assisted_completion", False))
            for item in items
        )
        slices.append(
            BootstrapMetricSlice(
                scope=scope,
                method_id=method_id,
                episode_count=len(items),
                pipeline_pass_count=sum(
                    bool(item.get("pipeline_pass", False)) for item in items
                ),
                task_completed_count=completed,
                natural_completion_count=natural,
                bootstrap_assisted_completion_count=assisted,
                incomplete_count=len(items) - completed,
                intervention_trigger_count=sum(
                    int(item.get("intervention_trigger_count", 0) or 0)
                    for item in items
                ),
                total_injected_logs=sum(
                    int(item.get("total_injected_logs", 0) or 0)
                    for item in items
                ),
                total_naturally_collected_logs=sum(
                    int(item.get("total_naturally_collected_logs", 0) or 0)
                    for item in items
                ),
                planner_calls=sum(
                    int(item.get("planner_calls", 0) or 0) for item in items
                ),
                reflection_calls=sum(
                    int(item.get("reflection_calls", 0) or 0) for item in items
                ),
                evaluation_chain_calls=sum(
                    int(item.get("evaluation_chain_calls", 0) or 0)
                    for item in items
                ),
            )
        )

    return BootstrapMetricsReport(
        bootstrap_policy_id=bootstrap_policy_id,
        bootstrap_amendment_id=bootstrap_amendment_id,
        source_commit=source_commit,
        blueprint_id=blueprint_id,
        condition_name="planning-focused log-bootstrap MineDojo",
        result_language=(
            "Report task success under the standardized log-bootstrap "
            "condition. Report natural and bootstrap-assisted completions "
            "separately. Do not call the aggregate natural MineDojo success."
        ),
        slices=tuple(slices),
        paper_natural_performance_claim_permitted=False,
    ).with_id()
