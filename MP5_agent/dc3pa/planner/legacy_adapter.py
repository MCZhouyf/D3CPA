from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from ..contracts import AgentState, Plan


class LegacyPlannerAdapter:
    """Stage-1 adapter around MP5's ``Planner.get_workflow`` method.

    The adapter intentionally does not import the legacy Planner class. Tests can inject
    a fake object, and production code can pass the existing instance unchanged.
    """

    def __init__(
        self,
        legacy_planner: Any,
        message_factory: Callable[[str, AgentState, Mapping[str, Any]], Any],
    ):
        if not hasattr(legacy_planner, "get_workflow"):
            raise TypeError("legacy_planner must expose get_workflow(message)")
        self.legacy_planner = legacy_planner
        self.message_factory = message_factory

    def plan(
        self,
        task: str,
        state: AgentState,
        context: Optional[Mapping[str, Any]] = None,
    ) -> Plan:
        resolved_context = dict(context or {})
        message = self.message_factory(task, state, resolved_context)
        workflow = self.legacy_planner.get_workflow(message)
        return Plan.from_dict(workflow, task=task)
