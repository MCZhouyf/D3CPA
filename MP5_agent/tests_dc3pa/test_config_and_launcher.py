from pathlib import Path

import pytest

from dc3pa.baseline.launcher import build_legacy_launch_spec
from dc3pa.config import DC3PAConfig, FeatureFlags
from dc3pa.errors import ContractValidationError


def _make_repo(root: Path) -> Path:
    agent = root / "MP5_agent" / "agent"
    agent.mkdir(parents=True)
    (agent / "run_agent.py").write_text("print('stub')\n", encoding="utf-8")
    task = agent / "tasks" / "log.json"
    task.parent.mkdir()
    task.write_text('{"task": "log"}\n', encoding="utf-8")
    return task


def test_feature_flags_require_real_json_booleans():
    with pytest.raises(ContractValidationError):
        FeatureFlags.from_mapping({"legacy_task_hacks": "false"})
    assert not FeatureFlags.from_mapping({"legacy_task_hacks": False}).legacy_task_hacks


def test_launcher_rejects_missing_task_file(tmp_path):
    _make_repo(tmp_path)
    config = DC3PAConfig(task_file="missing.json", model_name="stub-model")
    with pytest.raises(FileNotFoundError):
        build_legacy_launch_spec(tmp_path, config, seed=7, base_environment={})


def test_launcher_resolves_task_and_records_seed_without_secret(tmp_path):
    task = _make_repo(tmp_path)
    config = DC3PAConfig(
        task_file=str(task.relative_to(tmp_path)),
        model_name="stub-model",
        feature_flags=FeatureFlags(legacy_task_hacks=False),
    )
    spec = build_legacy_launch_spec(
        tmp_path,
        config,
        seed=7,
        base_environment={
            "OPENAI_API_KEY": "secret",
            "SERVICE_TOKEN": "token",
            "NORMAL_SETTING": "visible",
        },
    )
    assert spec.environment["TASK_FILE"] == str(task.resolve())
    assert spec.environment["DC3PA_WORLD_SEED"] == "7"
    assert spec.environment["DC3PA_SIM_SEED"] == "7"
    assert spec.environment["PYTHONHASHSEED"] == "7"
    assert spec.environment["DC3PA_LEGACY_TASK_HACKS"] == "0"
    redacted = spec.redacted().environment
    assert redacted["OPENAI_API_KEY"] == "<redacted>"
    assert redacted["SERVICE_TOKEN"] == "<redacted>"
    assert redacted["NORMAL_SETTING"] == "visible"


def test_manifest_uses_launch_environment_and_excludes_api_key(tmp_path):
    from dc3pa.observability.manifest import create_run_manifest

    task = _make_repo(tmp_path)
    config = DC3PAConfig(
        task_file=str(task.relative_to(tmp_path)), model_name="stub-model"
    )
    spec = build_legacy_launch_spec(
        tmp_path,
        config,
        seed=13,
        base_environment={"OPENAI_API_KEY": "secret"},
    )
    manifest = create_run_manifest(config, tmp_path, environment=spec.environment)
    assert manifest.selected_environment["GPT_MODEL_NAME"] == "stub-model"
    assert manifest.selected_environment["TASK_FILE"] == str(task.resolve())
    assert manifest.selected_environment["DC3PA_WORLD_SEED"] == "13"
    assert manifest.selected_environment["DC3PA_SIM_SEED"] == "13"
    assert manifest.selected_environment["PYTHONHASHSEED"] == "13"
    assert "OPENAI_API_KEY" not in manifest.selected_environment
