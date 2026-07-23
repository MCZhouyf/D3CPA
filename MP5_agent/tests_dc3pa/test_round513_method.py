from __future__ import annotations

import inspect

import pytest

from dc3pa.experiments import round513_method as method


def test_hard_constraints_bypass_fusion_and_are_excluded_from_soft_coverage():
    assert method.knowledge_features((False,), (True, True)) == (0, 1.0, 1)
    assert method.knowledge_features((True,), ()) == (1, 0.0, 0)
    assert method.chrmlite_probability(
        h=0, k=1.0, u=1, p_model=0.9, p_environment=0.9,
        base_rate=0.5, intercept=0.0, beta_k=1.0, beta_u=0.0,
        beta_model=1.0, beta_environment=1.0,
    ) is None


def test_coefficient_constraints_and_positive_evidence_monotonicity():
    contracts = method.build_method_contracts("source")
    provenance = contracts[3]
    assert provenance.coefficient_constraints["intercept"] == "unrestricted"
    assert provenance.coefficient_constraints["knowledge_available"] == "unrestricted"
    assert all(
        provenance.coefficient_constraints[name] == "nonnegative"
        for name in ("knowledge_coverage", "model_logit", "environment_logit")
    )
    base = dict(
        h=1, k=0.2, u=1, p_environment=0.7, base_rate=0.5,
        intercept=-1.0, beta_k=0.5, beta_u=-0.4, beta_model=1.0,
        beta_environment=1.0,
    )
    assert method.chrmlite_probability(p_model=0.8, **base) > method.chrmlite_probability(p_model=0.6, **base)
    with pytest.raises(ValueError, match="nonnegative"):
        method.chrmlite_probability(p_model=0.8, **{**base, "beta_model": -1.0})


def test_environment_is_bilateral_undercovered_unknown_and_tie_breaks_deterministically():
    assert method.environment_state(
        (("a", 0.9),), (("b", 0.8),), gamma_minus=-0.1, gamma_plus=0.1
    )[0] == "unknown"
    state = method.environment_state(
        (("z", 0.9), ("a", 0.9), ("b", 0.8), ("c", 0.1)),
        (("n3", 0.3), ("n1", 0.3), ("n2", 0.3)),
        gamma_minus=-0.1,
        gamma_plus=0.1,
    )
    assert state[0] == "matched"
    assert state[2] == ("a", "z", "b")
    assert state[3] == ("n1", "n2", "n3")


def test_weighted_pav_preserves_required_order():
    calibrated = method.weighted_pav((0.8, 0.2, 0.9), (2.0, 1.0, 1.0))
    assert calibrated[0] <= calibrated[1] <= calibrated[2]


def test_cdt_threshold_is_zero_when_expected_benefit_does_not_exceed_cost():
    assert method.cdt_threshold(
        rho_lcb=0.2, failure_loss=2.0, evaluation_cost=0.4,
        false_positive_cost=1.0, tau_max=0.95,
    ) == 0.0
    assert method.cdt_threshold(
        rho_lcb=0.5, failure_loss=4.0, evaluation_cost=0.5,
        false_positive_cost=1.0, tau_max=0.95,
    ) > 0.0


def test_cdt_has_no_redundant_max_condition_and_no_legacy_smoothing_state():
    source = inspect.getsource(method.cdt_should_trigger)
    assert "m_max" not in source.lower()
    assert method.cdt_should_trigger(h=1, p_pre=0.9, tau=0.5, delta=0.05, counter=4, interval=4)
    interval_fields = method.CHRMLiteParameterProvenancePolicyV4_1.__dataclass_fields__
    assert "exponential_moving_average" not in interval_fields
    assert "moving_average_state" not in interval_fields


def test_false_positive_cost_is_unconditional_over_evaluated_correct_steps():
    assert method.false_positive_cost(((False, 100.0), (True, 2.0))) == 1.0


def test_post_revision_recomputes_knowledge_and_environment_only_on_action_change():
    changed = method.post_revision_features(
        action_changed=True, old_h=1, old_k=0.1, old_u=1,
        old_environment_probability=0.2, recomputed=(0, 0.8, 1, 0.9),
        new_model_probability=0.7,
    )
    assert changed == (0, 0.8, 1, 0.7, 0.9)
    unchanged = method.post_revision_features(
        action_changed=False, old_h=1, old_k=0.1, old_u=1,
        old_environment_probability=0.2, recomputed=None,
        new_model_probability=0.7,
    )
    assert unchanged == (1, 0.1, 1, 0.7, 0.2)


def test_interval_updates_only_from_observed_evaluation_outcome():
    assert method.update_evaluation_interval(
        current=3, action_changed=True, revised_action_succeeded=True,
        p_post=0.1, tau=0.5, delta=0.05, m_min=1, m_max=4,
    ) == 2
    assert method.update_evaluation_interval(
        current=3, action_changed=False, revised_action_succeeded=False,
        p_post=0.8, tau=0.5, delta=0.05, m_min=1, m_max=4,
    ) == 4


def test_same_planner_schema_and_task_level_crossfit_bootstrap_are_frozen():
    method_contract, schema, _, _, statistical = method.build_method_contracts("source")
    assert schema.confidence_same_planner_generation_required
    assert schema.confidence_extra_online_call_forbidden
    assert statistical.cross_fit_group == "terminal_task"
    assert statistical.primary_bootstrap_group == "terminal_task"
    assert not statistical.decision_row_iid_bootstrap_permitted
    folds = method.deterministic_task_folds(("b", "a", "c", "d", "e"), 5)
    assert len(set(folds.values())) == 5
    assert not method_contract.model_fitting_permitted_in_round513a
