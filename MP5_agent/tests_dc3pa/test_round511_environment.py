from dc3pa.experiments.environment_parameter_selection import (
    EnvironmentCandidate,
    select_environment_evidence,
)
from tests_dc3pa.round511_test_utils import make_record


def test_environment_grid_is_selected_on_tune_without_holdout():
    candidates = [
        EnvironmentCandidate(
            top_k=3,
            minimum_similarity=0.5,
            minimum_coverage=0.5,
            mismatch_compatibility_threshold=0.3,
            match_compatibility_threshold=0.7,
        ).with_id(),
        EnvironmentCandidate(
            top_k=3,
            minimum_similarity=0.8,
            minimum_coverage=0.8,
            mismatch_compatibility_threshold=0.2,
            match_compatibility_threshold=0.8,
        ).with_id(),
    ]
    train = [
        make_record(
            "train-match",
            role="dev_train",
            correct=True,
            compatibility=0.9,
            coverage=0.9,
            similarity=0.95,
        ),
        make_record(
            "train-mismatch",
            role="dev_train",
            correct=False,
            compatibility=0.1,
            coverage=0.9,
            similarity=0.95,
            raw_state="mismatch",
        ),
        make_record(
            "train-unknown",
            role="dev_train",
            correct=False,
            compatibility=0.5,
            coverage=0.2,
            similarity=0.4,
            raw_state="unknown",
        ),
    ]
    tune = [
        make_record(
            "tune-match",
            role="dev_tune",
            correct=True,
            compatibility=0.9,
            coverage=0.9,
            similarity=0.95,
        ),
        make_record(
            "tune-mismatch",
            role="dev_tune",
            correct=False,
            compatibility=0.1,
            coverage=0.9,
            similarity=0.95,
            raw_state="mismatch",
        ),
    ]
    release = select_environment_evidence(
        release_name="environment-v1",
        source_commit="a" * 40,
        development_input_release_id="dev-input",
        collection_audit_id="audit",
        paper_memory_v5_release_id="memory-v5",
        active_taskset_release_id="taskset",
        candidates=candidates,
        train_records=train,
        tune_records=tune,
    )
    assert release.eligible
    assert not release.holdout_used
    assert release.selected_candidate_id
    probabilities = [
        release.selected_result.state_probabilities[state]
        for state in ("mismatch", "unknown", "matched")
    ]
    assert probabilities == sorted(probabilities)
