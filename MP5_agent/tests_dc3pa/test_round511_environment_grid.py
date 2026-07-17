from dc3pa.experiments.environment_grid_compiler import compile_grid_from_anchor


def test_environment_grid_is_small_one_factor_at_a_time_and_outcome_free():
    grid = compile_grid_from_anchor(
        {
            "top_k": 3,
            "minimum_similarity": 0.4,
            "minimum_coverage": 0.5,
            "mismatch_compatibility_threshold": 0.3,
            "match_compatibility_threshold": 0.7,
        },
        anchor_config_id="anchor",
    )
    assert 1 <= len(grid.candidates) <= 9
    assert grid.one_factor_at_a_time
    assert not grid.outcome_data_used
    assert all(item.top_k == 3 for item in grid.candidates)
