import json

import pytest

from dc3pa.contracts import AgentState, PlanStep
from dc3pa.errors import ContractValidationError
from dc3pa.evaluation import (
    CallableEvaluationProvider,
    EvaluationReport,
    EvaluationRequest,
    PlanEdit,
    PlanEditor,
    StructuredEvaluationChain,
)
from tests_dc3pa.helpers_stage3_5 import find_step, reliability_result, simple_plan


def test_plan_editor_applies_insert_replace_delete_atomically():
    plan = simple_plan(3)
    inserted = find_step("prerequisite")
    replacement = find_step("replacement")
    report = EvaluationReport(
        plan_id=plan.plan_id,
        plan_version=plan.version,
        summary="repair",
        edits=(
            PlanEdit("insert_before", plan.steps[1].step_id, (inserted,)),
            PlanEdit("replace", plan.steps[2].step_id, (replacement,)),
        ),
    )
    application = PlanEditor().apply(plan, report)
    revised = application.revised_plan
    assert revised.version == 2
    assert revised.parent_plan_id == plan.plan_id
    assert [step.step_id for step in revised.steps] == [
        plan.steps[0].step_id,
        inserted.step_id,
        plan.steps[1].step_id,
        replacement.step_id,
    ]
    assert [step.step_id for step in plan.steps] != [step.step_id for step in revised.steps]


def test_plan_editor_rejects_stale_unknown_and_empty_patches():
    plan = simple_plan(1)
    stale = EvaluationReport(
        plan_id="other",
        plan_version=1,
        summary="stale",
        edits=(PlanEdit("delete", plan.steps[0].step_id),),
    )
    with pytest.raises(ContractValidationError):
        PlanEditor().apply(plan, stale)

    emptying = EvaluationReport(
        plan_id=plan.plan_id,
        plan_version=plan.version,
        summary="delete all",
        edits=(PlanEdit("delete", plan.steps[0].step_id),),
    )
    with pytest.raises(ContractValidationError):
        PlanEditor().apply(plan, emptying)


def test_plan_editor_rewrites_duplicate_ids_from_patch_steps():
    plan = simple_plan(2)
    duplicate = find_step("duplicate", step_id=plan.steps[0].step_id)
    report = EvaluationReport(
        plan_id=plan.plan_id,
        plan_version=plan.version,
        summary="bad",
        edits=(PlanEdit("insert_before", plan.steps[1].step_id, (duplicate,)),),
    )
    application = PlanEditor().apply(plan, report)
    revised_ids = [step.step_id for step in application.revised_plan.steps]
    assert len(revised_ids) == len(set(revised_ids))
    assert revised_ids[0] == plan.steps[0].step_id
    assert revised_ids[1] != plan.steps[0].step_id
    assert application.revised_plan.steps[1].actions == duplicate.actions


def test_plan_editor_allows_replacement_to_reuse_target_step_id():
    plan = simple_plan(2)
    replacement = find_step("replacement", step_id=plan.steps[1].step_id)
    report = EvaluationReport(
        plan_id=plan.plan_id,
        plan_version=plan.version,
        summary="reuse replaced step id",
        edits=(PlanEdit("replace", plan.steps[1].step_id, (replacement,)),),
    )
    application = PlanEditor().apply(plan, report)
    assert [step.step_id for step in application.revised_plan.steps] == [
        plan.steps[0].step_id,
        plan.steps[1].step_id,
    ]
    assert application.revised_plan.steps[1].actions == replacement.actions


def test_plan_editor_rejects_duplicate_step_ids_in_input_plan():
    duplicate_id = "same-step-id"
    plan = simple_plan(1)
    duplicate_plan = type(plan)(
        task=plan.task,
        steps=[
            find_step("first", step_id=duplicate_id),
            find_step("second", step_id=duplicate_id),
        ],
    )
    report = EvaluationReport(
        plan_id=duplicate_plan.plan_id,
        plan_version=duplicate_plan.version,
        summary="input plan is already invalid",
        edits=(PlanEdit("delete", duplicate_plan.steps[0].step_id),),
    )
    with pytest.raises(ContractValidationError):
        PlanEditor().apply(duplicate_plan, report)


def test_structured_evaluation_chain_parses_fenced_json_and_checks_staleness():
    plan = simple_plan(1)
    state = AgentState(task=plan.task)
    request = EvaluationRequest(
        plan=plan,
        state=state,
        step_indices=(0,),
        reliability=(reliability_result(plan, 0, 0.2),),
    )
    replacement = find_step("safe")
    payload = {
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "summary": "replace unsafe step",
        "issues": [],
        "edits": [
            {
                "operation": "replace",
                "target_step_id": plan.steps[0].step_id,
                "steps": [replacement.to_dict()],
            }
        ],
        "replacement_steps": [],
        "request_replan": False,
    }
    provider = CallableEvaluationProvider(
        lambda prompt: "```json\n" + json.dumps(payload) + "\n```"
    )
    report = StructuredEvaluationChain(provider).evaluate(request)
    assert report.has_patch
    assert report.provider_metadata["provider_type"] == "CallableEvaluationProvider"

    payload["plan_version"] = 999
    with pytest.raises(ContractValidationError):
        StructuredEvaluationChain(
            CallableEvaluationProvider(lambda prompt: payload)
        ).evaluate(request)


def test_evaluation_provider_failure_can_request_replan_without_guessing():
    plan = simple_plan(1)
    request = EvaluationRequest(
        plan=plan,
        state=AgentState(task=plan.task),
        step_indices=(0,),
        reliability=(reliability_result(plan, 0, None),),
    )
    chain = StructuredEvaluationChain(
        CallableEvaluationProvider(lambda prompt: "not json"),
        failure_mode="request_replan",
    )
    report = chain.evaluate(request)
    assert report.request_replan
    assert not report.has_patch


def test_evaluation_report_requires_exactly_one_explicit_outcome():
    plan = simple_plan(1)
    with pytest.raises(ContractValidationError):
        EvaluationReport(
            plan_id=plan.plan_id,
            plan_version=plan.version,
            summary="ambiguous empty response",
        )
    with pytest.raises(ContractValidationError):
        EvaluationReport(
            plan_id=plan.plan_id,
            plan_version=plan.version,
            summary="conflicting",
            accepted=True,
            request_replan=True,
        )
    accepted = EvaluationReport.accepted_plan(plan, "validated without correction")
    assert accepted.accepted
    assert not accepted.has_patch


def test_evaluation_payload_rejects_string_booleans():
    plan = simple_plan(1)
    payload = {
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "summary": "bad boolean",
        "issues": [],
        "edits": [],
        "replacement_steps": [],
        "accepted": "false",
        "request_replan": False,
    }
    with pytest.raises(ContractValidationError):
        EvaluationReport.from_dict(payload, expected_plan=plan)


def test_plan_editor_rejects_duplicate_edit_ids():
    plan = simple_plan(2)
    first = PlanEdit(
        "insert_before",
        plan.steps[1].step_id,
        (find_step("a"),),
        edit_id="same",
    )
    second = PlanEdit(
        "insert_after",
        plan.steps[1].step_id,
        (find_step("b"),),
        edit_id="same",
    )
    report = EvaluationReport(
        plan_id=plan.plan_id,
        plan_version=plan.version,
        summary="duplicate edit identifiers",
        edits=(first, second),
    )
    with pytest.raises(ContractValidationError):
        PlanEditor().apply(plan, report)


def test_evaluation_rejects_unknown_issue_step_and_fractional_version():
    plan = simple_plan(1)
    base = {
        "plan_id": plan.plan_id,
        "summary": "invalid",
        "issues": [],
        "edits": [],
        "replacement_steps": [],
        "accepted": True,
        "request_replan": False,
    }
    with pytest.raises(ContractValidationError):
        EvaluationReport.from_dict({**base, "plan_version": 1.5}, expected_plan=plan)
    payload = {
        **base,
        "plan_version": plan.version,
        "issues": [
            {
                "step_id": "not-in-plan",
                "dimension": "model",
                "severity": "warning",
                "diagnosis": "bad reference",
                "evidence": {},
            }
        ],
    }
    with pytest.raises(ContractValidationError):
        EvaluationReport.from_dict(payload, expected_plan=plan)
