from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dc3pa.reliability import OrdinalCalibrationArtifact, ordinal_prompt_template_sha256


def _valid_artifact_payload(**overrides):
    payload = {
        "schema_version": 1,
        "artifact_id": "a",
        "model_id": "gpt-test",
        "prompt_version": "ordinal-v1",
        "prompt_sha256": ordinal_prompt_template_sha256(),
        "dataset_sha256": "d",
        "created_from_commit": "c",
        "base_mapping": {
            "very_unlikely": 0.1,
            "unlikely": 0.3,
            "uncertain": 0.5,
            "likely": 0.7,
            "very_likely": 0.9,
        },
        "calibrated_mapping": {
            "very_unlikely": 0.2,
            "unlikely": 0.3,
            "uncertain": 0.5,
            "likely": 0.8,
            "very_likely": 0.95,
        },
        "sample_counts": {
            level: {"total": 1, "positive": 1, "negative": 0}
            for level in (
                "very_unlikely",
                "unlikely",
                "uncertain",
                "likely",
                "very_likely",
            )
        },
        "metrics": {"base_brier": 0.1},
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 999},
        _valid_artifact_payload(calibrated_mapping={"likely": 0.7}),
        _valid_artifact_payload(
            calibrated_mapping={
                "very_unlikely": 0.9,
                "unlikely": 0.3,
                "uncertain": 0.5,
                "likely": 0.7,
                "very_likely": 0.95,
            }
        ),
    ],
)
def test_artifact_loader_fails_closed_on_corrupt_or_incomplete_payload(tmp_path, payload):
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        OrdinalCalibrationArtifact.load(path)


def _write_episode(root: Path, name: str, level: str, label: int):
    path = root / "episodes" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    status = "success" if label else "failure"
    payload = {
        "schema_version": 2,
        "record": {
            "episode_id": name,
            "task_name": "log",
            "seed": name,
            "success": bool(label),
            "plan": {"plan_id": "p", "version": 1, "steps": [{"step_id": name}]},
            "telemetry": [
                {
                    "event_type": "step_finished",
                    "plan_id": "p",
                    "plan_version": 1,
                    "step_id": name,
                    "step_index": 0,
                    "status": status,
                    "payload": {},
                }
            ],
            "confidence_observations": [
                {
                    "plan_id": "p",
                    "plan_version": 1,
                    "step_id": name,
                    "step_index": 0,
                    "request_hash": f"h-{name}",
                    "implementation": "ordinal_v2",
                    "confidence_level": level,
                    "base_probability": 0.7,
                    "decision_probability": 0.7,
                    "model_id": "gpt-test",
                    "prompt_version": "ordinal-v1",
                    "prompt_sha256": ordinal_prompt_template_sha256(),
                }
            ],
            "failure_reason": "" if label else "controller_reported_failure",
            "metadata": {},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_fit_ordinal_calibrator_cli_is_deterministic(tmp_path):
    root = tmp_path / "calibration"
    for index, (level, label) in enumerate(
        [
            ("very_unlikely", 0),
            ("unlikely", 0),
            ("uncertain", 1),
            ("likely", 1),
            ("very_likely", 1),
        ]
    ):
        _write_episode(root, f"e{index}", level, label)

    outputs = []
    for run in (1, 2):
        output = tmp_path / f"artifact-{run}.json"
        completed = subprocess.run(
            [
                sys.executable,
                "scripts_dc3pa/fit_ordinal_calibrator.py",
                "--calibration-root",
                str(root),
                "--output",
                str(output),
                "--model-id",
                "gpt-test",
                "--created-from-commit",
                "commit",
                "--min-total-samples",
                "1",
                "--min-observed-levels",
                "1",
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=True,
        )
        outputs.append(json.loads(completed.stdout)["artifact_id"])
    assert outputs[0] == outputs[1]
