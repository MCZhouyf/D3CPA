#!/usr/bin/env python3
"""Run a hermetic dynamic trace of the existing delayed log callback."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    agent_dir = args.repo.resolve() / "MP5_agent" / "agent"
    sys.path.insert(0, str(agent_dir))
    from controller import Controller

    class Memory:
        def __init__(self) -> None:
            self.inventory: dict[str, float] = {}

        def update_inventory(self, inventory):
            self.inventory = dict(inventory)

    class Env:
        def __init__(self, memory: Memory) -> None:
            self.memory, self.step_count, self.set_calls = memory, 0, []

        def step(self, _action):
            self.step_count += 1
            return ({"inventory": {"name": np.array(list(self.memory.inventory)), "quantity": np.array(list(self.memory.inventory.values()))}}, 0, False, {})

        def set_inventory(self, items):
            self.set_calls.append(list(items))
            self.memory.inventory = {item.name.replace("_", " "): float(item.quantity) for item in items}

    controller = Controller.__new__(Controller)
    controller.memory, controller.checker = Memory(), object()
    env = Env(controller.memory)
    import controller as controller_module
    originals = {
        "check_find": controller_module.check_find,
        "approach": controller_module.approach,
        "explore_above_ground_none": controller_module.explore_above_ground_none,
    }
    try:
        controller_module.check_find = lambda *args, **kwargs: False
        controller_module.approach = lambda *args, **kwargs: False
        controller_module.explore_above_ground_none = lambda *args, **kwargs: None
        success = controller._gather_logs(env, underground=False, target_logs=2)
    finally:
        for name, value in originals.items():
            setattr(controller_module, name, value)
    trace = {
        "scenario": "unreachable_log_until_delayed_callback",
        "success": success,
        "environment_steps": env.step_count,
        "inventory_writes": [[{"name": item.name, "quantity": item.quantity} for item in call] for call in env.set_calls],
        "final_inventory": controller.memory.inventory,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(trace, sort_keys=True))
    return 0 if success and env.step_count >= 100 and trace["inventory_writes"] == [[{"name": "log", "quantity": 2}]] else 1


if __name__ == "__main__":
    raise SystemExit(main())
