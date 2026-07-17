from dc3pa.experiments.ordinal_confidence_calibration import (
    fit_confidence_calibration,
    weighted_pav,
)
from tests_dc3pa.round511_test_utils import make_record


def test_weighted_pav_is_monotonic():
    result = weighted_pav((0.8, 0.2, 0.7), (1.0, 1.0, 1.0))
    assert list(result) == sorted(result)


def test_five_level_confidence_release_uses_train_and_tune_only():
    levels = ("very_low", "low", "medium", "high", "very_high")
    outcomes = (True, False, True, False, True)
    train = [
        make_record(
            f"train-{level}",
            role="dev_train",
            confidence_level=level,
            correct=outcome,
        )
        for level, outcome in zip(levels, outcomes)
    ]
    tune = [
        make_record(
            "tune-low",
            role="dev_tune",
            confidence_level="low",
            correct=False,
        ),
        make_record(
            "tune-high",
            role="dev_tune",
            confidence_level="high",
            correct=True,
        ),
    ]
    release = fit_confidence_calibration(
        release_name="confidence-v1",
        source_commit="a" * 40,
        development_input_release_id="dev-input",
        collection_audit_id="audit",
        paper_memory_v5_release_id="memory-v5",
        active_taskset_release_id="taskset",
        train_records=train,
        tune_records=tune,
    )
    probabilities = [item.calibrated_probability for item in release.levels]
    assert probabilities == sorted(probabilities)
    assert not release.holdout_used
    assert release.tune_metrics.record_count == 2
