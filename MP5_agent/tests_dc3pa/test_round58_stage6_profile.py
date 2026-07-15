from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from dc3pa.experiments.blueprint import AcquisitionAssignment
from tests_dc3pa.round56_helpers import make_blueprint


def test_stage6_reference_profile_replaces_roles_and_applies_approved_seed(
    monkeypatch, tmp_path
):
    import scripts_dc3pa.stage6_run_minecraft as launcher

    seed = "1234567"
    blueprint = make_blueprint(
        acquisition=(
            AcquisitionAssignment(
                group_id="acq-reference",
                task="basic-task-0",
                seed=seed,
                task_kind="experience_covered_final_goal",
                difficulty="basic",
                sequence_index=0,
            ),
        )
    )
    blueprint_path = tmp_path / "blueprint.json"
    blueprint_path.write_text(
        json.dumps(blueprint.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    task_path = tmp_path / "task.json"
    task_path.write_text(
        json.dumps([{"task": "basic-task-0", "quantity": 1}]),
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {
                    "mode": "reasoning_only",
                    "max_execution_attempts": 1,
                    "memory_mode": "disabled",
                    "record_legacy_workflow_memory": False,
                    "record_multimodal_memory": False,
                },
                "hybrid_probability": {},
                "dual_chain": {},
                "adaptive_trigger": {},
            }
        ),
        encoding="utf-8",
    )
    trace_path = tmp_path / "trace.jsonl"
    observed = {}

    class FakeEnv:
        def reset(self):
            return None

        def set_inventory(self, inventory):
            return None

        def step(self, action):
            return {
                "inventory": {
                    "name": SimpleNamespace(tolist=lambda: []),
                    "quantity": SimpleNamespace(tolist=lambda: []),
                }
            }, 0, False, {}

    class FakeEvaluator:
        def __init__(self):
            self.env = FakeEnv()
            self.effective_world_seed = int(os.environ["DC3PA_WORLD_SEED"])
            self.effective_simulator_seed = int(os.environ["DC3PA_SIM_SEED"])

    class FakeMemory:
        inventory = {}

        def __init__(self, *args, **kwargs):
            self.llm = object()

    class FakePlanner:
        def __init__(self, *args, **kwargs):
            self.llm = object()

    class FakeReflexion:
        def __init__(self, *args, **kwargs):
            self.llm = object()

    class FakeController:
        def __init__(self, *args, **kwargs):
            return None

    fake_module = SimpleNamespace(
        Evaluator=FakeEvaluator,
        Work_Memory=FakeMemory,
        Reflexion=FakeReflexion,
        Planner=FakePlanner,
        Controller=FakeController,
        share_memory=lambda memory, events: None,
        args=None,
    )

    class FakeRuntime:
        def run_task(self, task_information, underground=False):
            return SimpleNamespace(
                success=True,
                final_underground=False,
                to_dict=lambda: {"success": True, "task": task_information["task"]},
            )

    def fake_build_runtime(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(runtime=FakeRuntime())

    monkeypatch.setattr(launcher.importlib, "import_module", lambda name: fake_module)
    monkeypatch.setattr(launcher, "_validate_display_available", lambda: None)
    monkeypatch.setattr(launcher, "build_legacy_state_provider", lambda **kwargs: object())
    monkeypatch.setattr(launcher, "build_stage6_runtime", fake_build_runtime)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    rc = launcher.main(
        [
            "--mode",
            "reasoning_only",
            "--model-profile",
            "gpt51_reference",
            "--task",
            str(task_path),
            "--config",
            str(config_path),
            "--memory-root",
            str(tmp_path / "memory"),
            "--trace",
            str(trace_path),
            "--real-experiment-blueprint",
            str(blueprint_path),
            "--real-experiment-phase",
            "acquisition_completed",
            "--real-experiment-task",
            "basic-task-0",
            "--real-experiment-seed",
            seed,
        ]
    )

    assert rc == 0
    assert fake_module.args.gpt_model_name == "gpt-5.1"
    assert observed["chat_model"]._model.purpose == "dc3pa_confidence_and_evaluation"
    assert observed["chat_model"]._include_error_detail is False
    events = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    seed_event = next(
        event for event in events if event["event_type"] == "environment_seed_applied"
    )
    assert seed_event["payload"] == {
        "application_point": "minedojo.make",
        "effective_simulator_seed": int(seed),
        "effective_world_seed": int(seed),
        "requested_seed": int(seed),
    }
    profile_event = next(
        event for event in events if event["event_type"] == "model_profile_activated"
    )
    assert profile_event["payload"]["model"] == "gpt-5.1"


def test_stage6_legacy_model_profile_remains_default():
    import scripts_dc3pa.stage6_run_minecraft as launcher

    assert launcher._resolve_model_profile("", {}) is None
    assert launcher._resolve_model_profile("legacy", {"model_profile": "gpt51_reference"}) is None


@pytest.mark.minedojo
def test_real_legacy_evaluator_passes_requested_seed_to_minedojo_make(
    monkeypatch, tmp_path
):
    import minedojo

    agent_dir = Path(__file__).resolve().parents[1] / "agent"
    monkeypatch.syspath_prepend(str(agent_dir))
    monkeypatch.chdir(tmp_path)
    task_path = tmp_path / "task.json"
    task_path.write_text(
        json.dumps([{"task": "log", "quantity": 1}]), encoding="utf-8"
    )
    captured = {}

    class FakeEnv:
        pass

    def fake_make(**kwargs):
        captured.update(kwargs)
        return FakeEnv()

    monkeypatch.setattr(minedojo, "make", fake_make)
    monkeypatch.setenv("DC3PA_WORLD_SEED", "7654321")
    monkeypatch.setenv("DC3PA_SIM_SEED", "7654321")
    spec = importlib.util.spec_from_file_location(
        "round58_real_run_agent", agent_dir / "run_agent.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.args = SimpleNamespace(
        mllm_url="",
        openai_key="unused",
        task=str(task_path),
    )

    evaluator = module.Evaluator()

    assert captured["world_seed"] == 7654321
    assert captured["seed"] == 7654321
    assert evaluator.effective_world_seed == 7654321
    assert evaluator.effective_simulator_seed == 7654321
