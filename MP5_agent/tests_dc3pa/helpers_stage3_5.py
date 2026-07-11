from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.evaluation import EvaluationReport, EvaluationRequest
from dc3pa.reliability import (
    DimensionScore,
    ReliabilityContext,
    ReliabilityResult,
    StrategyWeights,
)


def find_step(name: str, step_id: Optional[str] = None) -> PlanStep:
    kwargs = {"step_id": step_id} if step_id else {}
    return PlanStep(actions=[Action("find", {"obj": name})], **kwargs)


def simple_plan(count: int = 3, task: str = "test") -> Plan:
    return Plan(task=task, steps=[find_step(f"item-{index}") for index in range(count)])


def reliability_result(
    plan: Plan,
    index: int,
    probability: Optional[float],
    hard_conflict: bool = False,
) -> ReliabilityResult:
    knowledge = DimensionScore(
        dimension="knowledge",
        probability=0.0 if hard_conflict else None,
        available=hard_conflict,
        reason="hard conflict" if hard_conflict else "not checked",
        hard_conflict=hard_conflict,
    )
    model = (
        DimensionScore(
            dimension="model",
            probability=probability,
            available=True,
            reason="scripted",
        )
        if probability is not None
        else DimensionScore.unavailable("model", "scripted unavailable")
    )
    environment = DimensionScore.unavailable("environment", "not checked")
    effective = StrategyWeights(0.0, 1.0, 0.0) if probability is not None else None
    return ReliabilityResult(
        plan_id=plan.plan_id,
        plan_version=plan.version,
        step_id=plan.steps[index].step_id,
        step_index=index,
        probability=probability,
        scores={
            "knowledge": knowledge,
            "model": model,
            "environment": environment,
        },
        base_weights=StrategyWeights(0.0, 1.0, 0.0),
        effective_weights=effective,
        successful_memory_count=0,
    )


class StaticReasoningChain:
    def __init__(self, plan: Plan):
        self.plan_value = plan
        self.calls = 0
        self.contexts = []

    def plan(self, task: str, state: AgentState, context=None) -> Plan:
        self.calls += 1
        self.contexts.append(dict(context or {}))
        assert task == self.plan_value.task
        return self.plan_value


class FunctionReliabilityModel:
    def __init__(self, function: Callable[[Plan, int], tuple[Optional[float], bool]]):
        self.function = function
        self.calls = []

    def score_window(
        self,
        plan: Plan,
        step_indices: Sequence[int],
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
        successful_memory_count: Optional[int] = None,
    ):
        self.calls.append((plan.plan_id, plan.version, tuple(step_indices)))
        return [
            reliability_result(plan, index, *self.function(plan, index))
            for index in step_indices
        ]


class FunctionEvaluationChain:
    def __init__(self, function: Callable[[EvaluationRequest], EvaluationReport]):
        self.function = function
        self.requests = []

    def evaluate(self, request: EvaluationRequest) -> EvaluationReport:
        self.requests.append(request)
        return self.function(request)
