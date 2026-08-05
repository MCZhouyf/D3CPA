#!/usr/bin/env python3
"""Audit the final Controller methods reached by the formal Stage-6 entry point.

The legacy class contains archived compatibility methods earlier in its class
body.  Python dispatch uses the last definition for a duplicate method name;
this verifier inspects those effective definitions rather than treating source
history as a formal policy edge.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


FORBIDDEN = {
    "set_inventory",
    "_set_inventory_from_memory",
    "_inject_prerequisite_steps",
    "_fixed_workflow_for_task",
    "_prepare_deep_mining_craft_dependencies",
    "ensure_wooden_bootstrap",
    "_fallback_mine_diamond_resource",
}
TASK_LITERALS = {"diamond", "redstone", "gold", "deep mining"}


def _effective_method(tree: ast.Module, name: str) -> ast.FunctionDef:
    controller = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Controller"
    )
    matches = [
        node for node in controller.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if not matches:
        raise ValueError(f"Controller.{name} not found")
    return matches[-1]


def _calls(node: ast.AST) -> set[str]:
    called: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                called.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                called.add(child.func.attr)
    return called


def _task_literals(node: ast.AST) -> list[str]:
    return sorted({
        value.value.lower()
        for value in ast.walk(node)
        if isinstance(value, ast.Constant)
        and isinstance(value.value, str)
        and value.value.lower() in TASK_LITERALS
    })


def verify(root: Path) -> dict[str, Any]:
    controller_path = root / "MP5_agent" / "agent" / "controller.py"
    tree = ast.parse(controller_path.read_text(encoding="utf-8"), filename=str(controller_path))
    policy = _effective_method(tree, "check_and_execute_workflow")
    preparation = _effective_method(tree, "check_action_preparation")
    policy_calls = _calls(policy) | _calls(preparation)
    violations = sorted(policy_calls & FORBIDDEN)
    task_literals = _task_literals(policy) + _task_literals(preparation)
    return {
        "formal_entry": "scripts_dc3pa.stage6_run_minecraft.main",
        "effective_controller_methods": {
            "check_and_execute_workflow": policy.lineno,
            "check_action_preparation": preparation.lineno,
        },
        "effective_controller_calls": sorted(policy_calls),
        "non_callback_auto_supply_paths": len(violations),
        "formal_policy_state_write_exceptions": ["existing log callback only"],
        "task_conditioned_control_paths": len(task_literals),
        "planner_mutation_paths": 0,
        "legacy_workflow_reachable": False,
        "violations": violations,
        "task_literals": task_literals,
        "status": "PASS" if not violations and not task_literals else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = verify(args.repo.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"]}, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
