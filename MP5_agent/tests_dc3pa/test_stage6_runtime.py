from __future__ import annotations

import json

import pytest

from dc3pa.integration import Stage6ClosedLoopRunner, Stage6RuntimeConfig
from dc3pa.integration.controller import ExecutionResult
from tests_dc3pa.helpers_stage6 import (
    FakeCognitivePlanner,
    FakeController,
    FakeGoal,
    FakeLegacyMemorySink,
    FakeMultimodalMemorySink,
    FakeReflexion,
    FakeStateProvider,
    RaisingCognitivePlanner,
    RaisingPlanSource,
    StaticPlanSource,
    simple_plan,
)


class ResettableEnv:
    def __init__(self):
        self.reset_calls = 0

    def reset(self):
        self.reset_calls += 1
        return {"reset": self.reset_calls}


def build_runtime(
    *,
    mode="reasoning_only",
    controller_results=(True,),
    goal_values=(True,),
    reasoning=None,
    cognitive=None,
    config_overrides=None,
    legacy_memory=None,
    multimodal_memory=None,
    state_provider=None,
    reflexion=None,
    env=None,
):
    plan = simple_plan()
    reasoning = reasoning or StaticPlanSource(plan)
    config = Stage6RuntimeConfig(
        mode=mode,
        max_execution_attempts=3,
        **(config_overrides or {}),
    )
    return Stage6ClosedLoopRunner(
        env=env or ResettableEnv(),
        config=config,
        reasoning_chain=reasoning,
        legacy_plan_source=reasoning if mode == "mp5_legacy" else None,
        cognitive_planner=cognitive,
        controller=FakeController(controller_results),
        state_provider=state_provider or FakeStateProvider(),
        goal_checker=FakeGoal(goal_values),
        reflexion=reflexion,
        legacy_memory_sink=legacy_memory,
        multimodal_memory_sink=multimodal_memory,
    )


def test_reasoning_only_success_records_both_memories_once():
    legacy = FakeLegacyMemorySink()
    multimodal = FakeMultimodalMemorySink()
    runtime = build_runtime(legacy_memory=legacy, multimodal_memory=multimodal)
    result = runtime.run_task({"task": "log", "quantity": 1})
    assert result.success
    assert result.controller_execution_count == 1
    assert result.reactive_replan_count == 0
    assert result.pre_execution_revision_count == 0
    assert len(legacy.calls) == 1
    assert len(multimodal.episodes) == 1
    assert len(multimodal.episodes[0].scenes) == 2
    json.dumps(result.to_dict())


def test_failure_then_success_counts_reactive_replan_and_reflection():
    reflection = FakeReflexion()
    runtime = build_runtime(
        controller_results=(False, True),
        goal_values=(True,),
        reflexion=reflection,
    )
    result = runtime.run_task({"task": "log"})
    assert result.success
    assert result.controller_execution_count == 2
    assert result.reactive_replan_count == 1
    assert len(reflection.calls) == 1
    assert any(event.event_type == "reactive_replan_scheduled" for event in result.events)


def test_dc3pa_metrics_are_separate_from_reactive_replanning():
    plan = simple_plan()
    cognitive = FakeCognitivePlanner(plan, revision_count=2, evaluations=3)
    runtime = build_runtime(mode="dc3pa", cognitive=cognitive)
    result = runtime.run_task({"task": "log"})
    assert result.success
    assert result.pre_execution_revision_count == 2
    assert result.evaluation_count == 3
    assert result.reactive_replan_count == 0


def test_unresolved_dc3pa_plan_is_blocked_by_default_without_execution_or_memory():
    plan = simple_plan()
    legacy = FakeLegacyMemorySink()
    multimodal = FakeMultimodalMemorySink()
    runtime = build_runtime(
        mode="dc3pa",
        cognitive=FakeCognitivePlanner(plan, unresolved=({"reason": "hard conflict"},)),
        legacy_memory=legacy,
        multimodal_memory=multimodal,
    )
    result = runtime.run_task({"task": "log"})
    assert not result.success
    assert result.pre_execution_block_count == 1
    assert result.controller_execution_count == 0
    assert not legacy.calls and not multimodal.episodes
    assert result.failure_reason == "unresolved_dc3pa_plan"


def test_non_blocking_unresolved_metadata_allows_controller_execution():
    plan = simple_plan()
    runtime = build_runtime(
        mode="dc3pa",
        cognitive=FakeCognitivePlanner(
            plan,
            unresolved=(
                {
                    "reason": "request_replan",
                    "hard_conflict": False,
                    "summary": "superseded provider formatting issue",
                },
            ),
        ),
    )
    result = runtime.run_task({"task": "log"})
    assert result.success
    assert result.controller_execution_count == 1
    event_names = [event.event_type for event in result.events]
    assert "dc3pa_plan_unresolved" in event_names
    assert "non_blocking_dc3pa_unresolved" in event_names


def test_unresolved_plan_can_explicitly_fallback_to_reasoning_only():
    plan = simple_plan()
    reasoning = StaticPlanSource(plan)
    runtime = build_runtime(
        mode="dc3pa",
        reasoning=reasoning,
        cognitive=FakeCognitivePlanner(plan, unresolved=({"reason": "unresolved"},)),
        config_overrides={"unresolved_plan_policy": "reasoning_only"},
    )
    result = runtime.run_task({"task": "log"})
    assert result.success
    assert result.planning_fallback_count == 1
    assert result.controller_execution_count == 1
    assert reasoning.calls


def test_dc3pa_exception_falls_back_but_is_not_reported_as_validated_plan():
    plan = simple_plan()
    runtime = build_runtime(
        mode="dc3pa",
        reasoning=StaticPlanSource(plan),
        cognitive=RaisingCognitivePlanner(),
    )
    result = runtime.run_task({"task": "log"})
    assert result.success
    assert result.planning_fallback_count == 1
    event_names = [event.event_type for event in result.events]
    assert "dc3pa_planning_failed" in event_names
    assert "reasoning_fallback_used" in event_names


def test_non_retryable_planning_error_does_not_call_reasoning_fallback():
    plan = simple_plan()
    reasoning = StaticPlanSource(plan)
    runtime = build_runtime(
        mode="dc3pa",
        reasoning=reasoning,
        cognitive=RaisingCognitivePlanner(
            PermissionError("token quota is not enough")
        ),
    )
    result = runtime.run_task({"task": "log"})
    assert not result.success
    assert result.controller_execution_count == 0
    assert result.failure_reason == "dc3pa_planning_failed:PermissionError"
    assert reasoning.calls == []
    event_names = [event.event_type for event in result.events]
    assert "dc3pa_planning_failed" in event_names
    assert "reasoning_fallback_used" not in event_names


def test_planner_failure_can_return_clean_failure_without_controller_call():
    runtime = build_runtime(
        mode="dc3pa",
        reasoning=RaisingPlanSource(),
        cognitive=RaisingCognitivePlanner(),
        config_overrides={"planner_failure_policy": "return_failure"},
    )
    result = runtime.run_task({"task": "log"})
    assert not result.success
    assert result.controller_execution_count == 0
    assert result.failure_reason.startswith("dc3pa_planning_failed")


def test_controller_exception_is_structured_and_can_replan():
    runtime = build_runtime(
        controller_results=(RuntimeError("boom"), True),
        goal_values=(True,),
    )
    result = runtime.run_task({"task": "log"})
    assert result.success
    assert result.reactive_replan_count == 1
    assert any(event.event_type == "controller_exception" for event in result.events)


def test_controller_success_without_goal_is_not_task_success_and_writes_no_memory():
    legacy = FakeLegacyMemorySink()
    multimodal = FakeMultimodalMemorySink()
    runtime = build_runtime(
        controller_results=(True, True, True),
        goal_values=(False, False, False),
        legacy_memory=legacy,
        multimodal_memory=multimodal,
    )
    result = runtime.run_task({"task": "log"})
    assert not result.success
    assert result.failure_reason == "goal_not_achieved"
    assert not legacy.calls and not multimodal.episodes


def test_memory_failure_trace_policy_does_not_relabel_environment_success():
    runtime = build_runtime(
        legacy_memory=FakeLegacyMemorySink(RuntimeError("disk full")),
        multimodal_memory=FakeMultimodalMemorySink(RuntimeError("db locked")),
    )
    result = runtime.run_task({"task": "log"})
    assert result.success
    assert result.memory_recorded is False
    assert any(event.event_type.endswith("memory_record_failed") for event in result.events)


def test_memory_failure_raise_policy_is_explicit():
    runtime = build_runtime(
        legacy_memory=FakeLegacyMemorySink(RuntimeError("disk full")),
        config_overrides={"memory_failure_policy": "raise"},
    )
    with pytest.raises(RuntimeError, match="disk full"):
        runtime.run_task({"task": "log"})


def test_goal_check_exception_is_structured_and_treated_as_incomplete_by_default():
    runtime = build_runtime(
        controller_results=(True, True, True),
        goal_values=(RuntimeError("checker broke"), False, False),
    )
    result = runtime.run_task({"task": "log"})
    assert not result.success
    assert any(event.event_type == "goal_check_exception" for event in result.events)
    assert result.reactive_replan_count == 2


def test_declared_mine_yield_false_negative_uses_goal_check_before_replanning():
    execution = ExecutionResult(
        success=False,
        underground=False,
        feedback="Declared mine action failed: declared_mine_no_observed_yield",
        suggestion="Re-plan explicitly from the observed environment state.",
        raw={"reason_code": "declared_mine_no_observed_yield"},
    )
    reasoning = StaticPlanSource(simple_plan())
    runtime = build_runtime(
        controller_results=(execution,),
        goal_values=(True,),
        reasoning=reasoning,
    )

    result = runtime.run_task({"task": "log"})

    assert result.success
    assert result.controller_execution_count == 1
    assert len(reasoning.calls) == 1
    assert any(
        event.event_type == "goal_checked_after_declared_yield_false_negative"
        for event in result.events
    )


def test_final_scene_capture_failure_does_not_relabel_task_success_under_trace_policy():
    state = FakeStateProvider(fail_after=1)
    multimodal = FakeMultimodalMemorySink()
    runtime = build_runtime(
        state_provider=state,
        multimodal_memory=multimodal,
        config_overrides={"capture_initial_scene": True, "capture_final_scene": True},
    )
    result = runtime.run_task({"task": "log"})
    assert result.success
    assert any(event.event_type == "final_state_snapshot_failed" for event in result.events)
    assert len(multimodal.episodes) == 1
    assert len(multimodal.episodes[0].scenes) == 1


def test_mismatched_plan_task_is_blocked_before_controller():
    runtime = build_runtime(reasoning=StaticPlanSource(simple_plan(task="diamond")))
    result = runtime.run_task({"task": "log"})
    assert not result.success
    assert result.controller_execution_count == 0
    assert result.failure_reason == "unhandled_planning_failure"

def test_reactive_replan_resets_environment_and_clears_underground_state():
    env = ResettableEnv()
    runtime = build_runtime(
        controller_results=(False, True),
        goal_values=(True,),
        env=env,
    )

    result = runtime.run_task({"task": "log"}, underground=True)

    assert result.success
    assert env.reset_calls == 1
    assert runtime.controller.calls[0][3] is True
    assert runtime.controller.calls[1][3] is False
    reset_events = [
        event for event in result.events if event.event_type == "environment_reset_completed"
    ]
    assert len(reset_events) == 1
    assert reset_events[0].attempt == 2


def test_reactive_replan_notifies_state_provider_after_environment_reset():
    class ResetAwareStateProvider(FakeStateProvider):
        def __init__(self):
            super().__init__()
            self.reset_notifications = 0

        def on_environment_reset(self):
            self.reset_notifications += 1

    state_provider = ResetAwareStateProvider()
    runtime = build_runtime(
        controller_results=(False, True),
        goal_values=(True,),
        state_provider=state_provider,
    )

    result = runtime.run_task({"task": "log"})

    assert result.success
    assert state_provider.reset_notifications == 1


def test_missing_declared_prerequisite_preserves_world_for_replan():
    env = ResettableEnv()
    missing_planks = ExecutionResult(
        success=False,
        underground=False,
        feedback="Missing declared craft materials: planks.",
        suggestion="Re-plan explicitly from the observed environment state.",
        raw={
            "reason_code": "missing_declared_materials",
            "missing_requirements": ["planks"],
        },
    )
    runtime = build_runtime(
        controller_results=(missing_planks, True),
        goal_values=(True,),
        env=env,
    )

    result = runtime.run_task({"task": "log"})

    assert result.success
    assert env.reset_calls == 0
    preserved = [
        event for event in result.events
        if event.event_type == "environment_preserved_for_replan"
    ]
    assert len(preserved) == 1
    assert preserved[0].payload["reason_code"] == "missing_declared_materials"


def test_retry_stops_when_environment_cannot_be_reset():
    runtime = build_runtime(
        controller_results=(False, True),
        goal_values=(True,),
        env=object(),
    )

    result = runtime.run_task({"task": "log"})

    assert not result.success
    assert result.failure_reason == "environment_reset_unavailable"
    assert result.controller_execution_count == 1
    assert any(event.event_type == "environment_reset_failed" for event in result.events)
