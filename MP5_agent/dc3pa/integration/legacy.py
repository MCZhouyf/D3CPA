from __future__ import annotations

import inspect
from typing import Any, Callable, Mapping, Optional

from ..contracts import AgentState, Plan
from ..planner.legacy_adapter import LegacyPlannerAdapter


class LegacyMP5ReasoningChain:
    """Adapt MP5 Planner + Work_Memory prompt construction to ReasoningChain."""

    def __init__(self, legacy_planner: Any, legacy_memory: Any):
        if not hasattr(legacy_memory, "generate_prompt_template"):
            raise TypeError("legacy_memory must expose generate_prompt_template(...)")
        self.legacy_memory = legacy_memory
        self.adapter = LegacyPlannerAdapter(legacy_planner, self._message_factory)

    def _message_factory(
        self, task: str, state: AgentState, context: Mapping[str, Any]
    ) -> Any:
        task_information = context.get("task_information")
        if not isinstance(task_information, Mapping):
            task_information = {"task": task}
        previous_workflow = context.get("previous_workflow")
        reflection = context.get("reflection", "")
        check_result = context.get("check_result")
        underground = bool(context.get("underground", state.metadata.get("underground", False)))
        return self.legacy_memory.generate_prompt_template(
            env=context.get("env"),
            task_information=dict(task_information),
            underground=underground,
            check_result=check_result,
            previous_workflow=previous_workflow,
            reflection=reflection,
        )

    def plan(
        self,
        task: str,
        state: AgentState,
        context: Optional[Mapping[str, Any]] = None,
    ) -> Plan:
        return self.adapter.plan(task=task, state=state, context=context)


class LegacyModePlanSource:
    """Preserve legacy fixed-workflow behavior only in explicit mp5_legacy mode."""

    def __init__(
        self,
        reasoning_chain: LegacyMP5ReasoningChain,
        fixed_workflow_provider: Optional[
            Callable[[Mapping[str, Any]], Optional[Mapping[str, Any]]]
        ] = None,
    ):
        self.reasoning_chain = reasoning_chain
        self.fixed_workflow_provider = fixed_workflow_provider

    def plan(self, task: str, state: AgentState, context=None) -> Plan:
        resolved = dict(context or {})
        task_information = resolved.get("task_information", {"task": task})
        if self.fixed_workflow_provider is not None and isinstance(task_information, Mapping):
            fixed = self.fixed_workflow_provider(task_information)
            if fixed is not None:
                return Plan.from_dict(fixed, task=task)
        return self.reasoning_chain.plan(task, state, resolved)


class LegacyGoalChecker:
    def __init__(self, legacy_controller: Any, legacy_memory: Any = None):
        if not hasattr(legacy_controller, "check_done"):
            raise TypeError("legacy_controller must expose check_done(task_information, ...)")
        self.legacy_controller = legacy_controller
        self.legacy_memory = legacy_memory

    def is_done(self, task_information: Mapping[str, Any]) -> bool:
        method = self.legacy_controller.check_done
        try:
            parameters = inspect.signature(method).parameters
        except (TypeError, ValueError):
            parameters = {}
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        if "memory" in parameters or accepts_kwargs:
            return bool(
                method(
                    task_information=dict(task_information),
                    memory=self.legacy_memory,
                )
            )
        return bool(method(dict(task_information)))


class LegacyReflexionAdapter:
    def __init__(self, legacy_reflexion: Any):
        if not (
            hasattr(legacy_reflexion, "reflect_failure")
            or hasattr(legacy_reflexion, "reflect")
        ):
            raise TypeError(
                "legacy_reflexion must expose reflect_failure(...) or reflect(...)"
            )
        self.legacy_reflexion = legacy_reflexion

    def reflect(
        self,
        *,
        task_information: Mapping[str, Any],
        previous_workflow: Mapping[str, Any],
        check_result: Mapping[str, Any],
        underground: bool = False,
    ) -> str:
        if hasattr(self.legacy_reflexion, "reflect_failure"):
            value = self.legacy_reflexion.reflect_failure(
                dict(task_information),
                dict(previous_workflow),
                dict(check_result),
                bool(underground),
            )
            return "" if value is None else str(value)
        try:
            value = self.legacy_reflexion.reflect(
                task_information=dict(task_information),
                previous_workflow=dict(previous_workflow),
                check_result=dict(check_result),
                underground=bool(underground),
            )
        except TypeError:
            try:
                value = self.legacy_reflexion.reflect(
                    dict(task_information), dict(previous_workflow), dict(check_result)
                )
            except TypeError:
                value = self.legacy_reflexion.reflect(
                    previous_workflow=dict(previous_workflow),
                    check_result=dict(check_result),
                )
        return "" if value is None else str(value)


class LegacyWorkflowMemorySink:
    def __init__(self, legacy_memory: Any):
        if not hasattr(legacy_memory, "add_successful_workflow"):
            raise TypeError("legacy_memory must expose add_successful_workflow(...)")
        self.legacy_memory = legacy_memory

    def record_success(
        self, task_information: Mapping[str, Any], plan: Plan
    ) -> Any:
        task_name = str(
            task_information.get("task")
            or task_information.get("task_name")
            or task_information.get("description")
            or plan.task
        )
        workflow_steps = plan.to_legacy_workflow()["workflow"]
        method = self.legacy_memory.add_successful_workflow
        try:
            parameters = inspect.signature(method).parameters
        except (TypeError, ValueError):
            parameters = {}
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        if "successful_workflow" in parameters or accepts_kwargs:
            kwargs = {
                "task_name": task_name,
                "successful_workflow": workflow_steps,
            }
            if "update_json" in parameters or accepts_kwargs:
                kwargs["update_json"] = True
            return method(**kwargs)
        positional = [
            parameter
            for parameter in parameters.values()
            if parameter.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        if len(positional) >= 3:
            return method(task_name, workflow_steps, True)
        return method(task_name, workflow_steps)
