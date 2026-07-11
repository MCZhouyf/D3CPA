from __future__ import annotations

from typing import Any, Mapping, Optional

from ..contracts import AgentState, Plan
from .interfaces import ReasoningChain


class PassthroughCognitiveControlPlanner:
    """Stage-1 planner shell: behavior is reasoning-only by construction."""

    def __init__(self, reasoning_chain: ReasoningChain):
        self.reasoning_chain = reasoning_chain

    def create_plan(
        self,
        task: str,
        state: AgentState,
        context: Optional[Mapping[str, Any]] = None,
    ) -> Plan:
        return self.reasoning_chain.plan(task=task, state=state, context=context)
