from dc3pa.memory.calibration_store import (
    CalibrationEpisodeRecord,
    CalibrationEpisodeStore,
)


def test_calibration_store_accepts_success_and_failure(tmp_path):
    store = CalibrationEpisodeStore(tmp_path / "calibration")
    for index, success in enumerate((True, False)):
        store.commit(
            CalibrationEpisodeRecord(
                episode_id=f"episode-{index}",
                task_name="obtain log",
                seed=str(index),
                success=success,
                plan={"task": "obtain log", "steps": []},
                telemetry=({"event_type": "step_finished", "status": "success" if success else "failure"},),
                failure_reason="" if success else "controller_reported_failure",
            )
        )
    assert store.count() == 2
    payloads = list(store.iter_payloads())
    assert [item["record"]["success"] for item in payloads] == [True, False]
