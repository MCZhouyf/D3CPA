from __future__ import annotations

import pytest

from dc3pa.experiments.blueprint import AcquisitionAssignment
from dc3pa.reliability.development_protocol import GroupAssignment
from tests_dc3pa.round56_helpers import final_manifest, make_blueprint


def test_final_heldout_goal_is_rejected_from_acquisition():
    with pytest.raises(ValueError):
        make_blueprint(
            acquisition=(
                AcquisitionAssignment(
                    "bad",
                    "basic-task-1",
                    "acq-seed",
                    "experience_covered_final_goal",
                    sequence_index=0,
                ),
            )
        )


def test_acquisition_and_development_task_seed_may_not_overlap():
    acquisition = (
        AcquisitionAssignment(
            "acq",
            "basic-task-0",
            "same-seed",
            "experience_covered_final_goal",
            sequence_index=0,
        ),
    )
    development = (
        GroupAssignment(
            "train", "basic-task-0", "same-seed", "dev_train",
            "basic", "experience_covered"
        ),
        GroupAssignment(
            "tune", "dev-a", "tune-seed", "dev_tune",
            "medium", "development_novel_goal"
        ),
        GroupAssignment(
            "holdout", "dev-b", "holdout-seed", "dev_holdout",
            "hard", "development_novel_goal"
        ),
    )
    with pytest.raises(ValueError):
        make_blueprint(acquisition=acquisition, development=development)
