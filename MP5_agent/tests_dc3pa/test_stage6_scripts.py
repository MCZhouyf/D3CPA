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


def test_g0_runtime_resolution_has_one_seed_and_no_legacy_recovery(monkeypatch, tmp_path):
    import scripts_dc3pa.stage6_run_minecraft as launcher

    config = tmp_path / "g0.json"
    config.write_text(
        json.dumps(
            {
                "episode_seed": 17,
                "model": {
                    "base_url": "https://relay.invalid/v1",
                    "model": "glm-test",
                    "api_key_environment_variable": "TEST_G0_KEY",
                },
                "budgets": {
                    "max_replans_per_task": 30,
                    "max_environment_steps": 12000,
                    "action_attempts": {"mine": 1, "craft": 1, "smelt": 1},
                },
                "feature_flags": {
                    "legacy_task_hacks": False,
                    "controller_low_level_recovery": False,
                    "legacy_workflow_memory": False,
                    "dc3pa_memory": False,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_G0_KEY", "not-a-real-key")
    monkeypatch.delenv("EPISODE_SEED", raising=False)
    args = launcher.build_parser().parse_args(
        ["--g0-runtime-config", str(config)]
    )

    resolved = launcher._resolve_g0_runtime(args)

    assert resolved["model"] == "glm-test"
    assert resolved["episode_seed"] == 17
    assert resolved["max_replans_per_task"] == 30
    assert resolved["action_attempts"] == {"mine": 1, "craft": 1, "smelt": 1}
    assert os.environ["EPISODE_SEED"] == "17"
    assert os.environ["DC3PA_WORLD_SEED"] == "17"
    assert os.environ["DC3PA_SIM_SEED"] == "17"
    assert os.environ["DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK"] == "0"
    assert os.environ["MP5_DISABLE_MEMORY"] == "1"
    assert os.environ["DC3PA_LLM_TEMPERATURE"] == "0.0"
    assert os.environ["DC3PA_LLM_TOP_P"] == "1.0"
    assert os.environ["DC3PA_LLM_MAX_TOKENS"] == "4096"
    assert os.environ["DC3PA_LLM_MAX_RETRIES"] == "1"
    assert "openai_key" in resolved


def test_minecraft_entrypoint_enters_legacy_agent_cwd_with_absolute_paths(monkeypatch, tmp_path):
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
    memory_root = tmp_path / "memory"
    trace_path = tmp_path / "trace.jsonl"
    observed = {}
    initial_cwd = Path.cwd()

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
        ]
    )

    assert rc == 0
    assert observed["cwd"] == ROOT / "agent"
    assert Path(observed["task_path"]).is_absolute()
    assert observed["memory_root"].is_absolute()
    assert Path.cwd() == initial_cwd
