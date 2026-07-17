import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np

from dc3pa.memory.acquisition import (
    AcquisitionStore,
    LocalSceneCandidate,
    SuccessfulTrajectoryRecord,
)


def test_build_frozen_memory_cli_creates_readonly_snapshot(tmp_path):
    acquisition_root = tmp_path / "acquisition"
    store = AcquisitionStore(acquisition_root)
    episode_id = "episode-1"
    image_path = store.write_rgb_array(
        episode_id=episode_id,
        step_id="craft-pickaxe",
        action_index=0,
        rgb=np.zeros((8, 8, 3), dtype=np.uint8),
    )
    plan = {
        "task": "obtain wooden pickaxe",
        "plan_id": "plan-1",
        "version": 1,
        "steps": [
            {
                "step_id": "craft-pickaxe",
                "times": 1,
                "expected_outputs": {"wooden pickaxe": 1},
                "metadata": {"local_subgoal": "craft wooden pickaxe"},
                "actions": [
                    {
                        "name": "craft",
                        "args": {
                            "obj": {"wooden pickaxe": 1},
                            "materials": {"planks": 3, "stick": 2},
                            "platform": "crafting table",
                        },
                    }
                ],
            }
        ],
    }
    store.commit_success(
        SuccessfulTrajectoryRecord(
            episode_id=episode_id,
            task_name="obtain wooden pickaxe",
            seed="1",
            plan=plan,
            telemetry=(),
            scene_candidates=(
                LocalSceneCandidate(
                    episode_id=episode_id,
                    task_name="obtain wooden pickaxe",
                    plan_id="plan-1",
                    plan_version=1,
                    step_id="craft-pickaxe",
                    step_index=0,
                    action_index=0,
                    local_subgoal="craft wooden pickaxe",
                    action=plan["steps"][0]["actions"][0],
                    image_path=image_path,
                    pre_inventory={"planks": 3, "stick": 2, "crafting table": 1},
                ),
            ),
        )
    )

    root = Path(__file__).resolve().parents[1]
    script = root / "scripts_dc3pa" / "build_frozen_memory.py"
    output_root = tmp_path / "snapshot"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--acquisition-root",
            str(acquisition_root),
            "--output-root",
            str(output_root),
            "--source-commit",
            "test",
            "--min-dependency-support",
            "1",
            "--development-encoders",
            "--snapshot-metadata-json",
            json.dumps({"paper_memory_generation": "v5-test"}),
            "--reset-output",
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((output_root / "snapshot_manifest.json").read_text())
    stats = json.loads((output_root / "build_stats.json").read_text())
    assert manifest["schema_version"] == 2
    assert manifest["asset_files"]
    assert manifest["metadata"]["paper_memory_generation"] == "v5-test"
    assert stats["structured_action_key_scenes"] == 1
    assert stats["structured_action_key_coverage"] == 1.0
    with sqlite3.connect(output_root / "memory.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM dependency_edges").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM scene_exemplars").fetchone()[0] == 1
        metadata = json.loads(
            connection.execute(
                "SELECT metadata_json FROM scene_exemplars"
            ).fetchone()[0]
        )
        assert metadata["action_key"] == "craft:wooden_pickaxe"
