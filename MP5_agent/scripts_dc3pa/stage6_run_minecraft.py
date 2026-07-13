#!/usr/bin/env python3
"""Stage-6 Minecraft entry point.

This file keeps MineDojo and the legacy MP5 imports lazy so ``--help`` and offline
checks work without the Minecraft stack. Real runs still require the repository's
normal MineDojo/JDK/model setup.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import os
import shutil
import subprocess
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
from dc3pa.memory.modes import MemoryMode  # noqa: E402
from dc3pa.memory.snapshot import (  # noqa: E402
    MemorySnapshotManifest,
    resolve_snapshot_database,
)
from dc3pa.observability.trace import JsonlTraceWriter  # noqa: E402
from dc3pa.reliability import (  # noqa: E402
    AdaptiveTriggerConfig,
    DualChainConfig,
    HybridProbabilityConfig,
)


class TracedChatModel:
    """Trace LLM request counts without recording prompts, responses, or credentials."""

    def __init__(self, model: Any, trace_writer: JsonlTraceWriter, purpose: str):
        self._model = model
        self._trace_writer = trace_writer
        self._purpose = purpose

    def _resolve_method(self, method_name: str) -> tuple[str, Any]:
        if hasattr(self._model, method_name):
            return method_name, getattr(self._model, method_name)
        if method_name == "invoke" and hasattr(self._model, "predict"):
            return "predict", getattr(self._model, "predict")
        if method_name in {"invoke", "predict"} and callable(self._model):
            return "__call__", self._model
        raise AttributeError(
            f"{type(self._model).__name__!r} object has no attribute {method_name!r}"
        )

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        actual_method_name, method = self._resolve_method(method_name)
        if actual_method_name == "__call__" and args and isinstance(args[0], str):
            from langchain.schema import HumanMessage

            args = ([HumanMessage(content=args[0])], *args[1:])
        self._trace_writer.write(
            "llm_call_started",
            {
                "purpose": self._purpose,
                "method": method_name,
                "actual_method": actual_method_name,
            },
        )
        try:
            result = method(*args, **kwargs)
        except Exception as exc:
            self._trace_writer.write(
                "llm_call_failed",
                {
                    "purpose": self._purpose,
                    "method": method_name,
                    "actual_method": actual_method_name,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise
        self._trace_writer.write(
            "llm_call_completed",
            {
                "purpose": self._purpose,
                "method": method_name,
                "actual_method": actual_method_name,
            },
        )
        return result

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("__call__", *args, **kwargs)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("invoke", *args, **kwargs)

    def predict(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("predict", *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model, name)


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


@contextlib.contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


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


def _validate_display_available() -> None:
    display = os.environ.get("DISPLAY", "").strip()
    if not display:
        raise RuntimeError(
            "DISPLAY is not set. Start a VNC/X server or run with "
            "xvfb-run -a -s '-screen 0 1920x1080x24'."
        )
    xdpyinfo = shutil.which("xdpyinfo")
    if xdpyinfo is None:
        return
    result = subprocess.run(
        [xdpyinfo],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"DISPLAY={display!r} is not reachable. Start the matching VNC/X "
            "server or run with xvfb-run -a -s '-screen 0 1920x1080x24'."
        )


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

    args.config = args.config.resolve()
    args.task = str(Path(args.task).resolve())
    args.memory_root = args.memory_root.resolve()
    args.trace = args.trace.resolve()

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
    _validate_display_available()

    agent_dir = ROOT / "agent"
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))
    with _working_directory(agent_dir):
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
        trace_writer = JsonlTraceWriter(args.trace)
        if hasattr(memory, "llm"):
            memory.llm = TracedChatModel(
                memory.llm, trace_writer, "dc3pa_confidence_and_evaluation"
            )
        if hasattr(reflexion, "llm"):
            reflexion.llm = TracedChatModel(
                reflexion.llm, trace_writer, "reflection"
            )
        if hasattr(planner_instance, "llm"):
            planner_instance.llm = TracedChatModel(
                planner_instance.llm, trace_writer, "planning"
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
        if args.mode == "mp5_legacy":
            runtime_config = replace(runtime_config, record_multimodal_memory=False)

        memory_mode = MemoryMode.parse(runtime_config.memory_mode)
        if memory_mode.requires_frozen_snapshot:
            if not args.memory_root.is_dir():
                raise FileNotFoundError(
                    f"readonly memory root does not exist: {args.memory_root}"
                )
            manifest = MemorySnapshotManifest.from_json(
                runtime_config.memory_snapshot_manifest
            )
            resolve_snapshot_database(manifest, memory_root=args.memory_root)
        elif memory_mode.memory_enabled:
            args.memory_root.mkdir(parents=True, exist_ok=True)

        memory_context = (
            contextlib.nullcontext(None)
            if not memory_mode.memory_enabled
            else MultimodalMemory(
                args.memory_root,
                image_encoder=image_encoder,
                text_encoder=text_encoder,
                readonly=memory_mode.requires_frozen_snapshot,
            )
        )
        with memory_context as multimodal_memory:
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
