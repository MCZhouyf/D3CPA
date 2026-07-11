import pytest

from dc3pa.reliability import AdaptiveTriggerConfig
from dc3pa.trigger import AdaptiveTriggerSession, FixedIntervalTriggerSession


def test_adaptive_trigger_expands_and_contracts_from_sliding_confidence():
    config = AdaptiveTriggerConfig(
        threshold=0.8,
        initial_interval=3,
        window_size=3,
        minimum_interval=1,
        maximum_interval=6,
    )
    session = AdaptiveTriggerSession(total_steps=10, config=config)
    first = session.next_window()
    assert first.step_indices == (0, 1, 2)
    observed = session.observe([0.9, 0.9, 0.9])
    assert observed.next_interval == 4

    second = session.next_window()
    assert second.step_indices == (3, 4, 5, 6)
    low = session.observe([0.4, 0.4, 0.4, 0.4])
    assert low.monitored_confidence == pytest.approx(0.4)
    assert low.next_interval == 3

    third = session.next_window()
    assert third.step_indices == (7, 8, 9)
    hard = session.observe([0.95, 0.95, 0.95], hard_conflict=True)
    assert hard.next_interval == 1
    assert session.finished


def test_unavailable_probability_is_treated_as_uncertainty():
    session = AdaptiveTriggerSession(
        total_steps=3,
        config=AdaptiveTriggerConfig(initial_interval=3),
    )
    session.next_window()
    observation = session.observe([0.9, None, 0.9])
    assert observation.had_unavailable
    assert observation.low_confidence
    assert observation.next_interval == 2


def test_revision_restart_forces_immediate_single_step_validation():
    session = AdaptiveTriggerSession(
        total_steps=8,
        config=AdaptiveTriggerConfig(initial_interval=3),
    )
    session.next_window()
    session.observe([0.9, 0.9, 0.9])
    session.restart_after_revision(start_index=1, total_steps=9)
    forced = session.next_window()
    assert forced.forced
    assert forced.step_indices == (1,)
    assert forced.reason == "post_revision_validation"


def test_fixed_interval_session_covers_final_partial_window():
    session = FixedIntervalTriggerSession(total_steps=5, interval=3)
    assert session.next_window().step_indices == (0, 1, 2)
    session.observe([0.9, 0.9, 0.9])
    assert session.next_window().step_indices == (3, 4)
    session.observe([0.9, 0.9])
    assert session.next_window() is None


def test_revision_clears_confidence_from_stale_plan_version():
    session = AdaptiveTriggerSession(
        total_steps=6,
        config=AdaptiveTriggerConfig(initial_interval=3, window_size=3),
    )
    session.next_window()
    session.observe([0.1, 0.1, 0.1])
    session.restart_after_revision(start_index=0, total_steps=6)
    forced = session.next_window()
    assert forced.step_indices == (0,)
    observation = session.observe([0.95])
    assert observation.monitored_confidence == pytest.approx(0.95)


def test_trigger_rejects_boolean_and_nonfinite_probabilities():
    session = AdaptiveTriggerSession(
        total_steps=1,
        config=AdaptiveTriggerConfig(initial_interval=1),
    )
    session.next_window()
    with pytest.raises(ValueError):
        session.observe([True])

    session = FixedIntervalTriggerSession(total_steps=1, interval=1)
    session.next_window()
    with pytest.raises(ValueError):
        session.observe([float("nan")])
