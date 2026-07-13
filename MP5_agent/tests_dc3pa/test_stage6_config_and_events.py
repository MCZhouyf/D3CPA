from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from dc3pa.errors import ContractValidationError
from dc3pa.integration import (
    InventorySnapshot,
    RuntimeEvent,
    Stage6RuntimeConfig,
    sanitize_for_trace,
)
from dc3pa.reliability import DualChainConfig


def test_stage6_config_strict_validation(tmp_path):
    config = Stage6RuntimeConfig.from_mapping(
        {"mode": "dc3pa", "max_execution_attempts": 2}
    )
    assert config.max_execution_attempts == 2
    with pytest.raises(ContractValidationError):
        Stage6RuntimeConfig.from_mapping({"max_execution_attempts": True})
    with pytest.raises(ContractValidationError):
        Stage6RuntimeConfig.from_mapping({"mode": "unknown"})
    with pytest.raises(ContractValidationError):
        Stage6RuntimeConfig.from_mapping({"unexpected": 1})
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"runtime": {"mode": "reasoning_only"}}))
    assert Stage6RuntimeConfig.from_json_file(path).mode == "reasoning_only"


def test_stage6_closed_loop_config_allows_material_repair_rounds():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "dc3pa" / "configs" / "stage6_closed_loop.json").read_text(
            encoding="utf-8"
        )
    )
    config = DualChainConfig.from_mapping(payload["dual_chain"])
    assert config.max_revision_rounds >= 4


def test_inventory_rejects_bool_nan_and_negative():
    assert InventorySnapshot.from_mapping({"oak_log": 2}).to_dict() == {
        "oak log": 2.0
    }
    for value in (True, float("nan"), float("inf"), -1):
        with pytest.raises(ContractValidationError):
            InventorySnapshot.from_mapping({"log": value})


def test_trace_sanitizer_redacts_secrets_and_describes_arrays():
    array = np.zeros((4, 5, 3), dtype=np.uint8)
    result = sanitize_for_trace(
        {
            "api_key": "do-not-log",
            "nested": {"access_token": "do-not-log-either"},
            "image": array,
            "ordinary": "ok",
        }
    )
    assert result["api_key"] == "<redacted>"
    assert result["nested"]["access_token"] == "<redacted>"
    assert result["image"]["shape"] == [4, 5, 3]
    assert result["ordinary"] == "ok"
    serialized = json.dumps(RuntimeEvent("test", 0, result).to_dict())
    assert "do-not-log" not in serialized


def test_trace_sanitizer_redacts_secret_like_values_not_only_keys():
    payload = sanitize_for_trace(
        {
            "error": (
                "provider failed with " + "Bearer " + "abcdefghijklmnop"
                + " and " + "s" + "k-" + "abcdefghijklmnop"
            ),
            "message": "api_key=super-secret-value",
        }
    )
    text = json.dumps(payload)
    assert "abcdefghijklmnop" not in text
    assert "super-secret-value" not in text
