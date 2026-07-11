from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..contracts import AgentState, Plan


@runtime_checkable
class ReasoningChain(Protocol):
    def plan(
        self,
        task: str,
        state: AgentState,
        context: Mapping[str, Any] | None = None,
    ) -> Plan:
        ...


@runtime_checkable
class EvaluationChain(Protocol):
    def evaluate(
        self,
        plan: Plan,
        state: AgentState,
        evidence: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        ...
