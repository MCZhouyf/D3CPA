from __future__ import annotations

from typing import Optional, Protocol, Sequence

from ..contracts import AgentState, Plan
from .contracts import (
    DIMENSIONS,
    DimensionScore,
    ReliabilityContext,
    ReliabilityResult,
)
from .weights import LinearMemoryWeightPolicy, effective_weights


class ReliabilityStrategy(Protocol):
    def score(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> DimensionScore:
        ...


class SuccessfulMemoryCounter(Protocol):
    def successful_episode_count(self) -> int:
        ...


class HybridProbabilityModel:
    def __init__(
        self,
        knowledge: ReliabilityStrategy,
        model: ReliabilityStrategy,
        environment: ReliabilityStrategy,
        weight_policy: LinearMemoryWeightPolicy,
        memory_counter: Optional[SuccessfulMemoryCounter] = None,
    ):
        self.knowledge = knowledge
        self.model = model
        self.environment = environment
        self.weight_policy = weight_policy
        self.memory_counter = memory_counter

    def _memory_count(self, override: Optional[int]) -> int:
        raw = (
            override
            if override is not None
            else self.memory_counter.successful_episode_count()
            if self.memory_counter is not None
            else 0
        )
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise ValueError("successful memory count must be a non-negative integer")
        return raw

    def score_step(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
        successful_memory_count: Optional[int] = None,
    ) -> ReliabilityResult:
        if not 0 <= step_index < len(plan.steps):
            raise IndexError(f"step_index {step_index} out of range")
        context = context or ReliabilityContext()
        scores = {
            "knowledge": self.knowledge.score(plan, step_index, state, context),
            "model": self.model.score(plan, step_index, state, context),
            "environment": self.environment.score(plan, step_index, state, context),
        }
        for expected, score in scores.items():
            if score.dimension != expected:
                raise ValueError(
                    f"Strategy registered as {expected!r} returned {score.dimension!r}"
                )
        count = self._memory_count(successful_memory_count)
        base = self.weight_policy.weights(count)
        effective = effective_weights(base, scores)
        notes = []
        if effective is None:
            probability = None
            notes.append("No positive-weight reliability signal was available")
        else:
            weights = effective.as_dict()
            probability = sum(
                weights[name] * float(scores[name].probability)
                for name in DIMENSIONS
                if scores[name].probability is not None
            )
            probability = max(0.0, min(1.0, float(probability)))
            if effective != base:
                notes.append("Weights were renormalized across available signals")
        step = plan.steps[step_index]
        return ReliabilityResult(
            plan_id=plan.plan_id,
            plan_version=plan.version,
            step_id=step.step_id,
            step_index=step_index,
            probability=probability,
            scores=scores,
            base_weights=base,
            effective_weights=effective,
            successful_memory_count=count,
            notes=tuple(notes),
        )

    def score_window(
        self,
        plan: Plan,
        step_indices: Sequence[int],
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
        successful_memory_count: Optional[int] = None,
    ) -> list[ReliabilityResult]:
        return [
            self.score_step(
                plan=plan,
                step_index=index,
                state=state,
                context=context,
                successful_memory_count=successful_memory_count,
            )
            for index in step_indices
        ]
