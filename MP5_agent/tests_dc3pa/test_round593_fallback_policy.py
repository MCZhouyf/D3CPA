import pytest

from dc3pa.experiments.log_fallback import (
    DiagnosticLogFallbackSession,
    LogFallbackPolicy,
)


def test_policy_allows_only_explicit_diagnostic_dry_run():
    policy = LogFallbackPolicy().with_id()
    policy.assert_activation_allowed(
        scope="diagnostic_dry_run",
        explicit_cli_enable=True,
        dry_run_campaign_present=True,
        dry_run_output_marker_present=True,
    )
    with pytest.raises(ValueError):
        policy.assert_activation_allowed(
            scope="formal_acquisition",
            explicit_cli_enable=True,
            dry_run_campaign_present=True,
            dry_run_output_marker_present=True,
        )
    with pytest.raises(ValueError):
        policy.assert_activation_allowed(
            scope="diagnostic_dry_run",
            explicit_cli_enable=False,
            dry_run_campaign_present=True,
            dry_run_output_marker_present=True,
        )


def _session():
    return DiagnosticLogFallbackSession(
        policy=LogFallbackPolicy().with_id(),
        source_commit="commit",
        task="craft fence",
        seed="17",
    )


def test_session_injects_only_log_shortfall_and_preserves_other_items():
    requested = []

    def apply_inventory(inventory):
        requested.append(dict(inventory))
        return inventory

    event = _session().intervene(
        target_item="log",
        target_quantity=4,
        inventory_before={"log": 1, "stick": 2, "stone pickaxe": 1},
        naturally_collected_count=1,
        natural_collection_attempts=3,
        bounded_attempts_exhausted=True,
        apply_inventory=apply_inventory,
    )

    assert requested == [{"log": 4, "stick": 2, "stone pickaxe": 1}]
    assert event.injected_count == 3
    assert event.inventory_after == 4


def test_session_fails_when_unrelated_inventory_preservation_is_not_proven():
    with pytest.raises(RuntimeError, match="preservation"):
        _session().intervene(
            target_item="log",
            target_quantity=4,
            inventory_before={"log": 1, "stick": 2},
            naturally_collected_count=1,
            natural_collection_attempts=3,
            bounded_attempts_exhausted=True,
            apply_inventory=lambda inventory: {"log": inventory["log"]},
        )


def test_session_rejects_non_log_and_unexhausted_attempts():
    for changes in (
        {"target_item": "cobblestone"},
        {"bounded_attempts_exhausted": False},
        {"natural_collection_attempts": 2},
    ):
        values = {
            "target_item": "log",
            "target_quantity": 4,
            "inventory_before": {},
            "naturally_collected_count": 0,
            "natural_collection_attempts": 3,
            "bounded_attempts_exhausted": True,
            "apply_inventory": lambda inventory: inventory,
        }
        values.update(changes)
        with pytest.raises(ValueError):
            _session().intervene(**values)
