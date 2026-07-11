from dc3pa.contracts import AgentState
from dc3pa.evaluation import EvaluationRequest, build_evaluation_prompt
from dc3pa.reliability import (
    ConfidenceRequest,
    ReliabilityContext,
    build_verbal_confidence_prompt,
)
from tests_dc3pa.helpers_stage3_5 import reliability_result, simple_plan


def test_prompts_request_concise_auditable_output_not_hidden_reasoning():
    plan = simple_plan(1)
    state = AgentState(task=plan.task)
    confidence_prompt = build_verbal_confidence_prompt(
        ConfidenceRequest(plan, state, 0, ReliabilityContext(task_context="x"))
    )
    assert "do not provide hidden chain-of-thought" in confidence_prompt.lower()
    request = EvaluationRequest(
        plan=plan,
        state=state,
        step_indices=(0,),
        reliability=(reliability_result(plan, 0, 0.3),),
    )
    evaluation_prompt = build_evaluation_prompt(request)
    assert "do not reveal hidden chain-of-thought" in evaluation_prompt.lower()
    assert plan.steps[0].step_id in evaluation_prompt
