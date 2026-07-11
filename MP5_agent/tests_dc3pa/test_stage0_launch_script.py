import json
import subprocess
import sys
from pathlib import Path


def test_stage0_dry_run_creates_one_non_overwriting_manifest_per_seed(tmp_path):
    repo = tmp_path / "repo"
    agent = repo / "MP5_agent" / "agent"
    agent.mkdir(parents=True)
    (agent / "run_agent.py").write_text(
        "from pathlib import Path\n"
        "Path('../logs').mkdir(exist_ok=True)\n"
        "Path('../logs/agent.log').write_text('legacy detail\\n')\n"
        "print('Task log | Iteration 1 | Successful True | Episode length 2 | Success rate 1.0')\n",
        encoding="utf-8",
    )
    task = agent / "tasks" / "log.json"
    task.parent.mkdir()
    task.write_text('[{"task": "log", "quantity": 1}]\n', encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "mp5_legacy",
                "task_file": None,
                "model_name": None,
                "seeds": [2, 3],
                "output_dir": "runs/test",
                "feature_flags": {},
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts_dc3pa"
        / "stage0_launch.py"
    )
    command = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo),
        "--config",
        str(config),
        "--task",
        str(task),
        "--model",
        "stub-model",
        "--run-id",
        "fixed",
        "--dry-run",
    ]
    first = subprocess.run(command, text=True, capture_output=True, check=False)
    assert first.returncode == 0, first.stderr
    manifests = sorted((repo / "runs" / "test" / "log" / "fixed").rglob("manifest.json"))
    assert [path.parent.name for path in manifests] == ["seed_2", "seed_3"]
    assert json.loads(manifests[0].read_text())["config"]["seeds"] == [2]
    assert json.loads(manifests[1].read_text())["config"]["seeds"] == [3]

    second = subprocess.run(command, text=True, capture_output=True, check=False)
    assert second.returncode != 0
    assert "never overwritten automatically" in second.stderr


def test_stage0_execution_copies_legacy_log_and_writes_metrics(tmp_path):
    repo = tmp_path / "repo"
    agent = repo / "MP5_agent" / "agent"
    agent.mkdir(parents=True)
    (agent / "run_agent.py").write_text(
        "from pathlib import Path\n"
        "Path('../logs').mkdir(exist_ok=True)\n"
        "Path('../logs/agent.log').write_text('legacy detail\\n')\n"
        "print('Task log | Iteration 1 | Successful True | Episode length 2 | Success rate 1.0')\n",
        encoding="utf-8",
    )
    task = agent / "tasks" / "log.json"
    task.parent.mkdir()
    task.write_text('[{"task": "log", "quantity": 1}]\n', encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "mp5_legacy",
                "task_file": str(task),
                "model_name": "stub-model",
                "seeds": [2],
                "output_dir": "runs/test",
                "feature_flags": {},
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[1] / "scripts_dc3pa" / "stage0_launch.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo-root",
            str(repo),
            "--config",
            str(config),
            "--run-id",
            "executed",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    run_dir = repo / "runs" / "test" / "log" / "executed" / "seed_2"
    assert (run_dir / "legacy_agent.log").read_text() == "legacy detail\n"
    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert metrics["success_rate"] == 1.0
    assert metrics["average_replanning_count"] == 1.0
