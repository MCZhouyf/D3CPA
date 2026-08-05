from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from controller import Controller  # noqa: E402


class _Memory:
    def __init__(self) -> None:
        self.inventory: dict[str, float] = {}

    def update_inventory(self, inventory):
        self.inventory = dict(inventory)


class _Env:
    def __init__(self, memory: _Memory) -> None:
        self.memory = memory
        self.step_count = 0
        self.set_calls = []

    def step(self, _action):
        self.step_count += 1
        return ({"inventory": {"name": np.array(list(self.memory.inventory)), "quantity": np.array(list(self.memory.inventory.values()))}}, 0, False, {})

    def set_inventory(self, items):
        self.set_calls.append(list(items))
        self.memory.inventory = {item.name.replace("_", " "): float(item.quantity) for item in items}


def test_g0_dynamic_log_callback_trace_preserves_delayed_log_only_write(monkeypatch) -> None:
    controller = Controller.__new__(Controller)
    controller.memory = _Memory()
    controller.checker = object()
    env = _Env(controller.memory)
    monkeypatch.setattr("controller.check_find", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.approach", lambda *args, **kwargs: False)
    monkeypatch.setattr("controller.explore_above_ground_none", lambda *args, **kwargs: None)

    assert controller._gather_logs(env, underground=False, target_logs=2)
    assert env.step_count >= 100
    assert len(env.set_calls) == 1
    assert [(item.name, item.quantity) for item in env.set_calls[0]] == [("log", 2)]
    assert controller.memory.inventory == {"log": 2.0}
