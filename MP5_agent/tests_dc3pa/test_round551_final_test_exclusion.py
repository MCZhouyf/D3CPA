from __future__ import annotations

import pytest

from dc3pa.reliability.final_test_exclusion import (
    FinalEvaluationTask,
    FinalTestExclusionManifest,
)


def _manifest():
    return FinalTestExclusionManifest(
        manifest_name="final-50x30",
        tasks=(
            FinalEvaluationTask(
                task="obtain diamond",
                difficulty="complex",
                goal_status="final_heldout_terminal_goal",
                test_seeds=("1", "2"),
            ),
            FinalEvaluationTask(
                task="obtain log",
                difficulty="basic",
                goal_status="experience_covered",
                test_seeds=("1", "2"),
            ),
        ),
        created_from_commit="commit",
    ).with_id()


def test_final_heldout_goal_never_enters_development():
    with pytest.raises(ValueError):
        _manifest().validate_development_item(
            task="obtain diamond",
            seed="99",
            goal_status="development_novel_goal",
        )


def test_covered_goal_may_use_non_test_development_seed():
    _manifest().validate_development_item(
        task="obtain log",
        seed="dev-3",
        goal_status="experience_covered",
    )


def test_final_test_seed_is_rejected_even_for_covered_goal():
    with pytest.raises(ValueError):
        _manifest().validate_development_item(
            task="obtain log",
            seed="1",
            goal_status="experience_covered",
        )
