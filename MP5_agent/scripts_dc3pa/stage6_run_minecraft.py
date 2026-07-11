#!/usr/bin/env python3
"""Stage-6 Minecraft entry point.

This file keeps MineDojo and the legacy MP5 imports lazy so ``--help`` and offline
checks work without the Minecraft stack. Real runs still require the repository's
normal MineDojo/JDK/model setup.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.integration import (  # noqa: E402
    Stage6RuntimeConfig,
    build_legacy_state_provider,
    build_stage6_runtime,
)
from dc3pa.memory import (  # noqa: E402
    HashingTextEncoder,
    MultimodalMemory,
    RGBHistogramEncoder,
)
from dc3pa.observability.trace import JsonlTraceWriter  # noqa: E402
from dc3pa.reliability import (  # noqa: E402
    AdaptiveTriggerConfig,
    DualChainConfig,
    HybridProbabilityConfig,
)


def _load_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Config must be a JSON object: {path}")
    return payload


def _load_plugin(spec: str, config: Mapping[str, Any]) -> Any:
    if ":" not in spec:
        raise ValueError("Plugin must use module:attribute syntax")
    module_name, attribute_name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    value = getattr(module, attribute_name)
    if isinstance(value, type):
        return value(**dict(config))
    if callable(value):
        return value(**dict(config))
    return value


def _build_encoders(args: argparse.Namespace):
    plugin_config = json.loads(args.encoder_config_json or "{}")
    if not isinstance(plugin_config, Mapping):
        raise ValueError("--encoder-config-json must decode to an object")
    image_encoder = None
    text_encoder = None
    if args.image_encoder_factory:
        image_encoder = _load_plugin(
            args.image_encoder_factory,
            plugin_config.get("image", {}) if isinstance(plugin_config.get("image", {}), Mapping) else {},
        )
    if args.text_encoder_factory:
        text_encoder = _load_plugin(
            args.text_encoder_factory,
            plugin_config.get("text", {}) if isinstance(plugin_config.get("text", {}), Mapping) else {},
        )
    if args.development_encoders:
        if image_encoder is not None or text_encoder is not None:
            raise ValueError(
                "Do not combine --development-encoders with explicit encoder plugins"
            )
        image_encoder = RGBHistogramEncoder()
        text_encoder = HashingTextEncoder()
        print(
            "WARNING: development histogram/hash encoders are active; "
            "this is not a paper-grade MineCLIP run.",
            file=sys.stderr,
        )
    if args.require_environment_score and (
        image_encoder is None or text_encoder is None
    ):
        raise ValueError(
            "--require-environment-score needs both image and text encoder plugins"
        )
    if image_encoder is None and text_encoder is None and args.mode == "dc3pa":
        print(
            "WARNING: no environment encoders are configured; pE will be unavailable. "
            "Do not report this as a full paper configuration.",
            file=sys.stderr,
        )
    elif (image_encoder is None) != (text_encoder is None):
        print(
            "WARNING: only one environment encoder is configured; pE may be unavailable.",
            file=sys.stderr,
        )
    return image_encoder, text_encoder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Stage-6 DC3PA closed loop on the legacy MP5 environment"
    )
    parser.add_argument("--mode", choices=("mp5_legacy", "reasoning_only", "dc3pa"), default="dc3pa")
    parser.add_argument("--mllm_url", default="")
    parser.add_argument("--openai_key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--gpt_model_name", default=os.environ.get("GPT_MODEL_NAME", ""))
    parser.add_argument("--task", default=os.environ.get("TASK_FILE", ""))
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "dc3pa" / "configs" / "stage6_closed_loop.json",
    )
    parser.add_argument("--memory-root", type=Path, default=ROOT / "memory" / "dc3pa_stage6")
    parser.add_argument("--trace", type=Path, default=ROOT / "runs" / "stage6_trace.jsonl")
    parser.add_argument("--max-execution-attempts", type=int)
    parser.add_argument("--unresolved-plan-policy", choices=("block", "reasoning_only", "execute"))
    parser.add_argument("--planner-failure-policy", choices=("raise", "reasoning_only", "return_failure"))
    parser.add_argument("--image-encoder-factory", default="")
    parser.add_argument("--text-encoder-factory", default="")
    parser.add_argument("--encoder-config-json", default="{}")
    parser.add_argument("--development-encoders", action="store_true")
    parser.add_argument("--require-environment-score", action="store_true")
    parser.add_argument(
        "--allow-legacy-task-hacks",
        action="store_true",
        help="Keep task-name-specific legacy rules outside mp5_legacy mode.",
    )
    parser.add_argument("--disable-controller-recovery", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.openai_key:
        parser.error("openai_key is required, set --openai_key or OPENAI_API_KEY")
    if not args.gpt_model_name:
        parser.error("gpt_model_name is required, set --gpt_model_name or GPT_MODEL_NAME")
    if not args.task:
        parser.error("task is required, set --task or TASK_FILE")
    if args.mode != "mp5_legacy" and not args.allow_legacy_task_hacks:
        os.environ["DC3PA_LEGACY_TASK_HACKS"] = "0"
    if args.disable_controller_recovery:
        os.environ["DC3PA_CONTROLLER_LOW_LEVEL_RECOVERY"] = "0"

    payload = _load_json(args.config)
    runtime_config = Stage6RuntimeConfig.from_mapping(payload.get("runtime", {}))
    runtime_config = replace(runtime_config, mode=args.mode)
    if args.max_execution_attempts is not None:
        runtime_config = replace(
            runtime_config, max_execution_attempts=args.max_execution_attempts
        )
    if args.unresolved_plan_policy is not None:
        runtime_config = replace(
            runtime_config, unresolved_plan_policy=args.unresolved_plan_policy
        )
    if args.planner_failure_policy is not None:
        runtime_config = replace(
            runtime_config, planner_failure_policy=args.planner_failure_policy
        )
    runtime_config.validate()
    hybrid_config = HybridProbabilityConfig.from_mapping(
        payload.get("hybrid_probability", {})
    )
    dual_config = DualChainConfig.from_mapping(payload.get("dual_chain", {}))
    trigger_config = AdaptiveTriggerConfig.from_mapping(
        payload.get("adaptive_trigger", {})
    )
    image_encoder, text_encoder = _build_encoders(args)

    agent_dir = ROOT / "agent"
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))
    # These imports intentionally occur only after CLI validation.
    legacy_runner = importlib.import_module("run_agent")
    legacy_runner.args = SimpleNamespace(
        mllm_url=args.mllm_url,
        openai_key=args.openai_key,
        gpt_model_name=args.gpt_model_name,
        task=args.task,
        answer_method="active",
        answer_model="mllm",
    )
    evaluator = legacy_runner.Evaluator()
    evaluator.env.reset()
    evaluator.env.set_inventory([])
    initial_result = evaluator.env.step([0, 0, 0, 12, 6, 0, 0, 0])
    initial_observation = initial_result[0] if isinstance(initial_result, tuple) else initial_result

    disable_memory = os.environ.get("MP5_DISABLE_MEMORY", "").lower() in {
        "1", "true", "yes", "on"
    }
    memory = legacy_runner.Work_Memory(
        openai_key=args.openai_key,
        model_name=args.gpt_model_name,
        use_history_workflow=not disable_memory,
    )
    legacy_runner.share_memory(memory=memory, events=initial_observation)
    reflexion = legacy_runner.Reflexion(
        openai_key=args.openai_key, memory=memory, model_name=args.gpt_model_name
    )
    planner_instance = legacy_runner.Planner(
        openai_key=args.openai_key, memory=memory, model_name=args.gpt_model_name
    )
    controller = legacy_runner.Controller(memory=memory, checker=reflexion)
    state_provider = build_legacy_state_provider(
        env=evaluator.env,
        legacy_memory=memory,
        share_memory=lambda target, observation: legacy_runner.share_memory(
            memory=target, events=observation
        ),
        refresh_environment=args.mode != "mp5_legacy",
        initial_observation=initial_observation,
    )
    trace_writer = JsonlTraceWriter(args.trace)
    args.memory_root.mkdir(parents=True, exist_ok=True)
    if args.mode == "mp5_legacy":
        runtime_config = replace(runtime_config, record_multimodal_memory=False)

    with MultimodalMemory(
        args.memory_root,
        image_encoder=image_encoder,
        text_encoder=text_encoder,
    ) as multimodal_memory:
        bundle = build_stage6_runtime(
            env=evaluator.env,
            runtime_config=runtime_config,
            legacy_planner=planner_instance,
            legacy_controller=controller,
            legacy_memory=memory,
            state_provider=state_provider,
            multimodal_memory=multimodal_memory,
            chat_model=getattr(memory, "llm", None),
            legacy_reflexion=reflexion,
            fixed_workflow_provider=getattr(evaluator, "_fixed_workflow_for_task", None),
            hybrid_config=hybrid_config,
            dual_chain_config=dual_config,
            trigger_config=trigger_config,
            trace_writer=trace_writer,
        )
        tasks = json.loads(Path(args.task).read_text(encoding="utf-8"))
        if isinstance(tasks, Mapping):
            task_list = [tasks]
        elif isinstance(tasks, list):
            task_list = tasks
        else:
            raise ValueError("Task file must contain an object or list")
        underground = False
        all_succeeded = True
        for task_information in task_list[::-1]:
            if not isinstance(task_information, Mapping):
                raise ValueError("Every task entry must be an object")
            result = bundle.runtime.run_task(task_information, underground=underground)
            underground = result.final_underground
            print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
            if not result.success:
                all_succeeded = False
                break
    return 0 if all_succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
