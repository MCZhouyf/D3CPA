from __future__ import annotations

import pytest

from dc3pa.reliability.activation_policy import ActivationPolicy


def _policy(**updates):
    payload = dict(
        policy_name="pre-registered-policy",
        noninferiority_margins={"brier": 0.01, "nll": 0.02, "ece": 0.02},
        primary_metrics=("brier", "nll"),
        calibration_metrics=("ece",),
        minimum_primary_improvements=1,
        minimum_effects={"brier": 0.0, "nll": 0.0, "ece": 0.0},
        bootstrap_replicates=200,
    )
    payload.update(updates)
    return ActivationPolicy(**payload)


def test_policy_id_is_deterministic():
    assert _policy().with_id().policy_id == _policy().with_id().policy_id


def test_missing_margin_is_rejected():
    with pytest.raises(ValueError):
        _policy(noninferiority_margins={"brier": 0.01, "nll": 0.02})
