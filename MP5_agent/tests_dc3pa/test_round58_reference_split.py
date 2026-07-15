from __future__ import annotations

from collections import defaultdict

from tests_dc3pa.round58_helpers import design


def test_split_is_deterministic_balanced_and_horizon_paired():
    first = design()
    second = design()
    assert first.design_id == second.design_id

    grouped = defaultdict(list)
    for item in first.final_test_exclusion.tasks:
        grouped[item.difficulty].append(item)
    for difficulty, items in grouped.items():
        assert len(items) == 10
        assert sum(item.goal_status == "experience_covered" for item in items) == 5
        assert sum(
            item.goal_status == "final_heldout_terminal_goal" for item in items
        ) == 5
