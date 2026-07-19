from dc3pa.integration.round592_semantics import (
    _inventory_item_for_target,
    _spawned_block_for,
)


def test_semantic_fixture_uses_runtime_inventory_names():
    assert _inventory_item_for_target("wooden door") == "wooden_door"
    assert _inventory_item_for_target("diamond axe") == "diamond_axe"
    assert _inventory_item_for_target("coal ore") == "coal"


def test_semantic_fixture_records_harvest_spawn_blocks():
    assert _spawned_block_for("coal") == "coal_ore"
    assert _spawned_block_for("iron_ingot") == "iron_ore"
    assert _spawned_block_for("fence") == "not_applicable"
