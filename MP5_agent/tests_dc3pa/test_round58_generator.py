from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reference_generator_records_frozen_salts_and_round57_csv_shapes(tmp_path):
    catalog = tmp_path / "catalog.csv"
    with catalog.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=("task", "difficulty", "minimum_subgoals")
        )
        writer.writeheader()
        for difficulty in ("basic", "easy", "medium", "hard", "complex"):
            for index in range(10):
                writer.writerow(
                    {
                        "task": f"synthetic-{difficulty}-{index}",
                        "difficulty": difficulty,
                        "minimum_subgoals": index + 1,
                    }
                )
    output = tmp_path / "generated"

    subprocess.run(
        [
            sys.executable,
            "scripts_dc3pa/generate_gpt51_reference_design.py",
            "--task-catalog",
            str(catalog),
            "--source-commit",
            "test-commit",
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    report = (output / "reference_design_report.md").read_text(encoding="utf-8")
    for label in (
        "Split salt",
        "Final-seed salt",
        "Acquisition-seed salt",
        "Development-seed salt",
        "Development-role salt",
    ):
        assert label in report
    expected_headers = {
        "final_tasks.csv": {"task", "difficulty", "goal_status"},
        "final_seeds.csv": {"task", "seed", "seed_index"},
        "acquisition.csv": {
            "group_id", "task", "seed", "task_kind", "difficulty",
            "sequence_index",
        },
        "development.csv": {
            "group_id", "task", "seed", "role", "difficulty", "goal_status",
        },
    }
    for name, headers in expected_headers.items():
        with (output / name).open("r", encoding="utf-8", newline="") as handle:
            assert set(csv.DictReader(handle).fieldnames or ()) == headers
