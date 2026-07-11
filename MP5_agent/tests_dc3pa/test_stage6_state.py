from __future__ import annotations

import numpy as np

from dc3pa.integration.state import (
    LegacyMP5StateProvider,
    extract_rgb_observation,
)


def test_extract_rgb_supports_hwc_chw_and_float_ranges():
    hwc = np.zeros((5, 6, 3), dtype=np.uint8)
    assert extract_rgb_observation({"rgb": hwc}).shape == (5, 6, 3)
    chw = np.zeros((3, 5, 6), dtype=np.uint8)
    assert extract_rgb_observation({"obs": {"pov": chw}}).shape == (5, 6, 3)
    floating = np.ones((2, 3, 3), dtype=np.float32)
    assert extract_rgb_observation(floating).max() == 255
    assert extract_rgb_observation(np.zeros((5, 5))) is None
    assert extract_rgb_observation(np.array([[[float("nan")] * 3]])) is None


def test_legacy_state_provider_builds_detached_scene_and_context():
    image = np.zeros((3, 4, 5), dtype=np.uint8)
    provider = LegacyMP5StateProvider(
        refresh_observation=lambda: {
            "rgb": image,
            "life_stats": {"life": 18},
        },
        inventory_provider=lambda: {"oak_log": 2},
    )
    snapshot = provider.snapshot({"task": "log", "quantity": 1}, False)
    assert snapshot.state.task == "log"
    assert snapshot.state.inventory == {"oak log": 2.0}
    assert snapshot.state.health == 18.0
    assert snapshot.reliability_context.image.shape == (4, 5, 3)
    image[:] = 255
    assert snapshot.reliability_context.image.max() == 0
    assert snapshot.scene is not None
    assert "inventory=oak log=2" in snapshot.scene.description
