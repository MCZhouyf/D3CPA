from dc3pa.baseline.metrics import parse_legacy_metrics


def test_parse_legacy_metrics_derives_replanning_count():
    metrics = parse_legacy_metrics(
        [
            "noise",
            "Planner did not return a valid workflow. Retrying the task loop.",
            "Task diamond | Iteration 1 | Successful True | Episode length 4 | Success rate 1.0",
        ],
        wall_clock_seconds=12.5,
        return_code=0,
    )
    assert metrics.success_rate == 1.0
    assert metrics.average_replanning_count == 3.0
    assert metrics.episodes[0].planning_rounds == 4

    assert metrics.episodes[0].invalid_plan_retries == 1
