"""Offline-only deterministic G1 execution labels.

This module has no imports from planner, evaluator, memory, or controller.  It
is deliberately consumed only by the observability/artifact path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


FAILURE_MODES = {
    "none", "knowledge_gap", "model_reasoning_error", "environment_mismatch",
    "controller_failure", "budget_exhaustion", "system_api_error", "unknown",
}


@dataclass(frozen=True)
class ExecutionLabel:
    label_eligible: bool
    y_exec: int | None
    step_outcome: str
    failure_mode: str
    y_plan_fail: bool | None
    label_source: str


def label_execution(*, attempted: bool, status: str, result: Mapping[str, Any] | None = None) -> ExecutionLabel:
    """Classify one submitted high-level action without model judgement."""
    result = dict(result or {})
    if not attempted:
        return ExecutionLabel(False, None, "aborted", "unknown", None, "controller_trace")
    if status == "success":
        return ExecutionLabel(True, 1, "success", "none", False, "controller_trace")
    if status == "skipped_satisfied":
        return ExecutionLabel(False, None, "skipped_satisfied", "none", None, "controller_trace")
    reason = str(result.get("reason_code") or result.get("error_type") or "").lower()
    if status == "system_error" or any(token in reason for token in ("api", "network", "timeout", "parse")):
        return ExecutionLabel(False, None, "system_error", "system_api_error", None, "controller_trace")
    if status != "failure":
        return ExecutionLabel(False, None, "aborted", "unknown", None, "controller_trace")
    missing = result.get("missing_requirements") or []
    if missing or reason.startswith("missing_declared_"):
        mode = "knowledge_gap"
    elif "budget" in reason:
        mode = "budget_exhaustion"
    elif any(token in reason for token in ("unreachable", "no_observed_yield", "target")):
        mode = "environment_mismatch"
    elif any(token in reason for token in ("declared_dig", "unsupported_declared", "controller")):
        mode = "controller_failure"
    else:
        mode = "unknown"
    plan_fail = {"knowledge_gap": True, "model_reasoning_error": True,
                 "environment_mismatch": True, "controller_failure": False}.get(mode)
    return ExecutionLabel(True, 0, "failure", mode, plan_fail, "controller_trace")
