from __future__ import annotations

from tests_dc3pa.round58_helpers import design


def test_reference_policy_and_environment_grid_are_frozen():
    item = design()
    policy = item.activation_policy
    assert policy.noninferiority_margins == {
        "brier": 0.01,
        "nll": 0.02,
        "ece": 0.02,
    }
    assert policy.minimum_effects["brier"] == 0.005
    assert policy.minimum_effects["nll"] == 0.01
    assert policy.bootstrap_replicates == 2000

    grid = item.environment_search_space
    assert grid.top_k_values == (1, 3, 5)
    assert grid.text_threshold_values == (0.4, 0.5, 0.6)
    assert grid.match_threshold_values == (0.35, 0.5, 0.65)
