from __future__ import annotations

import pytest


@pytest.mark.minedojo
def test_real_registry_exposes_canonical_ids_and_known_unsupported_targets():
    from dc3pa.integration.round591_tasks import export_runtime_item_registry

    entries = export_runtime_item_registry()
    by_name = {item["name"]: item for item in entries}

    assert by_name["bucket"]["id"] == "minecraft:bucket"
    assert by_name["wooden button"]["id"] == "minecraft:wooden_button"
    assert "carpentry table" not in by_name
    assert "raw gold block" not in by_name
