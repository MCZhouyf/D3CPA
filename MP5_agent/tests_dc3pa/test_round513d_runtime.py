import sqlite3

import pytest

from dc3pa.contracts import Action, Plan, PlanStep
from dc3pa.errors import ContractValidationError
from dc3pa.experiments.round513_instrumentation import (
    BehaviorReceiptV4_1,
    compare_behavior_receipts_v4_1,
)
from dc3pa.integration.runtime import Stage6ClosedLoopRunner
from dc3pa.integration.stage6_config import Stage6RuntimeConfig
from dc3pa.memory.snapshot import create_snapshot_manifest
from tests_dc3pa.helpers_stage6 import (
    FakeController,
    FakeGoal,
    FakeStateProvider,
    StaticPlanSource,
)


def _plan():
    return Plan(
        task="log",
        source="chrmlite_v4_1_one_call",
        metadata={"planner_call_count": 1, "same_generation_confidence": True},
        steps=[
            PlanStep(
                actions=[Action("find", {"obj": "log"})],
                metadata={
                    "local_subgoal": "find log",
                    "v4_1_confidence": "likely",
                    "v4_1_failure_mode": "none",
                    "v4_1_same_generation": True,
                    "v4_1_planner_call_count": 1,
                    "v4_1_prompt_id": "p",
                    "v4_1_parser_id": "r",
                },
            )
        ],
    )


def _manifest(tmp_path):
    database = tmp_path / "memory.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE guard(id INTEGER PRIMARY KEY)")
    manifest = create_snapshot_manifest(database, source_commit="test")
    path = tmp_path / "snapshot_manifest.json"
    manifest.to_json(path)
    return path


def _collection_config(tmp_path):
    return Stage6RuntimeConfig(
        mode="chrmlite_estimation_collection_v41",
        max_execution_attempts=1,
        planner_failure_policy="raise",
        memory_mode="evaluate_readonly",
        memory_snapshot_manifest=str(_manifest(tmp_path)),
        telemetry_enabled=True,
        record_legacy_workflow_memory=False,
        record_multimodal_memory=False,
        capture_initial_scene=False,
        capture_final_scene=False,
    )


class Observer:
    def __init__(self, prepared=True):
        self.prepared = prepared
        self.prepare_calls = 0
        self.finalize_calls = 0
        self.errors = []

    def prepare_attempt(self, **kwargs):
        self.prepare_calls += 1
        return self.prepared

    def finalize_attempt(self, **kwargs):
        self.finalize_calls += 1


def test_collection_mode_rejects_writes_and_separate_confidence(tmp_path):
    manifest = str(_manifest(tmp_path))
    with pytest.raises(ContractValidationError):
        Stage6RuntimeConfig(
            mode="chrmlite_estimation_collection_v41",
            memory_mode="evaluate_readonly",
            memory_snapshot_manifest=manifest,
            telemetry_enabled=True,
            record_legacy_workflow_memory=True,
            record_multimodal_memory=False,
        ).validate()
    with pytest.raises(ContractValidationError):
        Stage6RuntimeConfig(
            mode="chrmlite_estimation_collection_v41",
            memory_mode="evaluate_readonly",
            memory_snapshot_manifest=manifest,
            telemetry_enabled=True,
            record_legacy_workflow_memory=False,
            record_multimodal_memory=False,
            model_confidence_collection="passive_final_plan",
        ).validate()


def test_completed_receipt_blocks_controller_relaunch(tmp_path):
    plan_source = StaticPlanSource(_plan())
    controller = FakeController([True])
    observer = Observer(prepared=False)
    runner = Stage6ClosedLoopRunner(
        env=object(),
        config=_collection_config(tmp_path),
        reasoning_chain=plan_source,
        chrmlite_plan_source=plan_source,
        controller=controller,
        state_provider=FakeStateProvider("log"),
        goal_checker=FakeGoal([True]),
        episode_id_provider=lambda _attempt: "frozen-episode",
        development_shadow_observer=observer,
    )
    result = runner.run_task({"task": "log", "quantity": 1})
    assert not result.success
    assert result.failure_reason == "completed_receipt_prevents_relaunch"
    assert result.controller_execution_count == 0
    assert controller.calls == []
    assert observer.prepare_calls == 1 and observer.finalize_calls == 0


def test_collection_runtime_is_behavior_equivalent_for_identical_v41_receipt(tmp_path):
    plan = _plan()
    normal_source = StaticPlanSource(plan)
    normal_controller = FakeController([True])
    normal = Stage6ClosedLoopRunner(
        env=object(),
        config=Stage6RuntimeConfig(
            mode="reasoning_only",
            max_execution_attempts=1,
            record_legacy_workflow_memory=False,
            record_multimodal_memory=False,
            capture_initial_scene=False,
            capture_final_scene=False,
        ),
        reasoning_chain=normal_source,
        controller=normal_controller,
        state_provider=FakeStateProvider("log"),
        goal_checker=FakeGoal([True]),
    ).run_task({"task": "log", "quantity": 1})

    collection_source = StaticPlanSource(plan)
    collection_controller = FakeController([True])
    observer = Observer()
    collection = Stage6ClosedLoopRunner(
        env=object(),
        config=_collection_config(tmp_path),
        reasoning_chain=collection_source,
        chrmlite_plan_source=collection_source,
        controller=collection_controller,
        state_provider=FakeStateProvider("log"),
        goal_checker=FakeGoal([True]),
        development_shadow_observer=observer,
    ).run_task({"task": "log", "quantity": 1})

    action = plan.steps[0].actions[0].to_dict()
    common = {
        "subgoal": "find log",
        "action": action,
        "evaluation_before_action_calls": 0,
        "budget_profile_id": "synthetic-identical-budget",
        "outcome": "success",
    }
    left = BehaviorReceiptV4_1(
        planner_calls=len(normal_source.calls),
        controller_calls=len(normal_controller.calls),
        **common,
    )
    right = BehaviorReceiptV4_1(
        planner_calls=len(collection_source.calls),
        controller_calls=len(collection_controller.calls),
        **common,
    )
    equivalent, mismatches = compare_behavior_receipts_v4_1(left, right)
    assert normal.success and collection.success
    assert equivalent and mismatches == ()
    assert normal.evaluation_count == collection.evaluation_count == 0
    assert observer.prepare_calls == observer.finalize_calls == 1
