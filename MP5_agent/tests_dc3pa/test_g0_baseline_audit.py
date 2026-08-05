from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
ASSET_ROOT = Path("/external/dc3pa/task_assets_schema")


def test_g0_log_callback_matches_success_finish(tmp_path: Path) -> None:
    manifest = tmp_path / "callback.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "g0_verify_log_callback_unchanged.py"),
            "--repo",
            str(ROOT),
            "--baseline",
            "success-finish",
            "--manifest",
            str(manifest),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(result.stdout)["unchanged"] is True
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["baseline_commit"] == "06a708e2dcfc6bb83d48e41b1475cf0581db15d5"
    assert payload["unchanged"] is True


def test_g0_taskset_is_the_frozen_50_task_catalog(tmp_path: Path) -> None:
    output = tmp_path / "taskset.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "g0_verify_taskset.py"),
            "--catalog",
            str(ASSET_ROOT / "final_task_catalog.csv"),
            "--spec-dir",
            str(ASSET_ROOT / "formal_task_specs"),
            "--creative-dir",
            str(ASSET_ROOT / "creative_task_jsons"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["task_count"] == 50
    assert payload["invalid_terminal_types"] == []
    assert payload["duplicate_task_ids"] == []
    assert payload["type_counts"] == {"craft": 37, "mine": 11, "smelt": 2}
