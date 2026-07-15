from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

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
    assert "--real-experiment-blueprint" in result.stdout


def test_minecraft_entrypoint_rejects_missing_display_before_legacy_import(
    monkeypatch, tmp_path
):
    import scripts_dc3pa.stage6_run_minecraft as launcher

    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps([{"task": "log", "quantity": 1}]), encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {"mode": "reasoning_only", "max_execution_attempts": 1},
                "hybrid_probability": {},
                "dual_chain": {},
                "adaptive_trigger": {},
            }
        ),
        encoding="utf-8",
    )
    imported = {"legacy": False}

    def fail_if_imported(name):
        imported["legacy"] = True
        raise AssertionError(name)

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(launcher.importlib, "import_module", fail_if_imported)

    try:
        launcher.main(
            [
                "--mode",
                "reasoning_only",
                "--openai_key",
                "test-key",
                "--gpt_model_name",
                "gpt-4-turbo",
                "--task",
                str(task_path),
                "--config",
                str(config_path),
                "--memory-root",
                str(tmp_path / "memory"),
                "--trace",
                str(tmp_path / "trace.jsonl"),
            ]
        )
    except RuntimeError as exc:
        assert "DISPLAY is not set" in str(exc)
    else:
        raise AssertionError("launcher should reject a missing DISPLAY")
    assert imported["legacy"] is False


def test_minecraft_entrypoint_enters_legacy_agent_cwd_with_absolute_paths(monkeypatch, tmp_path):
    import scripts_dc3pa.stage6_run_minecraft as launcher
    from tests_dc3pa.round56_helpers import make_blueprint

    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps([{"task": "log", "quantity": 1}]), encoding="utf-8")
    blueprint = make_blueprint()
    blueprint_path = tmp_path / "blueprint.json"
    blueprint_path.write_text(
        json.dumps(blueprint.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {"mode": "reasoning_only", "max_execution_attempts": 1},
                "hybrid_probability": {},
                "dual_chain": {},
                "adaptive_trigger": {},
            }
        ),
        encoding="utf-8",
    )
    memory_root = tmp_path / "memory"
    trace_path = tmp_path / "trace.jsonl"
    observed = {}

    class FakeEnv:
        def reset(self):
            pass

        def set_inventory(self, inventory):
            pass

        def step(self, action):
            return {
                "inventory": {
                    "name": SimpleNamespace(tolist=lambda: []),
                    "quantity": SimpleNamespace(tolist=lambda: []),
                }
            }, 0, False, {}

    class FakeEvaluator:
        def __init__(self):
            observed["cwd"] = Path.cwd()
            observed["task_path"] = fake_module.args.task
            self.env = FakeEnv()

    class FakeMemory:
        llm = None
        inventory = {}

        def __init__(self, *args, **kwargs):
            pass

    class FakePlanner:
        def __init__(self, *args, **kwargs):
            pass

    class FakeReflexion:
        def __init__(self, *args, **kwargs):
            pass

    class FakeController:
        def __init__(self, *args, **kwargs):
            pass

    fake_module = SimpleNamespace(
        Evaluator=FakeEvaluator,
        Work_Memory=FakeMemory,
        Reflexion=FakeReflexion,
        Planner=FakePlanner,
        Controller=FakeController,
        share_memory=lambda memory, events: None,
        args=None,
    )

    class FakeMultimodalMemory:
        def __init__(self, root, **kwargs):
            observed["memory_root"] = Path(root)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    class FakeRuntime:
        def run_task(self, task_information, underground=False):
            return SimpleNamespace(
                success=True,
                final_underground=False,
                to_dict=lambda: {"success": True, "task": task_information["task"]},
            )

    monkeypatch.setattr(launcher.importlib, "import_module", lambda name: fake_module)
    monkeypatch.setattr(launcher, "_validate_display_available", lambda: None)
    monkeypatch.setattr(launcher, "MultimodalMemory", FakeMultimodalMemory)
    monkeypatch.setattr(
        launcher,
        "build_legacy_state_provider",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        launcher,
        "build_stage6_runtime",
        lambda **kwargs: SimpleNamespace(runtime=FakeRuntime()),
    )

    rc = launcher.main(
        [
            "--mode",
            "reasoning_only",
            "--openai_key",
            "test-key",
            "--gpt_model_name",
            "gpt-4-turbo",
            "--task",
            str(task_path),
            "--config",
            str(config_path),
            "--memory-root",
            str(memory_root),
            "--trace",
            str(trace_path),
            "--real-experiment-blueprint",
            str(blueprint_path),
            "--real-experiment-phase",
            "dry_run_completed",
            "--real-experiment-task",
            "basic-task-0",
            "--real-experiment-seed",
            "dev-train",
            "--real-experiment-run-manifest-id",
            "stage6=manifest-id",
        ]
    )

    assert rc == 0
    assert observed["cwd"] == ROOT / "agent"
    assert Path(observed["task_path"]).is_absolute()
    assert observed["memory_root"].is_absolute()
    events = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    validation = [
        event
        for event in events
        if event["event_type"] == "real_experiment_launch_validated"
    ]
    assert validation[0]["payload"]["blueprint_id"] == blueprint.blueprint_id
    assert validation[0]["payload"]["run_manifest_ids"]["stage6"] == "manifest-id"
    assert Path.cwd() == ROOT
