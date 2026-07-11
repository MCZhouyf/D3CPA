from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_stage6_demo_runs_by_file_path_and_emits_json():
    result = subprocess.run(
        [sys.executable, "scripts_dc3pa/stage6_closed_loop_demo.py"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["reactive_replan_count"] == 1
    assert payload["pre_execution_revision_count"] == 2
    assert payload["recorded_episode_count"] == 1
    assert payload["demo_only"] is True


def test_minecraft_entrypoint_help_has_no_minedojo_import_requirement():
    result = subprocess.run(
        [sys.executable, "scripts_dc3pa/stage6_run_minecraft.py", "--help"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert "Stage-6 DC3PA closed loop" in result.stdout
    assert "--require-environment-score" in result.stdout
