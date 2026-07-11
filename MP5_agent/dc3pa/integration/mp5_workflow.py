from __future__ import annotations

from typing import Any, Mapping

from ..contracts import Plan


def legacy_workflow_to_plan(workflow: Mapping[str, Any], task: str) -> Plan:
    return Plan.from_dict(workflow, task=task)


def plan_to_legacy_workflow(plan: Plan) -> dict[str, Any]:
    return plan.to_legacy_workflow()
