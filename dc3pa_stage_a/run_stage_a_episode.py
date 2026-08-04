#!/usr/bin/env python3
"""Additive Stage A episode launcher.

It installs InventoryWriteLogger around the MineDojo object returned by the
existing Stage6 launcher, then delegates execution to that launcher unchanged.
No MP5/DC3PA source is imported or modified until after the frozen Option-B
configuration has been asserted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
MP5_ROOT = ROOT / "MP5_agent"
for candidate in (ROOT, MP5_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from dc3pa_stage_a.inventory_write_logger import InventoryWriteLogger
from dc3pa_stage_a.paper_config import PaperRunConfig, load


class EnvironmentStepBudgetExceeded(RuntimeError):
    """Raised before a task attempts its (max_steps + 1)-th environment step."""


class StepBudgetEnv:
    """Transparent MineDojo proxy that enforces a whole-episode step budget."""

    def __init__(self, env: Any, max_steps: int) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        self._env = env
        self.max_steps = int(max_steps)
        self.step_count = 0

    def step(self, *args: Any, **kwargs: Any) -> Any:
        if self.step_count >= self.max_steps:
            raise EnvironmentStepBudgetExceeded(
                f"environment_step_budget_exhausted: {self.max_steps} steps"
            )
        self.step_count += 1
        return self._env.step(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._env, name)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _task_name(task_path: Path) -> str:
    payload = _json(task_path)
    rows = payload if isinstance(payload, list) else [payload]
    if len(rows) != 1 or not isinstance(rows[0], Mapping) or not rows[0].get("task"):
        raise ValueError("Stage A launcher requires exactly one task object with task")
    return str(rows[0]["task"])


def _assert_formal_task(task_path: Path, taskset_manifest: Path) -> Mapping[str, Any]:
    task_path = task_path.resolve()
    manifest = _json(taskset_manifest)
    for entry in manifest.get("entries", []):
        if Path(entry["creative_json"]).resolve() == task_path:
            if _sha256(task_path) != entry["creative_json_sha256"]:
                raise RuntimeError(f"formal task JSON hash drift: {task_path}")
            return entry
    raise ValueError(f"task is not in the frozen formal task manifest: {task_path}")


def _stage6_payload(
    config: PaperRunConfig, snapshot_manifest: Path | None, max_env_steps: int | None = None
) -> Mapping[str, Any]:
    if snapshot_manifest is not None and not snapshot_manifest.is_file():
        raise FileNotFoundError(snapshot_manifest)
    payload = {
        "runtime": {
            "mode": config.runtime_mode,
            "max_execution_attempts": config.max_execution_attempts,
            "unresolved_plan_policy": "block",
            "planner_failure_policy": "reasoning_only",
            "controller_exception_policy": (
                "raise" if max_env_steps is not None else "return_failure"
            ),
            "goal_check_exception_policy": "return_failure",
            "memory_failure_policy": "trace",
            "require_goal_check": True,
            "record_legacy_workflow_memory": config.record_legacy_workflow_memory,
            "record_multimodal_memory": config.record_multimodal_memory,
            "capture_initial_scene": True,
            "capture_final_scene": True,
            "memory_mode": config.memory_mode,
            "telemetry_enabled": True,
        },
        "hybrid_probability": {
            "visual_similarity_weight": 0.7,
            "learned_weight_cap": 0.4,
            "memory_weight_growth": 0.02,
            "require_environment_text_relevance": True,
            "model_failure_mode": "unavailable",
            "task_name_filter_environment": False,
        },
        "dual_chain": {
            "confidence_threshold": 0.8,
            "max_revision_rounds": 4,
            "evaluate_when_unavailable": True,
        },
        "adaptive_trigger": {
            "threshold": 0.8,
            "initial_interval": 3,
            "window_size": 3,
            "minimum_interval": 1,
            "maximum_interval": 64,
            "increase_step": 1,
            "decrease_step": 1,
        },
    }


    if snapshot_manifest is not None:
        payload["runtime"]["memory_snapshot_manifest"] = str(snapshot_manifest.resolve())
    return payload

def _append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True, ensure_ascii=False) + "\n")



def _trace_metrics(path: Path) -> dict[str, Any]:
    completed = failed = 0
    token_usage = []
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue
            event_type = record.get("event_type")
            if event_type == "llm_call_completed":
                completed += 1
            elif event_type == "llm_call_failed":
                failed += 1
            payload = record.get("payload") or {}
            usage = payload.get("usage")
            if isinstance(usage, Mapping):
                token_usage.append(dict(usage))
    return {
        "llm_calls_completed": completed,
        "llm_calls_failed": failed,
        "token_usage": token_usage or None,
        "token_usage_status": "provider_not_exposed_in_stage6_trace" if not token_usage else "captured",
    }


def _action_sequence(controller_results: list[Any]) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    for result in controller_results:
        for event in getattr(result, "telemetry", ()):
            if getattr(event, "event_type", "") != "action_started":
                continue
            payload = getattr(event, "payload", {}) or {}
            sequence.append({
                "plan_id": str(getattr(event, "plan_id", "")),
                "plan_version": int(getattr(event, "plan_version", 0)),
                "step_id": str(getattr(event, "step_id", "")),
                "step_index": int(getattr(event, "step_index", -1)),
                "action_index": int(getattr(event, "action_index", -1)),
                "action": dict(payload.get("action") or {}),
            })
    return sequence

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one frozen Stage A episode")
    parser.add_argument("--paper-config", type=Path, required=True)
    parser.add_argument("--taskset-manifest", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--tier", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--snapshot-manifest", type=Path)
    parser.add_argument("--traversal", choices=("forward", "reverse", "repeat"), default="forward")
    parser.add_argument("--mllm-url", default="")
    parser.add_argument("--openai-key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--gpt-model-name", default=os.environ.get("GPT_MODEL_NAME", ""))
    parser.add_argument("--memory-root", type=Path)
    parser.add_argument("--development-encoders", action="store_true")
    parser.add_argument("--record-inventory-writes", action="store_true")
    parser.add_argument(
        "--max-env-steps",
        type=int,
        help="Whole-episode MineDojo env.step budget; no wall-clock limit is applied.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load(args.paper_config)
    config.export_env()
    config.assert_process_matches()
    if args.tier not in {"basic", "easy", "medium", "hard", "complex"}:
        raise ValueError(f"unknown formal tier: {args.tier}")
    formal_entry = _assert_formal_task(args.task, args.taskset_manifest)
    if formal_entry["tier"] != args.tier:
        raise ValueError(f"tier mismatch: requested={args.tier}, catalog={formal_entry['tier']}")
    task_name = _task_name(args.task)
    run_root = args.run_root.resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        print(json.dumps({
            "status": "dry_run_ok", "task": task_name, "tier": args.tier,
            "runtime_mode": config.runtime_mode, "config_hash": config.config_hash(),
            "task_json_sha256": _sha256(args.task),
        }, sort_keys=True))
        return 0
    if config.memory_mode == "evaluate_readonly" and args.snapshot_manifest is None:
        raise ValueError("--snapshot-manifest is required for evaluate_readonly execution")
    if config.memory_mode != "evaluate_readonly" and args.snapshot_manifest is not None:
        raise ValueError("snapshot manifests are only accepted for evaluate_readonly execution")
    if not args.openai_key or not args.gpt_model_name:
        raise ValueError("openai key and model name are required for execution")
    if args.max_env_steps is not None and args.max_env_steps <= 0:
        raise ValueError("--max-env-steps must be positive")

    stage6_config = run_root / "stage6_runtime_config.json"
    stage6_config.write_text(json.dumps(
        _stage6_payload(config, args.snapshot_manifest, args.max_env_steps), indent=2
    ) + "\n", encoding="utf-8")
    os.environ["DC3PA_WORLD_SEED"] = str(args.seed)
    os.environ["DC3PA_SIM_SEED"] = str(args.seed)

    import minedojo
    from dc3pa.integration.controller import LegacyControllerAdapter
    from dc3pa.integration.runtime import Stage6ClosedLoopRunner
    from scripts_dc3pa import stage6_run_minecraft

    writes = run_root / "inventory_writes.jsonl"
    episodes = run_root / "episodes.jsonl"
    trace = run_root / "stage6_trace.jsonl"
    memory_root = args.memory_root or (run_root / "memory")
    logger: InventoryWriteLogger | None = None
    step_budget_env: StepBudgetEnv | None = None
    original_make = minedojo.make
    original_run_task = Stage6ClosedLoopRunner.run_task
    original_execute = LegacyControllerAdapter.execute
    task_results: list[Any] = []
    controller_results: list[Any] = []
    started = time.monotonic()

    def observed_run_task(self: Any, *run_args: Any, **run_kwargs: Any):
        result = original_run_task(self, *run_args, **run_kwargs)
        task_results.append(result)
        return result

    def observed_execute(self: Any, *execute_args: Any, **execute_kwargs: Any):
        result = original_execute(self, *execute_args, **execute_kwargs)
        controller_results.append(result)
        return result

    def traced_make(*make_args: Any, **make_kwargs: Any):
        nonlocal logger, step_budget_env
        env = original_make(*make_args, **make_kwargs)
        if args.record_inventory_writes:
            logger = InventoryWriteLogger(
            writes,
            context={
                "run_id": args.run_id, "task": task_name, "tier": args.tier,
                "seed": args.seed, "runtime_mode": config.runtime_mode,
                "memory_mode": config.memory_mode, "traversal": args.traversal,
                "config_hash": config.config_hash(),
                "legacy_task_hacks": os.environ["DC3PA_LEGACY_TASK_HACKS"],
                "bounded_resource_fallback": os.environ["DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK"],
            },
            )
            logger.install(env)
        if args.max_env_steps is not None:
            step_budget_env = StepBudgetEnv(env, args.max_env_steps)
            return step_budget_env
        return env

    minedojo.make = traced_make
    Stage6ClosedLoopRunner.run_task = observed_run_task
    LegacyControllerAdapter.execute = observed_execute
    return_code = 1
    error = ""
    try:
        launcher_args = [
            "--mode", config.runtime_mode, "--task", str(args.task.resolve()),
            "--config", str(stage6_config), "--memory-root", str(memory_root.resolve()),
            "--trace", str(trace), "--max-execution-attempts", str(config.max_execution_attempts),
            "--mllm_url", args.mllm_url, "--openai_key", args.openai_key,
            "--gpt_model_name", args.gpt_model_name,
        ]
        if args.development_encoders:
            launcher_args.append("--development-encoders")
        return_code = int(stage6_run_minecraft.main(launcher_args))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        minedojo.make = original_make
        Stage6ClosedLoopRunner.run_task = original_run_task
        LegacyControllerAdapter.execute = original_execute
        if logger is not None:
            logger.uninstall()
        result = task_results[-1] if task_results else None
        attempts = tuple(getattr(result, "attempts", ()) or ())
        _append_jsonl(episodes, {
            "run_id": args.run_id, "task": task_name, "tier": args.tier,
            "seed": args.seed, "runtime_mode": config.runtime_mode,
            "memory_mode": config.memory_mode, "traversal": args.traversal,
            "success": return_code == 0, "exit_code": return_code,
            "config_hash": config.config_hash(), "error": error,
            "wall_clock_seconds": time.monotonic() - started,
            "environment_step_count": step_budget_env.step_count if step_budget_env else None,
            "environment_step_budget": args.max_env_steps,
            "termination_reason": (
                "environment_step_budget_exhausted"
                if "environment_step_budget_exhausted" in error
                else "completed_or_other_error"
            ),
            "attempt_count": len(attempts),
            "max_attempts_reached": bool(result is not None and not getattr(result, "success", False) and len(attempts) >= config.max_execution_attempts),
            "llm": _trace_metrics(trace),
            "action_sequence": _action_sequence(controller_results),
            "stage6_result": result.to_dict() if result is not None else None,
        })
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
