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
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
MP5_ROOT = ROOT / "MP5_agent"
for candidate in (ROOT, MP5_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from dc3pa_stage_a.inventory_write_logger import InventoryWriteLogger
from dc3pa_stage_a.paper_config import PaperRunConfig, load


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


def _stage6_payload(config: PaperRunConfig, snapshot_manifest: Path) -> Mapping[str, Any]:
    if not snapshot_manifest.is_file():
        raise FileNotFoundError(snapshot_manifest)
    return {
        "runtime": {
            "mode": config.runtime_mode,
            "max_execution_attempts": config.max_execution_attempts,
            "unresolved_plan_policy": "block",
            "planner_failure_policy": "reasoning_only",
            "controller_exception_policy": "return_failure",
            "goal_check_exception_policy": "return_failure",
            "memory_failure_policy": "trace",
            "require_goal_check": True,
            "record_legacy_workflow_memory": config.record_legacy_workflow_memory,
            "record_multimodal_memory": config.record_multimodal_memory,
            "capture_initial_scene": True,
            "capture_final_scene": True,
            "memory_mode": config.memory_mode,
            "telemetry_enabled": True,
            "memory_snapshot_manifest": str(snapshot_manifest.resolve()),
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


def _append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True, ensure_ascii=False) + "\n")


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
    if args.snapshot_manifest is None:
        raise ValueError("--snapshot-manifest is required for evaluate_readonly execution")
    if not args.openai_key or not args.gpt_model_name:
        raise ValueError("openai key and model name are required for execution")

    stage6_config = run_root / "stage6_runtime_config.json"
    stage6_config.write_text(json.dumps(_stage6_payload(config, args.snapshot_manifest), indent=2) + "\n", encoding="utf-8")
    os.environ["DC3PA_WORLD_SEED"] = str(args.seed)
    os.environ["DC3PA_SIM_SEED"] = str(args.seed)

    import minedojo
    from scripts_dc3pa import stage6_run_minecraft

    writes = run_root / "inventory_writes.jsonl"
    episodes = run_root / "episodes.jsonl"
    trace = run_root / "stage6_trace.jsonl"
    memory_root = args.memory_root or (run_root / "memory")
    logger: InventoryWriteLogger | None = None
    original_make = minedojo.make

    def traced_make(*make_args: Any, **make_kwargs: Any):
        nonlocal logger
        env = original_make(*make_args, **make_kwargs)
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
        return env

    minedojo.make = traced_make
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
        if logger is not None:
            logger.uninstall()
        _append_jsonl(episodes, {
            "run_id": args.run_id, "task": task_name, "tier": args.tier,
            "seed": args.seed, "runtime_mode": config.runtime_mode,
            "memory_mode": config.memory_mode, "traversal": args.traversal,
            "success": return_code == 0, "exit_code": return_code,
            "config_hash": config.config_hash(), "error": error,
        })
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
