"""Repository-specific controlled success fixture for Round 5.9.2."""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from dc3pa.experiments.final_taskset_release import (
    TaskSemanticReceipt,
    save_immutable,
)
from dc3pa.integration.legacy import LegacyGoalChecker


ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = ROOT / "agent"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _inventory_item_for_target(target: str) -> str:
    normalized = str(target).strip().lower()
    # The coal-ore task is completed by its survival drop, not by carrying the
    # source block itself. Other controlled fixtures retain their exact item.
    if normalized == "coal ore":
        return "coal"
    return normalized.replace(" ", "_")


def _spawned_block_for(environment_target: str) -> str:
    return {
        "coal": "coal_ore",
        "iron_ingot": "iron_ore",
    }.get(environment_target, "not_applicable")


@contextlib.contextmanager
def _agent_directory():
    previous = Path.cwd()
    os.chdir(AGENT_DIR)
    try:
        yield
    finally:
        os.chdir(previous)


@contextlib.contextmanager
def _seed_environment(seed: str):
    names = ("DC3PA_WORLD_SEED", "DC3PA_SIM_SEED", "MP5_DISABLE_MEMORY")
    previous = {name: os.environ.get(name) for name in names}
    os.environ["DC3PA_WORLD_SEED"] = seed
    os.environ["DC3PA_SIM_SEED"] = seed
    os.environ["MP5_DISABLE_MEMORY"] = "1"
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def collect_task_semantic_receipt(
    *,
    runtime_task_path: str | Path,
    difficulty: str,
    source_commit: str,
    task_asset_validation_report_id: str,
    requested_seed: str,
    output_receipt: str | Path,
    output_trace: str | Path,
    output_observation: str | Path,
) -> TaskSemanticReceipt:
    """Observe the unchanged production success path against a real environment."""
    task_path = Path(runtime_task_path).resolve()
    trace_path = Path(output_trace)
    observation_path = Path(output_observation)
    for path in (trace_path, observation_path, Path(output_receipt)):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite semantic evidence: {path}")

    if str(AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(AGENT_DIR))
    environment_started = False
    controller_started = False
    evaluator = None
    with _seed_environment(str(requested_seed)), _agent_directory():
        runner = importlib.import_module("run_agent")
        stage6 = importlib.import_module("scripts_dc3pa.stage6_run_minecraft")
        loaded = stage6._load_task_list(task_path)
        if len(loaded) != 1:
            raise ValueError("Semantic fixture requires exactly one runtime task")
        task_information = dict(loaded[0])
        target = str(task_information["task"])
        quantity = int(task_information["quantity"])
        inventory_item = _inventory_item_for_target(target)
        runner.args = SimpleNamespace(
            mllm_url="",
            openai_key="",
            gpt_model_name="gpt-5.1",
            task=str(task_path),
            answer_method="active",
            answer_model="mllm",
        )
        original_make = runner.minedojo.make

        def make_with_controlled_inventory(*args, **kwargs):
            if "initial_inventory" in kwargs:
                raise ValueError("Evaluator unexpectedly supplied initial_inventory")
            kwargs["initial_inventory"] = [
                runner.InventoryItem(
                    slot=9,
                    name=inventory_item,
                    variant=None,
                    quantity=quantity,
                )
            ]
            return original_make(*args, **kwargs)

        runner.minedojo.make = make_with_controlled_inventory
        try:
            evaluator = runner.Evaluator()
        finally:
            runner.minedojo.make = original_make
        try:
            environment_started = evaluator.env is not None
            observation = evaluator.env.reset()
            inventory = runner.count_inventory(
                observation["inventory"]["name"].tolist(),
                observation["inventory"]["quantity"].tolist(),
            )
            memory = SimpleNamespace(inventory=inventory)
            controller = runner.Controller(memory=memory, checker=None)
            controller_started = True
            controller_success = bool(
                controller.check_done(task_information, memory)
            )
            # Stage6 evaluates task completion through this production adapter;
            # legacy Evaluator itself has no separate active check_done method.
            evaluator_success = LegacyGoalChecker(
                controller, memory
            ).is_done(task_information)
            success_inventory_name = inventory_item.replace("_", " ")
            success_observed = (
                inventory.get(success_inventory_name, 0) >= quantity
            )

            observation_payload: Mapping[str, Any] = {
                "inventory": {
                    "name": sorted(inventory),
                    "quantity": [inventory[name] for name in sorted(inventory)],
                },
                "target": target,
                "required_quantity": quantity,
            }
            trace_payload: Mapping[str, Any] = {
                "runtime_task_path_sha256": hashlib.sha256(
                    task_path.read_bytes()
                ).hexdigest(),
                "task": task_information,
                "requested_seed": str(requested_seed),
                "effective_world_seed": str(evaluator.effective_world_seed),
                "effective_simulator_seed": str(evaluator.effective_simulator_seed),
                "agent_target_name": str(evaluator.task_target_name),
                "environment_target_name": str(evaluator.env_target_name),
                "spawned_block_name": _spawned_block_for(
                    str(evaluator.env_target_name)
                ),
                "controller_success": controller_success,
                "evaluator_success": evaluator_success,
                "provider_call_count": 0,
                "controlled_state_api": "minedojo.make(initial_inventory=...)",
            }
            save_immutable(trace_path, trace_payload)
            save_immutable(observation_path, observation_payload)

            receipt_payload = {
                "task_name": f"craft {target}" if task_path.stem.startswith("craft_") else f"mine {target}",
                "difficulty": difficulty,
                "source_commit": source_commit,
                "task_asset_validation_report_id": task_asset_validation_report_id,
                "semantic_validation_mode": "controlled_success_fixture",
                "requested_seed": str(requested_seed),
                "effective_seed": str(evaluator.effective_world_seed),
                "effective_simulator_seed": str(evaluator.effective_simulator_seed),
                "process_exit_code": 0,
                "environment_started": environment_started,
                "controller_started": controller_started,
                "actual_runtime_task_loaded": True,
                "agent_target_name": str(evaluator.task_target_name),
                "environment_target_name": str(evaluator.env_target_name),
                "spawned_block_name": _spawned_block_for(str(evaluator.env_target_name)),
                "controller_success_target_name": target,
                "evaluator_success_target_name": target,
                "inventory_name_field": "inventory.name",
                "inventory_quantity_field": "inventory.quantity",
                "evaluator_delegates_to_controller": True,
                "success_condition_observed": success_observed,
                "controller_success_observed": controller_success,
                "evaluator_success_observed": evaluator_success,
                "controller_evaluator_agree": controller_success == evaluator_success,
                "task_completed": success_observed and controller_success and evaluator_success,
                "provider_call_count": 0,
                "formal_memory_used": False,
                "excluded_from_formal_fitting": True,
                "technical_failure_count": 0,
                "trace_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
                "observation_sha256": hashlib.sha256(
                    observation_path.read_bytes()
                ).hexdigest(),
                "notes": "Evaluator completion delegates to production LegacyGoalChecker and Controller.check_done.",
            }
            receipt = TaskSemanticReceipt(
                receipt_id=_sha(receipt_payload),
                **receipt_payload,
            )
            if not receipt.task_completed:
                raise RuntimeError(
                    f"Controlled semantic success was not observed for {target}: {inventory}"
                )
            save_immutable(output_receipt, receipt.to_dict())
            return receipt
        finally:
            if evaluator is not None and evaluator.env is not None:
                evaluator.env.close()


__all__ = [
    "collect_task_semantic_receipt",
    "_inventory_item_for_target",
    "_spawned_block_for",
]
