#!/usr/bin/env python3
"""Offline Stage-4 dual-chain repair/revalidation smoke demo."""

from __future__ import annotations

import sys
from pathlib import Path

_MP5_ROOT = Path(__file__).resolve().parents[1]
if str(_MP5_ROOT) not in sys.path:
    sys.path.insert(0, str(_MP5_ROOT))

import json

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.evaluation import EvaluationReport, PlanEdit
from dc3pa.planner import HighFrequencyDualChainPlanner
from dc3pa.reliability import DimensionScore, ReliabilityResult, StrategyWeights


class StaticReasoningChain:
    def __init__(self, plan: Plan):
        self.plan_value = plan

    def plan(self, task, state, context=None):
        return self.plan_value


class ScriptedReliabilityModel:
    def score_window(
        self,
        plan,
        step_indices,
        state,
        context=None,
        successful_memory_count=None,
    ):
        results = []
        for index in step_indices:
            low = plan.version == 1 and index == 0
            probability = 0.3 if low else 0.95
            scores = {
                "knowledge": DimensionScore.unavailable("knowledge", "demo"),
                "model": DimensionScore("model", probability, True, reason="demo"),
                "environment": DimensionScore.unavailable("environment", "demo"),
            }
            results.append(
                ReliabilityResult(
                    plan_id=plan.plan_id,
                    plan_version=plan.version,
                    step_id=plan.steps[index].step_id,
                    step_index=index,
                    probability=probability,
                    scores=scores,
                    base_weights=StrategyWeights(0.0, 1.0, 0.0),
                    effective_weights=StrategyWeights(0.0, 1.0, 0.0),
                    successful_memory_count=0,
                )
            )
        return results


class PrerequisiteEvaluationChain:
    def evaluate(self, request):
        target = request.plan.steps[request.step_indices[0]]
        if request.plan.version > 1:
            return EvaluationReport.accepted_plan(
                request.plan, "The revised step passed detailed evaluation."
            )
        prerequisite = PlanStep(
            step_id="find-pickaxe",
            actions=[Action("find", {"obj": "wooden_pickaxe"})],
        )
        return EvaluationReport(
            plan_id=request.plan.plan_id,
            plan_version=request.plan.version,
            summary="Insert the missing tool acquisition step.",
            edits=(
                PlanEdit(
                    operation="insert_before",
                    target_step_id=target.step_id,
                    steps=(prerequisite,),
                    edit_id="insert-pickaxe",
                    rationale="The mining step requires a wooden pickaxe.",
                ),
            ),
        )


def main() -> int:
    initial = Plan(
        task="obtain cobblestone",
        plan_id="initial-plan",
        steps=[
            PlanStep(
                step_id="mine-cobblestone",
                actions=[
                    Action(
                        "mine",
                        {"obj": "cobblestone", "tool": "wooden_pickaxe"},
                    )
                ],
            )
        ],
    )
    planner = HighFrequencyDualChainPlanner(
        StaticReasoningChain(initial),
        ScriptedReliabilityModel(),
        PrerequisiteEvaluationChain(),
    )
    outcome = planner.plan_with_outcome(
        initial.task,
        AgentState(task=initial.task),
    )
    assert outcome.revision_count == 1
    assert outcome.final_plan.steps[0].step_id == "find-pickaxe"
    assert any(item.window.forced for item in outcome.trigger_observations)
    print(json.dumps(outcome.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
