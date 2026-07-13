from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, Tuple, runtime_checkable

from ..contracts import Plan
from .execution_observer import (
    OBSERVER_ATTRIBUTE,
    ExecutionEvent,
    ExecutionObserver,
)
from .local_subgoal import resolve_local_subgoal


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    underground: bool
    feedback: str = ""
    suggestion: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    telemetry: Tuple[ExecutionEvent, ...] = field(default_factory=tuple)


@runtime_checkable
class ControllerAdapter(Protocol):
    def execute(
        self,
        env: Any,
        plan: Plan,
        task_information: Dict[str, Any],
        underground: bool,
    ) -> ExecutionResult:
        ...


class LegacyControllerAdapter:
    """Adapter that optionally attaches non-invasive Stage-6 telemetry."""

    def __init__(
        self,
        legacy_controller: Any,
        *,
        observer: Optional[ExecutionObserver] = None,
    ) -> None:
        if not hasattr(legacy_controller, "check_and_execute_workflow"):
            raise TypeError(
                "legacy_controller must expose check_and_execute_workflow(...)"
            )
        self.legacy_controller = legacy_controller
        self.observer = observer

    @staticmethod
    def _tag_workflow(plan: Plan) -> Dict[str, Any]:
        workflow = deepcopy(plan.to_legacy_workflow())
        legacy_steps = workflow.get("workflow", [])
        plan_steps = tuple(getattr(plan, "steps", ()))
        for index, legacy_step in enumerate(legacy_steps):
            if not isinstance(legacy_step, dict):
                continue
            plan_step = plan_steps[index] if index < len(plan_steps) else None
            legacy_step["_dc3pa_plan_id"] = str(getattr(plan, "plan_id", ""))
            legacy_step["_dc3pa_plan_version"] = int(getattr(plan, "version", 0))
            legacy_step["_dc3pa_step_index"] = index
            legacy_step["_dc3pa_step_id"] = str(
                getattr(plan_step, "step_id", f"step-{index}")
            )
            legacy_step["_dc3pa_local_subgoal"] = resolve_local_subgoal(
                plan_step if plan_step is not None else legacy_step,
                fallback_index=index,
            )
        return workflow

    def execute(
        self,
        env: Any,
        plan: Plan,
        task_information: Dict[str, Any],
        underground: bool,
    ) -> ExecutionResult:
        observer = self.observer
        if observer is not None:
            observer.clear()

        sentinel = object()
        previous_observer = getattr(
            self.legacy_controller, OBSERVER_ATTRIBUTE, sentinel
        )
        if observer is not None:
            setattr(self.legacy_controller, OBSERVER_ATTRIBUTE, observer)

        try:
            check_result, new_underground = (
                self.legacy_controller.check_and_execute_workflow(
                    env=env,
                    workflow_dict=self._tag_workflow(plan),
                    task_information=task_information,
                    underground=underground,
                )
            )
        finally:
            if observer is not None:
                if previous_observer is sentinel:
                    try:
                        delattr(self.legacy_controller, OBSERVER_ATTRIBUTE)
                    except AttributeError:
                        pass
                else:
                    setattr(
                        self.legacy_controller,
                        OBSERVER_ATTRIBUTE,
                        previous_observer,
                    )

        success = bool(check_result.get("success"))
        if observer is not None:
            observer.finalize_workflow(
                success=success,
                reason=str(check_result.get("feedback", "")),
            )
            telemetry = observer.events()
        else:
            telemetry = ()

        return ExecutionResult(
            success=success,
            underground=bool(new_underground),
            feedback=str(check_result.get("feedback", "")),
            suggestion=str(check_result.get("suggestion", "")),
            raw=dict(check_result),
            telemetry=telemetry,
        )
