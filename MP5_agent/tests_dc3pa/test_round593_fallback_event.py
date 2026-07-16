import pytest

from dc3pa.experiments.log_fallback import LogFallbackEvent


def event(**changes):
    value = dict(
        fallback_kind="log_inventory_injection",
        scope="diagnostic_dry_run",
        policy_id="policy",
        inventory_before=1,
        inventory_target=4,
        inventory_after=4,
        naturally_collected_count=1,
        injected_count=3,
        natural_collection_attempts=3,
        bounded_attempts_exhausted=True,
        triggered=True,
        source_commit="commit",
        task="crafting table",
        seed="1",
    )
    value.update(changes)
    return LogFallbackEvent(**value)


def test_triggered_event_injects_exact_shortfall():
    assert event().with_id().event_id


def test_over_injection_and_unbounded_trigger_fail():
    with pytest.raises(ValueError):
        event(injected_count=4, inventory_after=5)
    with pytest.raises(ValueError):
        event(bounded_attempts_exhausted=False)
