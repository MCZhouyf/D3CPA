from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dc3pa.experiments.launcher_validation import validate_real_experiment_launch
from dc3pa.experiments.phase_state import ExperimentPhaseState
from tests_dc3pa.round56_helpers import make_blueprint


def test_dry_run_launch_is_dev_train_only_and_budgeted():
    blueprint = make_blueprint()
    state = ExperimentPhaseState(
        experiment_id=blueprint.blueprint_id,
        records=(),
    ).advance(
        phase="blueprint_frozen",
        source_commit="commit",
        artifact_ids={"blueprint_id": blueprint.blueprint_id},
    )

    result = validate_real_experiment_launch(
        blueprint=blueprint,
        phase_state=state,
        phase="dry_run_completed",
        task="basic-task-0",
        seed="dev-train",
        max_execution_attempts=4,
        run_manifest_ids={"stage6": "manifest-id"},
    )
    assert result.budget_phase == "dry_run"
    assert result.to_trace_payload()["run_manifest_ids"]["stage6"] == "manifest-id"

    with pytest.raises(ValueError, match="dev_train"):
        validate_real_experiment_launch(
            blueprint=blueprint,
            phase="dry_run_completed",
            task="dev-novel-a",
            seed="dev-tune",
        )
    with pytest.raises(ValueError, match="replan budget"):
        validate_real_experiment_launch(
            blueprint=blueprint,
            phase="dry_run_completed",
            task="basic-task-0",
            seed="dev-train",
            max_execution_attempts=5,
        )


def test_launch_validator_rejects_phase_skips():
    blueprint = make_blueprint()
    state = ExperimentPhaseState(experiment_id=blueprint.blueprint_id, records=())
    with pytest.raises(ValueError, match="next permitted phase"):
        validate_real_experiment_launch(
            blueprint=blueprint,
            phase_state=state,
            phase="dry_run_completed",
            task="basic-task-0",
            seed="dev-train",
        )


def test_validate_launch_cli_emits_trace_payload(tmp_path):
    root = Path(__file__).resolve().parents[1]
    blueprint = make_blueprint()
    blueprint_path = tmp_path / "blueprint.json"
    blueprint_path.write_text(
        json.dumps(blueprint.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "scripts_dc3pa/validate_real_experiment_launch.py",
            "--blueprint",
            str(blueprint_path),
            "--phase",
            "dry_run_completed",
            "--task",
            "basic-task-0",
            "--seed",
            "dev-train",
            "--run-manifest-id",
            "stage6=manifest-id",
        ],
        check=True,
        cwd=root,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["blueprint_id"] == blueprint.blueprint_id
    assert payload["run_manifest_ids"]["stage6"] == "manifest-id"
