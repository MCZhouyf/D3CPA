from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from dc3pa.reliability.fusion_dataset import FusionExample
from dc3pa.reliability.fusion_dataset import save_jsonl
from dc3pa.reliability.fusion_training import TrainerConfig, fit_monotonic_logistic


def _example(index, split, label, value, legacy):
    return FusionExample(
        episode_id=f"{split}-{index}",
        task=f"task-{index}",
        seed=str(index),
        plan_id=f"plan-{index}",
        plan_version=1,
        step_id=f"step-{index}",
        step_index=0,
        group_id=f"{split}-{index}",
        split=split,
        label=label,
        features={
            "knowledge": value,
            "model": value,
            "environment": value,
            "environment_coverage": value,
        },
        legacy_probability=legacy,
    )


def test_trainer_is_deterministic_and_nonnegative():
    training = [
        _example(i, "train", int(i >= 10), i / 19, 0.5) for i in range(20)
    ]
    validation = [
        _example(i, "validation", int(i >= 5), i / 9, 0.5) for i in range(10)
    ]
    config = TrainerConfig(max_epochs=2000, patience=100)
    first = fit_monotonic_logistic(training, validation, config=config)
    second = fit_monotonic_logistic(training, validation, config=config)
    assert first.intercept == second.intercept
    assert first.coefficients == second.coefficients
    assert all(value >= 0 for value in first.coefficients.values())
    assert first.validation_metrics["brier"] < 0.25
    assert first.equal_weight_validation_metrics["count"] == 10


def test_fit_cli_is_deterministic(tmp_path):
    examples = [
        *[_example(i, "train", int(i >= 10), i / 19, 0.5) for i in range(20)],
        *[_example(i, "validation", int(i >= 5), i / 9, 0.5) for i in range(10)],
        _example(99, "test", 1, 1.0, 0.5),
    ]
    dataset = tmp_path / "dataset.jsonl"
    save_jsonl(dataset, examples)
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts_dc3pa" / "fit_monotonic_fusion.py"
    artifact_ids = []
    for index in (1, 2):
        report = tmp_path / f"report-{index}.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--dataset",
                str(dataset),
                "--output-artifact",
                str(tmp_path / f"artifact-{index}.json"),
                "--output-report",
                str(report),
                "--memory-snapshot-sha256",
                "memory",
                "--confidence-artifact-id",
                "confidence",
                "--created-from-commit",
                "commit",
                "--max-epochs",
                "2000",
                "--patience",
                "100",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["equal_weight_validation_metrics"]["count"] == 10
        artifact_ids.append(payload["artifact_id"])
    assert artifact_ids[0] == artifact_ids[1]
