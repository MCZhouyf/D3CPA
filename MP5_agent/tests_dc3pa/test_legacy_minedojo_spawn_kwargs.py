from __future__ import annotations

import importlib
import json
import sys
from types import SimpleNamespace

import pytest

from tests_dc3pa.legacy_controller_test_gate import (
    missing_legacy_controller_dependencies,
)


pytestmark = pytest.mark.minedojo
_missing_legacy_deps = missing_legacy_controller_dependencies()
if _missing_legacy_deps:
    pytest.skip(
        "legacy MineDojo spawn tests require optional runtime modules: "
        + ", ".join(_missing_legacy_deps),
        allow_module_level=True,
    )


def _load_run_agent(monkeypatch, tmp_path, task_name):
    task_path = tmp_path / f"{task_name}.json"
    task_path.write_text(
        json.dumps([{"task": task_name, "quantity": 1}]),
        encoding="utf-8",
    )
    agent_dir = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "agent")
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)
    module = importlib.import_module("agent.run_agent")
    monkeypatch.setattr(
        module,
        "args",
        SimpleNamespace(
            mllm_url="",
            openai_key="test-key",
            gpt_model_name="gpt-4-turbo",
            task=str(task_path),
            answer_method="active",
            answer_model="mllm",
        ),
        raising=False,
    )
    monkeypatch.setattr(module, "f_mkdir", lambda path: None)
    monkeypatch.setattr(module, "f_remove", lambda path: None)
    monkeypatch.setattr(module.logging, "basicConfig", lambda **kwargs: None)
    return module


def test_cobblestone_does_not_pass_unsupported_extra_spawn_kwargs(monkeypatch, tmp_path):
    module = _load_run_agent(monkeypatch, tmp_path, "cobblestone")
    captured = {}

    def fake_make(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(module.minedojo, "make", fake_make)
    module.Evaluator()

    assert captured["target_names"] == "cobblestone"
    assert "spawn_rate" not in captured
    assert "spawn_range_low" not in captured
    assert "spawn_range_high" not in captured


def test_diamond_keeps_supported_extra_spawn_kwargs(monkeypatch, tmp_path):
    module = _load_run_agent(monkeypatch, tmp_path, "diamond")
    captured = {}

    def fake_make(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(module.minedojo, "make", fake_make)
    module.Evaluator()

    assert captured["target_names"] == "diamond"
    assert captured["spawn_rate"] == 1
    assert captured["spawn_range_low"] == (-10, -10, -10)
    assert captured["spawn_range_high"] == (10, 10, 10)
