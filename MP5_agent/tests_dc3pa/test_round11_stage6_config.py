import json
from pathlib import Path

import pytest

from dc3pa.errors import ContractValidationError
from dc3pa.integration.stage6_config import Stage6RuntimeConfig


def test_paper_acquisition_disables_old_memory_write_paths():
    config_path = (
        Path(__file__).resolve().parents[1]
        / "dc3pa"
        / "configs"
        / "round11_paper_acquire.runtime.json"
    )
    config = Stage6RuntimeConfig.from_json_file(config_path)
    assert config.memory_mode == "acquire"
    assert config.acquisition_log_dir
    assert config.calibration_log_dir
    assert config.record_legacy_workflow_memory is False
    assert config.record_multimodal_memory is False


def test_calibration_log_is_not_allowed_in_readonly_evaluation():
    with pytest.raises(ContractValidationError):
        Stage6RuntimeConfig(
            memory_mode="evaluate_readonly",
            record_legacy_workflow_memory=False,
            record_multimodal_memory=False,
            memory_snapshot_manifest="manifest.json",
            calibration_log_dir="calibration",
        ).validate()
