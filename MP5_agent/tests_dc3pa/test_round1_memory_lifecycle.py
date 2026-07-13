import sqlite3

import numpy as np
import pytest

from dc3pa.integration.execution_observer import make_execution_event
from dc3pa.integration.runtime import Stage6ClosedLoopRunner
from dc3pa.integration.stage6_config import Stage6RuntimeConfig
from dc3pa.memory.acquisition import AcquisitionStore, SuccessfulTrajectoryRecord
from dc3pa.memory.snapshot import (
    ReadOnlyMemoryError,
    SnapshotGuard,
    create_snapshot_manifest,
    open_sqlite_readonly,
)
from dc3pa.memory.multimodal_memory import MultimodalMemory, SuccessfulEpisode
from tests_dc3pa.helpers_stage6 import (
    FakeController,
    FakeGoal,
    FakeLegacyMemorySink,
    FakeMultimodalMemorySink,
    FakeStateProvider,
    StaticPlanSource,
    simple_plan,
)


def test_acquisition_store_commits_one_file_per_success(tmp_path):
    store = AcquisitionStore(tmp_path / "acquisition")
    record = SuccessfulTrajectoryRecord(
        episode_id="episode-1",
        task_name="obtain log",
        seed="7",
        plan={"steps": []},
        telemetry=(),
        scene_candidates=(),
    )
    path = store.commit_success(record)
    assert path.exists()
    assert store.count() == 1


def test_readonly_sqlite_rejects_writes_and_guard_stays_stable(tmp_path):
    db = tmp_path / "memory.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE exemplars(id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO exemplars(value) VALUES ('a')")

    manifest = create_snapshot_manifest(db, source_commit="test")
    with SnapshotGuard(manifest):
        with open_sqlite_readonly(db) as connection:
            assert connection.execute("SELECT COUNT(*) FROM exemplars").fetchone()[0] == 1
            with pytest.raises(sqlite3.OperationalError):
                connection.execute("INSERT INTO exemplars(value) VALUES ('b')")


def test_multimodal_memory_readonly_rejects_record_success(tmp_path):
    root = tmp_path / "memory"
    plan = simple_plan("log")
    with MultimodalMemory(root) as memory:
        assert memory.successful_episode_count() == 0

    with MultimodalMemory(root, readonly=True) as memory:
        with pytest.raises(ReadOnlyMemoryError):
            memory.record_success(SuccessfulEpisode(task_name="log", plan=plan))


def _successful_telemetry():
    return (
        make_execution_event(
            "action_started",
            plan_id="p",
            plan_version=1,
            step_id="s",
            step_index=0,
            action_index=0,
            rgb=np.zeros((2, 2, 3), dtype=np.uint8),
            inventory={"log": 0},
            action={"name": "find", "args": {"obj": "log"}},
            local_subgoal="find log",
        ),
        make_execution_event(
            "action_finished",
            plan_id="p",
            plan_version=1,
            step_id="s",
            step_index=0,
            action_index=0,
            status="success",
        ),
    )


def _runner(config, *, controller, legacy_sink=None, multimodal_sink=None, acquisition_store=None):
    plan = simple_plan("log")
    return Stage6ClosedLoopRunner(
        env=object(),
        config=config,
        reasoning_chain=StaticPlanSource(plan),
        controller=controller,
        state_provider=FakeStateProvider("log"),
        goal_checker=FakeGoal([True]),
        legacy_memory_sink=legacy_sink,
        multimodal_memory_sink=multimodal_sink,
        acquisition_store=acquisition_store,
    )


def test_acquisition_records_only_successful_episodes(tmp_path):
    from dc3pa.integration.controller import ExecutionResult

    store = AcquisitionStore(tmp_path / "acquisition")
    failed = _runner(
        Stage6RuntimeConfig(
            mode="reasoning_only",
            telemetry_enabled=True,
            acquisition_log_dir=str(tmp_path / "acquisition"),
        ),
        controller=FakeController(
            [
                ExecutionResult(
                    success=False,
                    underground=False,
                    raw={"success": False},
                    telemetry=_successful_telemetry(),
                )
            ]
        ),
        acquisition_store=store,
    )
    assert failed.run_task({"task": "log", "quantity": 1}).success is False
    assert store.count() == 0

    succeeded = _runner(
        Stage6RuntimeConfig(
            mode="reasoning_only",
            telemetry_enabled=True,
            acquisition_log_dir=str(tmp_path / "acquisition"),
        ),
        controller=FakeController(
            [
                ExecutionResult(
                    success=True,
                    underground=False,
                    raw={"success": True},
                    telemetry=_successful_telemetry(),
                )
            ]
        ),
        acquisition_store=store,
    )
    assert succeeded.run_task({"task": "log", "quantity": 1}).success is True
    assert store.count() == 1


def test_evaluate_readonly_runtime_does_not_call_record_success(tmp_path):
    db = tmp_path / "memory.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE exemplars(id INTEGER PRIMARY KEY)")
    manifest = create_snapshot_manifest(db, source_commit="test")
    manifest_path = tmp_path / "manifest.json"
    manifest.to_json(manifest_path)
    legacy_sink = FakeLegacyMemorySink()
    multimodal_sink = FakeMultimodalMemorySink()
    runner = _runner(
        Stage6RuntimeConfig(
            mode="reasoning_only",
            memory_mode="evaluate_readonly",
            record_legacy_workflow_memory=False,
            record_multimodal_memory=False,
            memory_snapshot_manifest=str(manifest_path),
        ),
        controller=FakeController([True]),
        legacy_sink=legacy_sink,
        multimodal_sink=multimodal_sink,
    )

    result = runner.run_task({"task": "log", "quantity": 1})

    assert result.success is True
    assert legacy_sink.calls == []
    assert multimodal_sink.episodes == []


def test_acquire_runtime_preserves_legacy_and_multimodal_recording():
    legacy_sink = FakeLegacyMemorySink()
    multimodal_sink = FakeMultimodalMemorySink()
    runner = _runner(
        Stage6RuntimeConfig(mode="reasoning_only"),
        controller=FakeController([True]),
        legacy_sink=legacy_sink,
        multimodal_sink=multimodal_sink,
    )

    result = runner.run_task({"task": "log", "quantity": 1})

    assert result.success is True
    assert len(legacy_sink.calls) == 1
    assert len(multimodal_sink.episodes) == 1
