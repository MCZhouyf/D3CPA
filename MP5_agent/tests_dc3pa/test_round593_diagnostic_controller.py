from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from tests_dc3pa.legacy_controller_test_gate import (
    missing_legacy_controller_dependencies,
)


pytestmark = pytest.mark.minedojo
_missing_legacy_deps = missing_legacy_controller_dependencies()
if _missing_legacy_deps:
    pytest.skip(
        "diagnostic Controller tests require optional runtime modules: "
        + ", ".join(_missing_legacy_deps),
        allow_module_level=True,
    )

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from controller import Controller  # noqa: E402
from dc3pa.experiments.log_fallback import (  # noqa: E402
    DiagnosticLogFallbackSession,
    LogFallbackPolicy,
)


class FakeMemory:
    def __init__(self, inventory=None):
        self.inventory = dict(inventory or {})


class FakeEnv:
    def __init__(self, memory):
        self.memory = memory
        self.set_inventory_calls = []

    def events(self):
        return {
            "inventory": {
                "name": np.array(list(self.memory.inventory), dtype=object),
                "quantity": np.array(
                    list(self.memory.inventory.values()), dtype=float
                ),
            }
        }

    def set_inventory(self, items):
        self.set_inventory_calls.append(tuple(items))
        self.memory.inventory = {
            item.name.replace("_", " "): float(item.quantity) for item in items
        }


def _controller(inventory=None):
    controller = Controller.__new__(Controller)
    controller.memory = FakeMemory(inventory)
    controller.checker = object()
    controller._sync_memory = lambda env: env.events()
    return controller


def test_controller_diagnostic_session_preserves_inventory_and_records_event(
    monkeypatch,
):
    controller = _controller({"log": 1, "stick": 2, "stone pickaxe": 1})
    env = FakeEnv(controller.memory)
    session = DiagnosticLogFallbackSession(
        policy=LogFallbackPolicy().with_id(),
        source_commit="commit",
        task="craft fence",
        seed="17",
    )
    controller._dc3pa_log_fallback_session = session
    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "controller.explore_above_ground_none", lambda *args, **kwargs: None
    )

    assert controller._gather_logs(env, False, target_logs=4, max_attempts=3)

    assert controller.memory.inventory == {
        "log": 4.0,
        "stick": 2.0,
        "stone pickaxe": 1.0,
    }
    assert len(env.set_inventory_calls) == 1
    assert len(session.events) == 1
    assert session.events[0].injected_count == 3


def test_controller_without_session_never_calls_set_inventory(monkeypatch):
    controller = _controller({"stick": 2})
    env = FakeEnv(controller.memory)
    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "controller.explore_above_ground_none", lambda *args, **kwargs: None
    )

    assert not controller._gather_logs(env, False, target_logs=2, max_attempts=3)
    assert not env.set_inventory_calls
