"""Formal planning-focused log bootstrap condition.

This policy deliberately changes the experimental estimand. All formal methods
and all post-readiness phases use the same bounded log-shortfall intervention
so that the study focuses on planning and long-horizon control rather than
early-tree acquisition reliability.

Results under this policy must be described as a planning-focused,
log-bootstrap MineDojo condition. They are not natural empty-inventory
MineDojo performance, even though episodes begin with an empty inventory.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCHEMA_VERSION = 1
POLICY_MODE = "planning_focused_log_bootstrap_v1"
FALLBACK_KIND = "log_inventory_injection"
TARGET_SOURCE = "planner_declared_log_requirement"
INJECTION_TIMING = "after_bounded_natural_attempts"
OUTPUT_ROOT_MARKER = ".dc3pa-formal-log-bootstrap-output.json"

FORMAL_SCOPES = frozenset(
    {
        "bootstrap_readiness_dry_run",
        "formal_acquisition",
        "dev_train",
        "dev_tune",
        "dev_holdout",
        "confidence_calibration_collection",
        "environment_tuning_collection",
        "fusion_feature_collection",
        "final_evaluation",
        "matched_baseline_evaluation",
    }
)

NON_FORMAL_DIAGNOSTIC_SCOPES = frozenset({"fallback_diagnostic"})
FORBIDDEN_SCOPES = frozenset({"task_semantic_smoke"})
ALL_ALLOWED_SCOPES = FORMAL_SCOPES | NON_FORMAL_DIAGNOSTIC_SCOPES


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
class FormalLogBootstrapPolicy:
    policy_name: str = "dc3pa-planning-focused-log-bootstrap-v1"
    policy_mode: str = POLICY_MODE
    fallback_kind: str = FALLBACK_KIND
    target_item: str = "log"
    target_source: str = TARGET_SOURCE
    injection_timing: str = INJECTION_TIMING
    maximum_natural_collection_attempts: int = 3
    inject_exact_shortfall_only: bool = True
    preserve_unrelated_inventory: bool = True
    start_inventory_empty: bool = True
    enabled_for_all_formal_methods: bool = True
    enabled_for_all_formal_scopes: bool = True
    formal_scopes: tuple[str, ...] = tuple(sorted(FORMAL_SCOPES))
    diagnostic_scopes: tuple[str, ...] = tuple(
        sorted(NON_FORMAL_DIAGNOSTIC_SCOPES)
    )
    forbidden_scopes: tuple[str, ...] = tuple(sorted(FORBIDDEN_SCOPES))
    counts_as_natural_collection: bool = False
    counts_as_natural_task_success: bool = False
    counts_as_bootstrap_condition_success: bool = True
    planner_requirement_may_not_be_corrected: bool = True
    runtime_material_inference_forbidden: bool = True
    task_specific_injection_forbidden: bool = True
    must_record_every_intervention: bool = True
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported bootstrap policy schema")
        if self.policy_mode != POLICY_MODE:
            raise ValueError("Unexpected bootstrap policy mode")
        if self.fallback_kind != FALLBACK_KIND:
            raise ValueError("Unexpected fallback kind")
        if self.target_item != "log":
            raise ValueError("Formal bootstrap is restricted to log")
        if self.target_source != TARGET_SOURCE:
            raise ValueError("Log target must come from the Planner declaration")
        if self.injection_timing != INJECTION_TIMING:
            raise ValueError("Unexpected bootstrap timing")
        if self.maximum_natural_collection_attempts <= 0:
            raise ValueError("Natural attempt bound must be positive")
        if not all(
            (
                self.inject_exact_shortfall_only,
                self.preserve_unrelated_inventory,
                self.start_inventory_empty,
                self.enabled_for_all_formal_methods,
                self.enabled_for_all_formal_scopes,
                self.planner_requirement_may_not_be_corrected,
                self.runtime_material_inference_forbidden,
                self.task_specific_injection_forbidden,
                self.must_record_every_intervention,
            )
        ):
            raise ValueError("Formal bootstrap safeguards are incomplete")
        if set(self.formal_scopes) != FORMAL_SCOPES:
            raise ValueError("Formal scope set is incomplete")
        if set(self.diagnostic_scopes) != NON_FORMAL_DIAGNOSTIC_SCOPES:
            raise ValueError("Diagnostic scope set is incorrect")
        if set(self.forbidden_scopes) != FORBIDDEN_SCOPES:
            raise ValueError("Forbidden scope set is incorrect")
        if self.counts_as_natural_collection or self.counts_as_natural_task_success:
            raise ValueError("Injected logs cannot count as natural performance")
        if not self.counts_as_bootstrap_condition_success:
            raise ValueError("Policy must define a bootstrap-condition estimand")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("Bootstrap policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["formal_scopes"] = sorted(self.formal_scopes)
        payload["diagnostic_scopes"] = sorted(self.diagnostic_scopes)
        payload["forbidden_scopes"] = sorted(self.forbidden_scopes)
        return payload

    def compute_policy_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalLogBootstrapPolicy":
        return replace(self, policy_id=self.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.policy_id else self.with_id()
        payload = item.payload_without_id()
        payload["policy_id"] = item.policy_id
        return payload

    def assert_scope(self, scope: str) -> None:
        if scope in FORBIDDEN_SCOPES:
            raise ValueError(f"Log bootstrap is forbidden in scope {scope!r}")
        if scope not in ALL_ALLOWED_SCOPES:
            raise ValueError(f"Unknown or unapproved bootstrap scope {scope!r}")


@dataclass(frozen=True)
class FormalLogBootstrapEvent:
    policy_id: str
    scope: str
    method_id: str
    task: str
    seed: str
    plan_id: str
    plan_version: int
    event_index: int
    target_source: str
    planner_declared_log_requirement: int
    inventory_before: int
    natural_collection_attempts: int
    naturally_collected_logs: int
    bounded_attempts_exhausted: bool
    injected_logs: int
    inventory_after: int
    intervention_triggered: bool
    source_commit: str
    schema_version: int = SCHEMA_VERSION
    event_id: str = ""

    def __post_init__(self) -> None:
        if self.target_source != TARGET_SOURCE:
            raise ValueError("Bootstrap target source mismatch")
        integer_values = (
            self.plan_version,
            self.event_index,
            self.planner_declared_log_requirement,
            self.inventory_before,
            self.natural_collection_attempts,
            self.naturally_collected_logs,
            self.injected_logs,
            self.inventory_after,
        )
        if any(isinstance(value, bool) or value < 0 for value in integer_values):
            raise ValueError("Bootstrap event counts cannot be negative")
        if not all(
            (
                self.policy_id,
                self.scope,
                self.method_id,
                self.task,
                self.seed,
                self.plan_id,
                self.source_commit,
            )
        ):
            raise ValueError("Bootstrap event identity is incomplete")

        shortfall = max(
            0,
            self.planner_declared_log_requirement - self.inventory_before,
        )
        if self.intervention_triggered:
            if not self.bounded_attempts_exhausted:
                raise ValueError(
                    "Formal intervention requires exhausted bounded attempts"
                )
            if shortfall <= 0:
                raise ValueError("Intervention triggered without a shortfall")
            if self.injected_logs != shortfall:
                raise ValueError("Formal bootstrap must inject exact shortfall")
            if self.inventory_after != (
                self.inventory_before + self.injected_logs
            ):
                raise ValueError("Inventory-after value is inconsistent")
        else:
            if self.injected_logs != 0:
                raise ValueError("Untriggered event cannot inject logs")
            if self.inventory_after != self.inventory_before:
                raise ValueError("Untriggered event cannot change inventory")

        expected = self.compute_event_id()
        if self.event_id and self.event_id != expected:
            raise ValueError("Bootstrap event hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("event_id", None)
        return payload

    def compute_event_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalLogBootstrapEvent":
        return replace(self, event_id=self.compute_event_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.event_id else self.with_id()
        payload = item.payload_without_id()
        payload["event_id"] = item.event_id
        return payload


def is_log_target_name(value: Any) -> bool:
    normalized = " ".join(str(value).replace("_", " ").lower().split())
    return normalized == "log" or normalized.endswith(" log")


def planner_declared_log_requirement(plan: Any) -> int:
    """Read only explicit ``mine log`` quantities from the current plan."""

    steps = getattr(plan, "steps", None)
    if steps is None and isinstance(plan, Mapping):
        steps = plan.get("steps", plan.get("workflow", ()))
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
        raise TypeError("Plan must expose a sequence of steps")

    declared = 0
    for step in steps:
        times = getattr(step, "times", None)
        actions = getattr(step, "actions", None)
        if isinstance(step, Mapping):
            times = step.get("times", 1)
            actions = step.get("actions", ())
        try:
            quantity = int(times)
        except (TypeError, ValueError) as exc:
            raise ValueError("Plan step times must be integer-like") from exc
        if quantity <= 0:
            raise ValueError("Plan step times must be positive")
        if not isinstance(actions, Sequence) or isinstance(actions, (str, bytes)):
            raise TypeError("Plan step actions must be a sequence")
        for action in actions:
            name = getattr(action, "name", None)
            args = getattr(action, "args", None)
            if isinstance(action, Mapping):
                name = action.get("name")
                args = action.get("args", {})
            if name != "mine" or not isinstance(args, Mapping):
                continue
            if is_log_target_name(args.get("obj", "")):
                declared += quantity
    return declared


def mark_formal_bootstrap_output_root(
    root: str | Path,
    *,
    policy_id: str,
    amendment_id: str,
    blueprint_id: str,
    scope: str,
    method_id: str,
) -> Path:
    root_path = Path(root).resolve()
    root_path.mkdir(parents=True, exist_ok=True)
    marker = root_path / OUTPUT_ROOT_MARKER
    payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": str(policy_id),
        "amendment_id": str(amendment_id),
        "blueprint_id": str(blueprint_id),
        "scope": str(scope),
        "method_id": str(method_id),
    }
    if any(not value for key, value in payload.items() if key != "schema_version"):
        raise ValueError("Formal bootstrap output marker identity is incomplete")
    if marker.exists():
        existing = json.loads(marker.read_text(encoding="utf-8"))
        if existing != payload:
            raise ValueError("Formal bootstrap output marker mismatch")
        return marker
    marker.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return marker


def _validated_inventory(inventory: Mapping[str, Any]) -> dict[str, int]:
    if not isinstance(inventory, Mapping):
        raise TypeError("Inventory observation must be a mapping")
    normalized: dict[str, int] = {}
    for raw_name, raw_quantity in inventory.items():
        name = " ".join(str(raw_name).replace("_", " ").lower().split())
        if name == "air" or not raw_quantity:
            continue
        if isinstance(raw_quantity, bool):
            raise ValueError("Inventory quantity cannot be boolean")
        quantity = int(raw_quantity)
        if quantity <= 0 or float(raw_quantity) != quantity:
            raise ValueError("Inventory quantities must be positive integers")
        normalized[name] = normalized.get(name, 0) + quantity
    if len(normalized) > 36:
        raise ValueError("Inventory cannot exceed MineDojo slot capacity")
    return normalized


class FormalLogBootstrapSession:
    """Policy-bound formal intervention state for one task-seed run."""

    def __init__(
        self,
        *,
        policy: FormalLogBootstrapPolicy,
        amendment_id: str,
        source_commit: str,
        blueprint_id: str,
        scope: str,
        method_id: str,
        task: str,
        seed: str,
    ) -> None:
        if not policy.policy_id:
            raise ValueError("Formal bootstrap requires a frozen policy ID")
        policy.assert_scope(scope)
        identity = (
            amendment_id,
            source_commit,
            blueprint_id,
            scope,
            method_id,
            task,
            seed,
        )
        if any(not str(value).strip() for value in identity):
            raise ValueError("Formal bootstrap session identity is incomplete")
        self.policy = policy
        self.amendment_id = str(amendment_id)
        self.source_commit = str(source_commit)
        self.blueprint_id = str(blueprint_id)
        self.scope = str(scope)
        self.method_id = str(method_id)
        self.task = str(task)
        self.seed = str(seed)
        self._plan_id = ""
        self._plan_version = 0
        self._declared_target = 0
        self._plan_acquisition_completed = False
        self._events: list[FormalLogBootstrapEvent] = []

    @property
    def events(self) -> tuple[FormalLogBootstrapEvent, ...]:
        return tuple(self._events)

    def bind_plan(self, plan: Any) -> None:
        plan_id = str(getattr(plan, "plan_id", ""))
        plan_version = int(getattr(plan, "version", 0) or 0)
        if not plan_id or plan_version <= 0:
            raise ValueError("Formal bootstrap requires plan ID and version")
        self._plan_id = plan_id
        self._plan_version = plan_version
        self._declared_target = planner_declared_log_requirement(plan)
        self._plan_acquisition_completed = False

    def target_quantity(self, _controller_target: int) -> int:
        if not self._plan_id:
            raise RuntimeError("Formal bootstrap plan is not bound")
        return 0 if self._plan_acquisition_completed else self._declared_target

    def complete_acquisition(self, actual_log_count: int) -> None:
        if int(actual_log_count) < self._declared_target:
            raise ValueError("Cannot complete log acquisition below declared target")
        self._plan_acquisition_completed = True

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
    ) -> FormalLogBootstrapEvent:
        if target_item != self.policy.target_item:
            raise ValueError("Formal bootstrap can target only log")
        if not self._plan_id:
            raise RuntimeError("Formal bootstrap plan is not bound")
        if int(target_quantity) != self._declared_target:
            raise ValueError("Controller target differs from Planner declaration")
        if natural_collection_attempts != self.policy.maximum_natural_collection_attempts:
            raise ValueError("Natural collection attempt count does not match policy")
        if not bounded_attempts_exhausted:
            raise ValueError("Formal bootstrap requires exhausted bounded attempts")

        normalized_before = _validated_inventory(inventory_before)
        before_logs = normalized_before.get("log", 0)
        shortfall = max(0, self._declared_target - before_logs)
        if shortfall <= 0:
            raise ValueError("Formal bootstrap requires a positive log shortfall")
        requested = dict(normalized_before)
        requested["log"] = before_logs + shortfall
        normalized_after = _validated_inventory(apply_inventory(requested))
        unrelated_before = {
            key: value for key, value in normalized_before.items() if key != "log"
        }
        unrelated_after = {
            key: value for key, value in normalized_after.items() if key != "log"
        }
        if unrelated_before != unrelated_after:
            raise RuntimeError("Formal bootstrap changed unrelated inventory")
        if normalized_after.get("log", 0) != self._declared_target:
            raise RuntimeError("Formal bootstrap did not reach the declared target")

        event = FormalLogBootstrapEvent(
            policy_id=self.policy.policy_id,
            scope=self.scope,
            method_id=self.method_id,
            task=self.task,
            seed=self.seed,
            plan_id=self._plan_id,
            plan_version=self._plan_version,
            event_index=len(self._events),
            target_source=TARGET_SOURCE,
            planner_declared_log_requirement=self._declared_target,
            inventory_before=before_logs,
            natural_collection_attempts=int(natural_collection_attempts),
            naturally_collected_logs=int(naturally_collected_count),
            bounded_attempts_exhausted=True,
            injected_logs=shortfall,
            inventory_after=normalized_after.get("log", 0),
            intervention_triggered=True,
            source_commit=self.source_commit,
        ).with_id()
        self._events.append(event)
        self._plan_acquisition_completed = True
        return event

    def record_metadata(self, *, task_completed: bool) -> dict[str, Any]:
        triggered = [event for event in self._events if event.intervention_triggered]
        return {
            "bootstrap_policy_id": self.policy.policy_id,
            "formal_bootstrap_amendment_id": self.amendment_id,
            "bootstrap_event_ids": [event.event_id for event in triggered],
            "natural_completion": bool(task_completed and not triggered),
            "bootstrap_assisted_completion": bool(task_completed and triggered),
            "injected_log_count": sum(event.injected_logs for event in triggered),
            "source_commit": self.source_commit,
            "blueprint_id": self.blueprint_id,
        }


def load_formal_log_bootstrap_policy(
    path: str | Path,
) -> FormalLogBootstrapPolicy:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Formal bootstrap policy must be a JSON object")
    values = dict(payload)
    values["formal_scopes"] = tuple(values.get("formal_scopes", ()))
    values["diagnostic_scopes"] = tuple(values.get("diagnostic_scopes", ()))
    values["forbidden_scopes"] = tuple(values.get("forbidden_scopes", ()))
    policy = FormalLogBootstrapPolicy(**values)
    if not policy.policy_id:
        raise ValueError("Formal bootstrap policy must be frozen")
    return policy


@dataclass(frozen=True)
class FormalBootstrapRunReceipt:
    run_id: str
    readiness_campaign_id: str
    policy_id: str
    bootstrap_amendment_id: str
    bootstrap_data_binding_id: str
    scope: str
    method_id: str
    task: str
    seed: str
    source_commit: str
    blueprint_id: str
    model_profile_id: str
    requested_model: str
    returned_model_identities: tuple[str, ...]
    returned_identity_stable_within_run: bool
    process_exit_code: int
    pipeline_pass: bool
    task_completed: bool
    planner_calls: int
    reflection_calls: int
    evaluation_chain_calls: int
    controller_execution_count: int
    event_ids: tuple[str, ...]
    intervention_trigger_count: int
    total_injected_logs: int
    total_naturally_collected_logs: int
    natural_completion: bool
    bootstrap_assisted_completion: bool
    formal_memory_write_count: int
    acquisition_write_count: int
    provider_call_contract_passed: bool
    output_root_guard_passed: bool
    trace_sha256: str
    schema_version: int = SCHEMA_VERSION
    receipt_id: str = ""

    def __post_init__(self) -> None:
        if not all(
            (
                self.run_id,
                self.policy_id,
                self.bootstrap_amendment_id,
                self.bootstrap_data_binding_id,
                self.scope,
                self.method_id,
                self.task,
                self.seed,
                self.source_commit,
                self.blueprint_id,
                self.model_profile_id,
                self.requested_model,
            )
        ):
            raise ValueError("Run receipt identity is incomplete")
        if self.scope == "bootstrap_readiness_dry_run" and not (
            self.readiness_campaign_id
        ):
            raise ValueError("Readiness receipt must bind its campaign ID")
        integer_values = (
            self.process_exit_code,
            self.planner_calls,
            self.reflection_calls,
            self.evaluation_chain_calls,
            self.controller_execution_count,
            self.intervention_trigger_count,
            self.total_injected_logs,
            self.total_naturally_collected_logs,
            self.formal_memory_write_count,
            self.acquisition_write_count,
        )
        if any(isinstance(value, bool) or value < 0 for value in integer_values):
            raise ValueError("Run receipt counts cannot be negative")
        if self.pipeline_pass and not self.returned_model_identities:
            raise ValueError("Passing run must record returned model identity")
        if self.pipeline_pass and not self.provider_call_contract_passed:
            raise ValueError("Provider call contract failed for a passing run")
        if self.pipeline_pass and not self.output_root_guard_passed:
            raise ValueError("Passing run output root is not marked")
        if self.pipeline_pass and not self.trace_sha256:
            raise ValueError("Passing run must bind a trace SHA256")
        if len(self.event_ids) != self.intervention_trigger_count:
            raise ValueError("Bootstrap event count mismatch")
        if self.natural_completion != (
            self.task_completed and self.intervention_trigger_count == 0
        ):
            raise ValueError("Natural completion classification is inconsistent")
        if self.bootstrap_assisted_completion != (
            self.task_completed and self.intervention_trigger_count > 0
        ):
            raise ValueError(
                "Bootstrap-assisted completion classification is inconsistent"
            )
        if self.natural_completion and self.bootstrap_assisted_completion:
            raise ValueError("Completion classes must be mutually exclusive")
        expected = self.compute_receipt_id()
        if self.receipt_id and self.receipt_id != expected:
            raise ValueError("Run receipt hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("receipt_id", None)
        payload["returned_model_identities"] = list(
            self.returned_model_identities
        )
        payload["event_ids"] = list(self.event_ids)
        return payload

    def compute_receipt_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalBootstrapRunReceipt":
        return replace(self, receipt_id=self.compute_receipt_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.receipt_id else self.with_id()
        payload = item.payload_without_id()
        payload["receipt_id"] = item.receipt_id
        return payload


def validate_events_for_receipt(
    *,
    policy: FormalLogBootstrapPolicy,
    receipt: FormalBootstrapRunReceipt,
    events: Sequence[FormalLogBootstrapEvent],
) -> None:
    policy.assert_scope(receipt.scope)
    policy_id = policy.policy_id or policy.compute_policy_id()
    if receipt.policy_id != policy_id:
        raise ValueError("Receipt/bootstrap policy mismatch")
    event_ids = tuple(
        item.event_id or item.compute_event_id() for item in events
    )
    if receipt.event_ids != event_ids:
        raise ValueError("Receipt/event ID mismatch")
    if receipt.total_injected_logs != sum(
        item.injected_logs for item in events
    ):
        raise ValueError("Receipt injected-log total mismatch")
    if receipt.total_naturally_collected_logs != sum(
        item.naturally_collected_logs for item in events
    ):
        raise ValueError("Receipt natural-log total mismatch")
    for event in events:
        if event.policy_id != policy_id:
            raise ValueError("Event/bootstrap policy mismatch")
        if event.scope != receipt.scope:
            raise ValueError("Event/receipt scope mismatch")
        if event.method_id != receipt.method_id:
            raise ValueError("Event/receipt method mismatch")
        if event.task != receipt.task or event.seed != receipt.seed:
            raise ValueError("Event/receipt task-seed mismatch")
        if event.source_commit != receipt.source_commit:
            raise ValueError("Event/receipt source commit mismatch")
