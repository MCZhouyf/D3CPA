import pytest
import json

from dc3pa.experiments.log_fallback import (
    assert_readiness_receipts_are_natural,
)
from dc3pa.experiments.readiness import load_receipt


def receipt(enabled=False, triggered=False, injected=0):
    return {
        "entry_id": "entry",
        "fallback_metrics": {
            "fallback_enabled": enabled,
            "fallback_triggered": triggered,
            "total_injected_logs": injected,
        },
    }


def test_natural_readiness_receipts_pass():
    assert_readiness_receipts_are_natural([receipt()])


def test_any_fallback_evidence_is_rejected_for_readiness():
    with pytest.raises(ValueError):
        assert_readiness_receipts_are_natural(
            [receipt(enabled=True, triggered=True, injected=4)]
        )


def test_legacy_receipt_without_fallback_metrics_is_not_new_evidence(tmp_path):
    path = tmp_path / "legacy-receipt.json"
    path.write_text(json.dumps({"truth_receipt_id": "old"}), encoding="utf-8")

    with pytest.raises(ValueError, match="fallback metrics"):
        load_receipt(path)
