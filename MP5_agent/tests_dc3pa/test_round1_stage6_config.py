import pytest

from dc3pa.errors import ContractValidationError
from dc3pa.integration.stage6_config import Stage6RuntimeConfig


def test_round1_defaults_preserve_legacy_acquire_behavior():
    config = Stage6RuntimeConfig()
    config.validate()
    assert config.memory_mode == "acquire"
    assert config.record_legacy_workflow_memory is True
    assert config.record_multimodal_memory is True
    assert config.telemetry_enabled is False


def test_readonly_mode_requires_no_recording_and_manifest():
    with pytest.raises(ContractValidationError):
        Stage6RuntimeConfig(
            memory_mode="evaluate_readonly",
            memory_snapshot_manifest="snapshot.json",
        ).validate()

    config = Stage6RuntimeConfig(
        memory_mode="evaluate_readonly",
        record_legacy_workflow_memory=False,
        record_multimodal_memory=False,
        memory_snapshot_manifest="snapshot.json",
    )
    config.validate()
