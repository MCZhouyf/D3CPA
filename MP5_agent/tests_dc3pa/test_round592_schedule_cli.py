import json
import subprocess
import sys
from pathlib import Path


def test_schedule_cli_preserves_author_approved_salt(tmp_path):
    methods = tmp_path / "methods.json"
    units = tmp_path / "units.json"
    output = tmp_path / "schedule.json"
    methods.write_text(json.dumps({"methods": [{
        "method_id": "single-chain",
        "display_name": "Single chain",
        "provider_profile_id": "profile",
        "controller_profile": "controller",
        "memory_policy": "disabled",
        "cognitive_control_mode": "reasoning_only",
        "implementation_commit": "commit",
        "ready": True,
        "readiness_artifact_id": "approval",
    }]}))
    units.write_text(json.dumps({"units": [{
        "task": "mine log",
        "seed": "1",
        "difficulty": "basic",
        "block_id": "block-1",
    }]}))
    script = Path(__file__).parents[1] / "scripts_dc3pa" / (
        "build_interleaved_execution_schedule.py"
    )
    result = subprocess.run([
        sys.executable, str(script),
        "--methods", str(methods),
        "--units", str(units),
        "--schedule-name", "round592",
        "--blueprint-id", "blueprint",
        "--source-commit", "commit",
        "--model-profile-id", "profile",
        "--schedule-salt", "author-approved-salt",
        "--output", str(output),
    ], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text())["schedule_salt"] == (
        "author-approved-salt"
    )
