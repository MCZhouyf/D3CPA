from __future__ import annotations

from tests_dc3pa.round58_helpers import design


def test_all_stage_seeds_are_unique_and_final_has_1500_pairs():
    item = design()
    final = [
        int(seed)
        for task in item.final_test_exclusion.tasks
        for seed in task.test_seeds
    ]
    acquisition = [int(row.seed) for row in item.acquisition_assignments]
    development = [int(row.seed) for row in item.development_assignments]

    assert len(final) == 1500
    assert len(set(final)) == 1500
    all_seeds = final + acquisition + development
    assert len(all_seeds) == len(set(all_seeds))
    assert all(1 <= seed <= 2_147_483_646 for seed in all_seeds)
