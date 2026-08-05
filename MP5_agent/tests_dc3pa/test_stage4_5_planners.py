from pathlib import Path

import pytest

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.evaluation import EvaluationReport, PlanEdit
from dc3pa.observability import JsonlTraceWriter
from dc3pa.planner import AdaptiveCognitiveControlPlanner, HighFrequencyDualChainPlanner
from dc3pa.reliability import AdaptiveTriggerConfig, DualChainConfig, ReliabilityContext
from tests_dc3pa.helpers_stage3_5 import (
    FunctionEvaluationChain,
    FunctionReliabilityModel,
    StaticReasoningChain,
    find_step,
    simple_plan,
)


def test_high_frequency_dual_chain_repairs_then_revalidates_revision():
    initial = simple_plan(2, task="repair")
    reasoning = StaticReasoningChain(initial)
    reliability = FunctionReliabilityModel(
        lambda plan, index: ((0.2, False) if plan.version == 1 and index == 0 else (0.95, False))
    )
    inserted = find_step("prerequisite")

    def evaluator(request):
        return EvaluationReport(
            plan_id=request.plan.plan_id,
            plan_version=request.plan.version,
            summary="insert prerequisite",
            edits=(
                PlanEdit(
                    "insert_before",
                    request.plan.steps[request.step_indices[0]].step_id,
                    (inserted,),
                ),
            ),
        )

    chain = FunctionEvaluationChain(evaluator)
    planner = HighFrequencyDualChainPlanner(
        reasoning,
        reliability,
        chain,
        config=DualChainConfig(confidence_threshold=0.8, max_revision_rounds=2),
    )
    outcome = planner.plan_with_outcome(
        initial.task,
        AgentState(task=initial.task),
        ReliabilityContext(task_context=initial.task),
    )
    assert outcome.revision_count == 1
    assert outcome.final_plan.version == 2
    assert outcome.final_plan.steps[0].step_id == inserted.step_id
    assert chain.requests[0].step_indices == (0,)
    assert any(item.window.forced for item in outcome.trigger_observations)
    assert all(item.window.interval == 1 for item in outcome.trigger_observations)


def test_no_patch_is_recorded_as_unresolved_without_mutating_plan():
    initial = simple_plan(1, task="unresolved")
    chain = FunctionEvaluationChain(
        lambda request: EvaluationReport.unresolved(request.plan, "need full replan")
    )
    planner = HighFrequencyDualChainPlanner(
        StaticReasoningChain(initial),
        FunctionReliabilityModel(lambda plan, index: (0.1, False)),
        chain,
    )
    outcome = planner.plan_with_outcome(initial.task, AgentState(task=initial.task))
    assert outcome.final_plan is initial
    assert outcome.revision_count == 0
    assert outcome.unresolved[0]["reason"] == "request_replan"
    assert outcome.unresolved[0]["hard_conflict"] is False


def test_non_conflict_unresolved_from_superseded_plan_does_not_block_final_plan():
    initial = simple_plan(2, task="superseded")
    inserted = find_step("fix")
    calls = []

    def evaluator(request):
        calls.append(request.plan.version)
        if len(calls) == 1:
            return EvaluationReport.unresolved(request.plan, "provider format issue")
        return EvaluationReport(
            plan_id=request.plan.plan_id,
            plan_version=request.plan.version,
            summary="insert fix",
            edits=(
                PlanEdit(
                    "insert_before",
                    request.plan.steps[1].step_id,
                    (inserted,),
                ),
            ),
        )

    planner = AdaptiveCognitiveControlPlanner(
        StaticReasoningChain(initial),
        FunctionReliabilityModel(
            lambda plan, index: (0.7, False)
            if plan.version == 1
            else (0.95, False)
        ),
        FunctionEvaluationChain(evaluator),
        trigger_config=AdaptiveTriggerConfig(
            threshold=0.8,
            initial_interval=1,
            window_size=1,
            maximum_interval=1,
        ),
        dual_chain_config=DualChainConfig(confidence_threshold=0.8, max_revision_rounds=2),
    )

    outcome = planner.plan_with_outcome(initial.task, AgentState(task=initial.task))

    assert calls[:2] == [1, 1]
    assert outcome.revision_count == 1
    assert outcome.unresolved == ()


def test_adaptive_planner_uses_variable_windows_and_requests_evaluation():
    initial = simple_plan(7, task="adaptive")

    def scores(plan, index):
        return (0.9, False) if index < 3 else (0.7, False)

    chain = FunctionEvaluationChain(
        lambda request: EvaluationReport.unresolved(request.plan, "no safe local patch")
    )
    planner = AdaptiveCognitiveControlPlanner(
        StaticReasoningChain(initial),
        FunctionReliabilityModel(scores),
        chain,
        trigger_config=AdaptiveTriggerConfig(
            threshold=0.8,
            initial_interval=3,
            window_size=3,
            maximum_interval=8,
        ),
    )
    outcome = planner.plan_with_outcome(initial.task, AgentState(task=initial.task))
    assert [item.window.step_indices for item in outcome.trigger_observations] == [
        (0, 1, 2),
        (3, 4, 5, 6),
    ]
    assert outcome.trigger_observations[0].next_interval == 4
    assert outcome.trigger_observations[1].low_confidence
    assert len(chain.requests) == 1
    assert chain.requests[0].step_indices == (3, 4, 5, 6)


def test_hard_knowledge_conflict_overrides_high_average_confidence():
    initial = simple_plan(3, task="hard")
    chain = FunctionEvaluationChain(
        lambda request: EvaluationReport.unresolved(request.plan, "hard conflict")
    )
    reliability = FunctionReliabilityModel(
        lambda plan, index: (0.95, index == 1)
    )
    planner = AdaptiveCognitiveControlPlanner(
        StaticReasoningChain(initial),
        reliability,
        chain,
        trigger_config=AdaptiveTriggerConfig(initial_interval=3),
    )
    outcome = planner.plan_with_outcome(initial.task, AgentState(task=initial.task))
    assert outcome.trigger_observations[0].monitored_confidence == pytest.approx(0.95)
    assert outcome.trigger_observations[0].hard_conflict
    assert len(chain.requests) == 1


def test_planner_writes_auditable_trace_without_raw_image(tmp_path: Path):
    initial = simple_plan(1, task="trace")
    trace_path = tmp_path / "trace.jsonl"
    planner = HighFrequencyDualChainPlanner(
        StaticReasoningChain(initial),
        FunctionReliabilityModel(lambda plan, index: (0.95, False)),
        FunctionEvaluationChain(
            lambda request: EvaluationReport.unresolved(request.plan, "unused")
        ),
        trace_writer=JsonlTraceWriter(trace_path),
    )
    planner.create_plan(
        initial.task,
        AgentState(task=initial.task),
        context={"image": object(), "task_context": "trace"},
    )
    text = trace_path.read_text(encoding="utf-8")
    assert "reasoning_plan_created" in text
    assert "cognitive_control_complete" in text
    assert "<object object" not in text


def test_evaluation_may_explicitly_accept_low_score_without_mutating_plan():
    initial = simple_plan(1, task="accepted")
    chain = FunctionEvaluationChain(
        lambda request: EvaluationReport.accepted_plan(
            request.plan, "detailed evidence confirms the step is valid"
        )
    )
    planner = HighFrequencyDualChainPlanner(
        StaticReasoningChain(initial),
        FunctionReliabilityModel(lambda plan, index: (0.7, False)),
        chain,
    )
    outcome = planner.plan_with_outcome(initial.task, AgentState(task=initial.task))
    assert outcome.final_plan is initial
    assert not outcome.unresolved
    assert outcome.evaluation_reports[0].accepted


def test_reliability_context_is_preserved_for_reasoning_chain():
    initial = simple_plan(1, task="context")
    reasoning = StaticReasoningChain(initial)
    marker = object()
    planner = HighFrequencyDualChainPlanner(
        reasoning,
        FunctionReliabilityModel(lambda plan, index: (0.95, False)),
        FunctionEvaluationChain(
            lambda request: EvaluationReport.unresolved(request.plan, "unused")
        ),
    )
    planner.create_plan(
        initial.task,
        AgentState(task=initial.task),
        ReliabilityContext(
            task_context="context text",
            image=marker,
            image_vector=(1.0, 0.0),
            metadata={"source": "test"},
        ),
    )
    assert reasoning.contexts == [
        {
            "task_context": "context text",
            "image": marker,
            "image_vector": (1.0, 0.0),
            "source": "test",
        }
    ]


def test_reserved_reliability_context_fields_cannot_be_shadowed_by_metadata():
    initial = simple_plan(1, task="reserved")
    reasoning = StaticReasoningChain(initial)
    marker = object()
    planner = HighFrequencyDualChainPlanner(
        reasoning,
        FunctionReliabilityModel(lambda plan, index: (0.95, False)),
        FunctionEvaluationChain(
            lambda request: EvaluationReport.unresolved(request.plan, "unused")
        ),
    )
    planner.create_plan(
        initial.task,
        AgentState(task=initial.task),
        ReliabilityContext(
            task_context="real",
            image=marker,
            image_vector=(1, 2),
            metadata={
                "task_context": "shadow",
                "image": "shadow",
                "image_vector": "shadow",
            },
        ),
    )
    assert reasoning.contexts[0]["task_context"] == "real"
    assert reasoning.contexts[0]["image"] is marker
    assert reasoning.contexts[0]["image_vector"] == (1, 2)


def test_planner_rejects_task_mismatch_and_stale_reliability():
    initial = simple_plan(1, task="expected")
    planner = HighFrequencyDualChainPlanner(
        StaticReasoningChain(initial),
        FunctionReliabilityModel(lambda plan, index: (0.95, False)),
        FunctionEvaluationChain(
            lambda request: EvaluationReport.unresolved(request.plan, "unused")
        ),
    )
    with pytest.raises(ValueError):
        planner.create_plan("expected", AgentState(task="different"))

    class StaleModel:
        def score_window(self, plan, step_indices, state, context=None, successful_memory_count=None):
            result = FunctionReliabilityModel(lambda p, i: (0.95, False)).score_window(
                plan, step_indices, state, context
            )[0]
            return [
                type(result)(
                    plan_id="stale",
                    plan_version=result.plan_version,
                    step_id=result.step_id,
                    step_index=result.step_index,
                    probability=result.probability,
                    scores=result.scores,
                    base_weights=result.base_weights,
                    effective_weights=result.effective_weights,
                    successful_memory_count=result.successful_memory_count,
                )
            ]

    stale_planner = HighFrequencyDualChainPlanner(
        StaticReasoningChain(initial),
        StaleModel(),
        FunctionEvaluationChain(
            lambda request: EvaluationReport.unresolved(request.plan, "unused")
        ),
    )
    with pytest.raises(ValueError, match="stale or misaligned"):
        stale_planner.create_plan(initial.task, AgentState(task=initial.task))


def test_hard_conflict_cannot_be_silently_accepted_by_evaluator():
    initial = simple_plan(1, task="hard-accept")
    planner = HighFrequencyDualChainPlanner(
        StaticReasoningChain(initial),
        FunctionReliabilityModel(lambda plan, index: (0.95, True)),
        FunctionEvaluationChain(
            lambda request: EvaluationReport.accepted_plan(
                request.plan, "provider attempted to override conflict"
            )
        ),
    )
    outcome = planner.plan_with_outcome(initial.task, AgentState(task=initial.task))
    assert outcome.unresolved[0]["reason"] == "accepted_despite_hard_conflict"


def test_material_repair_runs_after_evaluation_patch_without_extra_revision():
    initial = Plan(
        task="cobblestone",
        steps=[
            PlanStep(actions=[Action("equip", {"obj": "wooden pickaxe"})]),
        ],
    )
    craft_pickaxe = PlanStep(
        actions=[
            Action(
                "craft",
                {
                    "obj": {"wooden pickaxe": 1},
                    "materials": {"planks": 3, "stick": 2},
                    "platform": "crafting table",
                },
            )
        ]
    )

    def evaluator(request):
        return EvaluationReport(
            plan_id=request.plan.plan_id,
            plan_version=request.plan.version,
            summary="insert missing wooden pickaxe craft",
            edits=(
                PlanEdit(
                    "insert_before",
                    request.plan.steps[0].step_id,
                    (craft_pickaxe,),
                ),
            ),
        )

    def scores(plan, index):
        if plan.version == 1:
            return (0.0, True)
        return (0.95, False)

    planner = HighFrequencyDualChainPlanner(
        StaticReasoningChain(initial),
        FunctionReliabilityModel(scores),
        FunctionEvaluationChain(evaluator),
        config=DualChainConfig(confidence_threshold=0.8, max_revision_rounds=1),
    )
    outcome = planner.plan_with_outcome(
        initial.task,
        AgentState(task=initial.task, inventory={}),
    )

    assert outcome.revision_count == 1
    assert outcome.final_plan.version == 2
    # G0 permits evaluator-authored edits, but never appends controller-owned
    # acquisition or craft steps to repair the edit's missing materials.
    assert not any(
        step.metadata.get("dc3pa_auto_material_repair")
        for step in outcome.final_plan.steps
    )
    assert len(outcome.final_plan.steps) == 2
    assert outcome.unresolved == ()


def test_material_repair_handles_hard_conflict_when_evaluator_requests_replan():
    initial = Plan(
        task="cobblestone",
        steps=[
            PlanStep(
                actions=[
                    Action(
                        "craft",
                        {
                            "obj": {"wooden pickaxe": 1},
                            "materials": {"planks": 3, "stick": 2},
                            "platform": "crafting table",
                        },
                    )
                ]
            ),
        ],
    )

    def scores(plan, index):
        if plan.version == 1:
            return (0.0, True)
        return (0.95, False)

    planner = HighFrequencyDualChainPlanner(
        StaticReasoningChain(initial),
        FunctionReliabilityModel(scores),
        FunctionEvaluationChain(
            lambda request: EvaluationReport.unresolved(
                request.plan,
                "provider returned an unusable patch",
            )
        ),
        config=DualChainConfig(confidence_threshold=0.8, max_revision_rounds=1),
    )
    outcome = planner.plan_with_outcome(
        initial.task,
        AgentState(task=initial.task, inventory={}),
    )

    assert outcome.revision_count == 0
    assert outcome.final_plan.version == 1
    assert outcome.final_plan.source == "reasoning_chain"
    assert outcome.unresolved
    assert outcome.unresolved[-1]["reason"] == "request_replan"
