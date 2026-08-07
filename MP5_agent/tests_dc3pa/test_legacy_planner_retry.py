from __future__ import annotations

import sys
from pathlib import Path

import pytest
from langchain.schema import HumanMessage


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from planner import Planner  # noqa: E402


class FakeMemory:
    def __init__(self):
        self.reset_calls = 0

    def reset_current_environment_information(self):
        self.reset_calls += 1


class RaisingLLM:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def __call__(self, message):
        self.calls += 1
        raise self.error


class SuccessfulLLM:
    def __init__(self):
        self.calls = 0

    def __call__(self, message):
        self.calls += 1
        return type("Response", (), {"content": '{"workflow": [{"times": "1", "actions": []}]}'})()


def _planner_with_error(error):
    planner = Planner.__new__(Planner)
    planner.memory = FakeMemory()
    planner.llm = RaisingLLM(error)
    return planner


def test_planner_fails_fast_on_permission_or_quota_errors():
    planner = _planner_with_error(
        RuntimeError("token quota is not enough, token remain quota: 2.35")
    )
    with pytest.raises(RuntimeError, match="token quota"):
        planner.get_workflow([HumanMessage(content="plan")])

    assert planner.llm.calls == 1
    assert planner.memory.reset_calls == 0


def test_planner_still_retries_transient_errors(monkeypatch):
    planner = _planner_with_error(RuntimeError("temporary upstream disconnect"))
    monkeypatch.setattr("planner.time.sleep", lambda seconds: None)

    result = planner.get_workflow([HumanMessage(content="plan")], max_retries=2)

    assert result == {}
    assert planner.llm.calls == 2
    assert planner.memory.reset_calls == 2


def test_transport_failure_rotates_to_the_next_configured_key(monkeypatch):
    planner = _planner_with_error(RuntimeError("APIConnectionError: connection error"))
    planner._api_keys = ("primary-key", "backup-key")
    planner._active_key_index = 0
    built_keys = []

    def build_llm(key):
        built_keys.append(key)
        return SuccessfulLLM()

    planner._build_llm = build_llm
    monkeypatch.setattr("planner.time.sleep", lambda seconds: None)

    result = planner.get_workflow([HumanMessage(content="plan")], max_retries=2)

    assert result["workflow"]
    assert built_keys == ["backup-key"]
    assert planner._active_key_index == 1
