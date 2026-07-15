from __future__ import annotations

import json

from dc3pa.contracts import Action, Plan, PlanStep
from dc3pa.integration import ExecutionResult, Stage6ClosedLoopRunner, Stage6RuntimeConfig
from dc3pa.integration.execution_observer import make_execution_event
from dc3pa.memory.calibration_store import CalibrationEpisodeStore
from dc3pa.reliability import (
    ConfidenceObservationCollector,
    DimensionScore,
    ModelConfidenceObservation,
    ReliabilityContext,
    join_confidence_with_execution,
)
from tests_dc3pa.helpers_stage6 import (
    FakeController,
    FakeGoal,
    FakeStateProvider,
    StaticPlanSource,
)


def _plan(version=1):
    return Plan(
        task="log",
        plan_id="p",
        version=version,
        steps=[
            PlanStep(step_id="s0", actions=[Action("find", {"obj": "log"})]),
            PlanStep(step_id="s1", actions=[Action("mine", {"obj": "log", "tool": ""})]),
        ],
    )


class PassiveScorer:
    def __init__(self, observer):
        self.observer = observer
        self.calls = []

    def score(self, plan, step_index, state, context=None):
        self.calls.append((plan.plan_id, plan.version, step_index, state, context))
        step = plan.steps[step_index]
        self.observer.record(
            ModelConfidenceObservation(
                plan_id=plan.plan_id,
                plan_version=plan.version,
                step_id=step.step_id,
                step_index=step_index,
                request_hash=f"h-{step_index}",
                implementation="ordinal_v2",
                confidence_level="likely",
                base_probability=0.7,
                decision_probability=0.7,
                model_id="gpt-test",
                prompt_version="ordinal-v1",
                prompt_sha256="prompt",
            )
        )
        return DimensionScore("model", 0.7, True)


def test_runtime_passive_collection_persists_only_final_plan_observations(tmp_path):
    plan = _plan()
    observer = ConfidenceObservationCollector()
    scorer = PassiveScorer(observer)
    telemetry = (
        make_execution_event(
            "step_finished",
            plan_id="p",
            plan_version=1,
            step_id="s0",
            step_index=0,
            status="success",
        ),
        make_execution_event(
            "step_finished",
            plan_id="p",
            plan_version=1,
            step_id="s1",
            step_index=1,
            status="skipped_satisfied",
        ),
        make_execution_event(
            "step_finished",
            plan_id="p",
            plan_version=0,
            step_id="old",
            step_index=0,
            status="failure",
        ),
    )
    runtime = Stage6ClosedLoopRunner(
        env=object(),
        config=Stage6RuntimeConfig(
            mode="reasoning_only",
            max_execution_attempts=1,
            telemetry_enabled=True,
            calibration_log_dir=str(tmp_path / "cal"),
            model_confidence_collection="passive_final_plan",
        ),
        reasoning_chain=StaticPlanSource(plan),
        controller=FakeController(
            (
                ExecutionResult(
                    success=True,
                    underground=False,
                    raw={"success": True},
                    telemetry=telemetry,
                ),
            )
        ),
        state_provider=FakeStateProvider(),
        goal_checker=FakeGoal((True,)),
        calibration_store=CalibrationEpisodeStore(tmp_path / "cal"),
        confidence_observer=observer,
        passive_confidence_scorer=scorer,
    )

    before = json.dumps(plan.to_dict(), sort_keys=True)
    result = runtime.run_task({"task": "log"})
    after = json.dumps(plan.to_dict(), sort_keys=True)

    assert result.success
    assert before == after
    assert len(scorer.calls) == 2
    payload = next(runtime.calibration_store.iter_payloads())["record"]
    assert len(payload["confidence_observations"]) == 2
    joined, excluded = join_confidence_with_execution(
        episode_id=payload["episode_id"],
        plan=payload["plan"],
        telemetry=payload["telemetry"],
        observations=payload["confidence_observations"],
    )
    assert [item.label for item in joined] == [1, 1]
    assert excluded == ()


def test_runtime_clears_stale_observations_between_reactive_attempts(tmp_path):
    plan = _plan()
    observer = ConfidenceObservationCollector()
    stale = ModelConfidenceObservation(
        plan_id="p",
        plan_version=99,
        step_id="stale",
        step_index=0,
        request_hash="stale",
        implementation="ordinal_v2",
        confidence_level="likely",
        base_probability=0.7,
        decision_probability=0.7,
    )
    observer.record(stale)
    scorer = PassiveScorer(observer)
    runtime = Stage6ClosedLoopRunner(
        env=object(),
        config=Stage6RuntimeConfig(
            mode="reasoning_only",
            max_execution_attempts=1,
            calibration_log_dir=str(tmp_path / "cal"),
            model_confidence_collection="passive_final_plan",
        ),
        reasoning_chain=StaticPlanSource(plan),
        controller=FakeController((False,)),
        state_provider=FakeStateProvider(),
        goal_checker=FakeGoal((False,)),
        calibration_store=CalibrationEpisodeStore(tmp_path / "cal"),
        confidence_observer=observer,
        passive_confidence_scorer=scorer,
    )
    runtime.run_task({"task": "log"})
    payload = next(runtime.calibration_store.iter_payloads())["record"]
    assert all(item["plan_version"] == 1 for item in payload["confidence_observations"])


def test_step_label_join_excludes_failure_and_censored_correctly():
    observations = [
        ModelConfidenceObservation(
            plan_id="p",
            plan_version=1,
            step_id=step_id,
            step_index=index,
            request_hash=f"h{index}",
            implementation="ordinal_v2",
            confidence_level="likely",
            base_probability=0.7,
            decision_probability=0.7,
        )
        for index, step_id in enumerate(("ok", "bad", "censored"))
    ]
    plan = {
        "plan_id": "p",
        "version": 1,
        "steps": [{"step_id": "ok"}, {"step_id": "bad"}, {"step_id": "censored"}],
    }
    telemetry = (
        {"event_type": "step_finished", "plan_id": "p", "plan_version": 1, "step_id": "ok", "status": "success"},
        {"event_type": "step_finished", "plan_id": "p", "plan_version": 1, "step_id": "bad", "status": "failure"},
        {"event_type": "step_finished", "plan_id": "p", "plan_version": 1, "step_id": "censored", "status": "censored"},
    )
    joined, excluded = join_confidence_with_execution(
        episode_id="e",
        plan=plan,
        telemetry=telemetry,
        observations=observations,
    )
    assert [(item.step_id, item.label) for item in joined] == [("ok", 1), ("bad", 0)]
    assert [(item.step_id, item.reason) for item in excluded] == [("censored", "censored")]
