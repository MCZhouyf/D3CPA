from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, Tuple, runtime_checkable

from ..contracts import Plan


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    underground: bool
    feedback: str = ""
    suggestion: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ControllerAdapter(Protocol):
    def execute(self, env: Any, plan: Plan, task_information: Dict[str, Any], underground: bool) -> ExecutionResult:
        ...


class LegacyControllerAdapter:
    def __init__(self, legacy_controller: Any):
        if not hasattr(legacy_controller, "check_and_execute_workflow"):
            raise TypeError(
                "legacy_controller must expose check_and_execute_workflow(...)"
            )
        self.legacy_controller = legacy_controller

    def execute(
        self,
        env: Any,
        plan: Plan,
        task_information: Dict[str, Any],
        underground: bool,
    ) -> ExecutionResult:
        check_result, new_underground = self.legacy_controller.check_and_execute_workflow(
            env=env,
            workflow_dict=plan.to_legacy_workflow(),
            task_information=task_information,
            underground=underground,
        )
        return ExecutionResult(
            success=bool(check_result.get("success")),
            underground=bool(new_underground),
            feedback=str(check_result.get("feedback", "")),
            suggestion=str(check_result.get("suggestion", "")),
            raw=dict(check_result),
        )
