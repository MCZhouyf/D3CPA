"""Dry-run-only log fallback policy and audit contracts.

The fallback is a diagnostic bootstrap mechanism. It is not natural resource
collection and is forbidden in formal acquisition, development calibration,
locked holdout, final evaluation, task-semantic smoke, and paper metrics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCHEMA_VERSION = 1
FALLBACK_KIND = "log_inventory_injection"
ALLOWED_SCOPES = frozenset({"diagnostic_dry_run"})
FORBIDDEN_SCOPES = frozenset(
    {
        "readiness_dry_run",
        "task_semantic_smoke",
        "formal_acquisition",
        "dev_train",
        "dev_tune",
        "dev_holdout",
        "fusion_fitting",
        "final_evaluation",
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


@dataclass(frozen=True)
class LogFallbackPolicy:
    policy_name: str = "dc3pa-diagnostic-log-fallback-v1"
    fallback_kind: str = FALLBACK_KIND
    default_enabled: bool = False
    allowed_scopes: tuple[str, ...] = ("diagnostic_dry_run",)
    forbidden_scopes: tuple[str, ...] = tuple(sorted(FORBIDDEN_SCOPES))
    maximum_natural_collection_attempts: int = 3
    inject_only_shortfall: bool = True
    target_item: str = "log"
    counts_as_natural_collection: bool = False
    counts_as_natural_task_success: bool = False
    require_explicit_cli_enable: bool = True
    require_dry_run_campaign: bool = True
    require_dry_run_output_marker: bool = True
    require_receipt_event: bool = True
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported fallback policy schema")
        if self.fallback_kind != FALLBACK_KIND:
            raise ValueError("Unsupported fallback kind")
        if self.default_enabled:
            raise ValueError("Log fallback must be disabled by default")
        if set(self.allowed_scopes) != ALLOWED_SCOPES:
            raise ValueError("Only diagnostic_dry_run may enable fallback")
        if set(self.forbidden_scopes) != FORBIDDEN_SCOPES:
            raise ValueError("Forbidden scope set is incomplete")
        if self.maximum_natural_collection_attempts <= 0:
            raise ValueError("Natural collection attempt bound must be positive")
        if not self.inject_only_shortfall:
            raise ValueError("Fallback may inject only the missing shortfall")
        if self.target_item != "log":
            raise ValueError("This policy is restricted to log")
        if self.counts_as_natural_collection or self.counts_as_natural_task_success:
            raise ValueError("Injected logs cannot count as natural success")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("Fallback policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["allowed_scopes"] = sorted(self.allowed_scopes)
        payload["forbidden_scopes"] = sorted(self.forbidden_scopes)
        return payload

    def compute_policy_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "LogFallbackPolicy":
        return replace(self, policy_id=self.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.policy_id else self.with_id()
        payload = item.payload_without_id()
        payload["policy_id"] = item.policy_id
        return payload

    def assert_activation_allowed(
        self,
        *,
        scope: str,
        explicit_cli_enable: bool,
        dry_run_campaign_present: bool,
        dry_run_output_marker_present: bool,
    ) -> None:
        if scope not in ALLOWED_SCOPES:
            raise ValueError(f"Log fallback is forbidden in scope {scope!r}")
        if self.require_explicit_cli_enable and not explicit_cli_enable:
            raise ValueError("Log fallback requires an explicit CLI flag")
        if self.require_dry_run_campaign and not dry_run_campaign_present:
            raise ValueError("Log fallback requires a bound dry-run campaign")
        if (
            self.require_dry_run_output_marker
            and not dry_run_output_marker_present
        ):
            raise ValueError("Log fallback requires a marked dry-run output root")


def load_log_fallback_policy(path: str | Path) -> LogFallbackPolicy:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Fallback policy must be a JSON object")
    values = dict(payload)
    values["allowed_scopes"] = tuple(values.get("allowed_scopes", ()))
    values["forbidden_scopes"] = tuple(values.get("forbidden_scopes", ()))
    return LogFallbackPolicy(**values)


@dataclass(frozen=True)
class LogFallbackEvent:
    fallback_kind: str
    scope: str
    policy_id: str
    inventory_before: int
    inventory_target: int
    inventory_after: int
    naturally_collected_count: int
    injected_count: int
    natural_collection_attempts: int
    bounded_attempts_exhausted: bool
    triggered: bool
    source_commit: str
    task: str
    seed: str
    event_index: int = 0
    schema_version: int = SCHEMA_VERSION
    event_id: str = ""

    def __post_init__(self) -> None:
        if self.fallback_kind != FALLBACK_KIND:
            raise ValueError("Unexpected fallback kind")
        if self.scope not in ALLOWED_SCOPES:
            raise ValueError("Fallback event uses a forbidden scope")
        integer_values = (
            self.inventory_before,
            self.inventory_target,
            self.inventory_after,
            self.naturally_collected_count,
            self.injected_count,
            self.natural_collection_attempts,
            self.event_index,
        )
        if any(isinstance(value, bool) or value < 0 for value in integer_values):
            raise ValueError("Fallback counts cannot be negative")
        expected_shortfall = max(
            0, self.inventory_target - self.inventory_before
        )
        if self.triggered:
            if not self.bounded_attempts_exhausted:
                raise ValueError("Triggered fallback must follow bounded attempts")
            if self.injected_count != expected_shortfall:
                raise ValueError("Fallback must inject exactly the shortfall")
            if self.inventory_after != (
                self.inventory_before + self.injected_count
            ):
                raise ValueError("Inventory after injection is inconsistent")
            if self.inventory_after < self.inventory_target:
                raise ValueError("Fallback did not reach the requested target")
        else:
            if self.injected_count != 0:
                raise ValueError("Untriggered fallback cannot inject inventory")
            if self.inventory_after != self.inventory_before:
                raise ValueError("Untriggered fallback cannot modify inventory")
        expected = self.compute_event_id()
        if self.event_id and self.event_id != expected:
            raise ValueError("Fallback event hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("event_id", None)
        return payload

    def compute_event_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "LogFallbackEvent":
        return replace(self, event_id=self.compute_event_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.event_id else self.with_id()
        payload = item.payload_without_id()
        payload["event_id"] = item.event_id
        return payload


class DiagnosticLogFallbackSession:
    """One explicitly authorized diagnostic intervention session."""

    def __init__(
        self,
        *,
        policy: LogFallbackPolicy,
        source_commit: str,
        task: str,
        seed: str,
    ) -> None:
        if not policy.policy_id:
            raise ValueError("Fallback session requires a frozen policy ID")
        if not source_commit or not task or not seed:
            raise ValueError("Fallback session identity is incomplete")
        self.policy = policy
        self.source_commit = str(source_commit)
        self.task = str(task)
        self.seed = str(seed)
        self._events: list[LogFallbackEvent] = []

    @property
    def events(self) -> tuple[LogFallbackEvent, ...]:
        return tuple(self._events)

    def intervene(
        self,
        *,
        target_item: str,
        target_quantity: int,
        inventory_before: Mapping[str, Any],
        naturally_collected_count: int,
        natural_collection_attempts: int,
        bounded_attempts_exhausted: bool,
        apply_inventory: Callable[[Mapping[str, int]], Mapping[str, Any]],
    ) -> LogFallbackEvent:
        if target_item != self.policy.target_item:
            raise ValueError("Diagnostic fallback can target only log")
        if not bounded_attempts_exhausted:
            raise ValueError("Natural collection attempts are not exhausted")
        if natural_collection_attempts != self.policy.maximum_natural_collection_attempts:
            raise ValueError("Natural collection attempt count does not match policy")

        normalized_before = _validated_inventory(inventory_before)
        before_logs = normalized_before.get("log", 0)
        target_quantity = int(target_quantity)
        if target_quantity <= before_logs:
            raise ValueError("Fallback requires a positive actual log shortfall")

        requested = dict(normalized_before)
        requested["log"] = target_quantity
        normalized_after = _validated_inventory(apply_inventory(requested))
        unrelated_before = {
            key: value for key, value in normalized_before.items() if key != "log"
        }
        unrelated_after = {
            key: value for key, value in normalized_after.items() if key != "log"
        }
        if unrelated_after != unrelated_before:
            raise RuntimeError("Fallback could not prove unrelated inventory preservation")

        event = LogFallbackEvent(
            fallback_kind=self.policy.fallback_kind,
            scope="diagnostic_dry_run",
            policy_id=self.policy.policy_id,
            inventory_before=before_logs,
            inventory_target=target_quantity,
            inventory_after=normalized_after.get("log", 0),
            naturally_collected_count=int(naturally_collected_count),
            injected_count=target_quantity - before_logs,
            natural_collection_attempts=int(natural_collection_attempts),
            bounded_attempts_exhausted=True,
            triggered=True,
            source_commit=self.source_commit,
            task=self.task,
            seed=self.seed,
            event_index=len(self._events),
        ).with_id()
        self._events.append(event)
        return event


def _validated_inventory(inventory: Mapping[str, Any]) -> dict[str, int]:
    if not isinstance(inventory, Mapping):
        raise TypeError("Inventory observation must be a mapping")
    normalized: dict[str, int] = {}
    for raw_name, raw_quantity in inventory.items():
        name = " ".join(str(raw_name).replace("_", " ").split()).lower()
        if name == "air" or not raw_quantity:
            continue
        if isinstance(raw_quantity, bool):
            raise ValueError("Inventory quantity cannot be boolean")
        quantity = int(raw_quantity)
        if quantity <= 0 or float(raw_quantity) != quantity:
            raise ValueError("Fallback requires positive integral inventory quantities")
        if name in normalized:
            raise ValueError("Fallback cannot preserve duplicate normalized inventory items")
        normalized[name] = quantity
    if len(normalized) > 36:
        raise ValueError("Fallback cannot preserve inventory larger than MineDojo slots")
    return normalized


@dataclass(frozen=True)
class FallbackReceiptMetrics:
    fallback_policy_id: str
    fallback_enabled: bool
    fallback_triggered: bool
    fallback_event_ids: tuple[str, ...]
    fallback_trigger_count: int
    total_injected_logs: int
    total_naturally_collected_logs: int
    total_natural_collection_attempts: int
    task_completed: bool
    natural_completion: bool
    fallback_assisted_completion: bool
    planner_calls: int
    reflection_calls: int
    evaluation_chain_calls: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        integer_values = (
            self.fallback_trigger_count,
            self.total_injected_logs,
            self.total_naturally_collected_logs,
            self.total_natural_collection_attempts,
            self.planner_calls,
            self.reflection_calls,
            self.evaluation_chain_calls,
        )
        if any(isinstance(value, bool) or value < 0 for value in integer_values):
            raise ValueError("Receipt metrics cannot be negative")
        if self.fallback_triggered != (self.fallback_trigger_count > 0):
            raise ValueError("Fallback trigger flag/count mismatch")
        if self.fallback_triggered and not self.fallback_enabled:
            raise ValueError("Triggered fallback was not enabled")
        if self.natural_completion and self.fallback_triggered:
            raise ValueError("Fallback-assisted run cannot be natural completion")
        if self.fallback_assisted_completion != (
            self.task_completed and self.fallback_triggered
        ):
            raise ValueError("Fallback-assisted completion is inconsistent")
        if self.natural_completion != (
            self.task_completed and not self.fallback_triggered
        ):
            raise ValueError("Natural completion is inconsistent")
        if len(self.fallback_event_ids) != self.fallback_trigger_count:
            raise ValueError("Fallback event count mismatch")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["fallback_event_ids"] = list(self.fallback_event_ids)
        return payload


def receipt_metrics_from_events(
    *,
    policy: LogFallbackPolicy,
    enabled: bool,
    events: Sequence[LogFallbackEvent],
    task_completed: bool,
    planner_calls: int,
    reflection_calls: int,
    evaluation_chain_calls: int,
) -> FallbackReceiptMetrics:
    triggered = [item for item in events if item.triggered]
    return FallbackReceiptMetrics(
        fallback_policy_id=policy.policy_id or policy.compute_policy_id(),
        fallback_enabled=enabled,
        fallback_triggered=bool(triggered),
        fallback_event_ids=tuple(
            (item.event_id or item.compute_event_id()) for item in triggered
        ),
        fallback_trigger_count=len(triggered),
        total_injected_logs=sum(item.injected_count for item in triggered),
        total_naturally_collected_logs=sum(
            item.naturally_collected_count for item in events
        ),
        total_natural_collection_attempts=sum(
            item.natural_collection_attempts for item in events
        ),
        task_completed=bool(task_completed),
        natural_completion=bool(task_completed and not triggered),
        fallback_assisted_completion=bool(task_completed and triggered),
        planner_calls=planner_calls,
        reflection_calls=reflection_calls,
        evaluation_chain_calls=evaluation_chain_calls,
    )


def assert_readiness_receipts_are_natural(
    receipt_payloads: Sequence[Mapping[str, Any]],
) -> None:
    errors: list[str] = []
    for payload in receipt_payloads:
        entry = str(payload.get("entry_id", "<unknown>"))
        metrics = payload.get("fallback_metrics", {})
        if not isinstance(metrics, Mapping):
            errors.append(f"{entry}: fallback_metrics missing")
            continue
        if bool(metrics.get("fallback_enabled", False)):
            errors.append(f"{entry}: fallback enabled in readiness campaign")
        if bool(metrics.get("fallback_triggered", False)):
            errors.append(f"{entry}: fallback triggered in readiness campaign")
        if int(metrics.get("total_injected_logs", 0) or 0) != 0:
            errors.append(f"{entry}: injected logs in readiness campaign")
    if errors:
        raise ValueError("; ".join(errors))
