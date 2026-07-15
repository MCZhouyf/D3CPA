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
from dc3pa.experiments.binding import load_binding  # noqa: E402
from dc3pa.experiments.blueprint import load_blueprint  # noqa: E402
from dc3pa.experiments.launcher_validation import (  # noqa: E402
    validate_real_experiment_launch,
)
from dc3pa.experiments.phase_state import load_state  # noqa: E402
from dc3pa.experiments.dry_run import (  # noqa: E402
    load_campaign,
    mark_dry_run_output_root,
    receipt_from_stage6_result,
    save_receipt,
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
from dc3pa.providers import (  # noqa: E402
    OpenAIResponsesChatAdapter,
    OpenAIResponsesModelProfile,
    ResponseUsage,
)
from dc3pa.reliability import (  # noqa: E402
    AdaptiveTriggerConfig,
    DualChainConfig,
    HybridProbabilityConfig,
)


class TracedChatModel:
    """Trace LLM request counts without recording prompts, responses, or credentials."""

    def __init__(
        self,
        model: Any,
        trace_writer: JsonlTraceWriter,
        purpose: str,
        *,
        include_error_detail: bool = True,
    ):
        self._model = model
        self._trace_writer = trace_writer
        self._purpose = purpose
        self._include_error_detail = include_error_detail

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
            payload = {
                "purpose": self._purpose,
                "method": method_name,
                "actual_method": actual_method_name,
                "error_type": type(exc).__name__,
            }
            if self._include_error_detail:
                payload["error"] = str(exc)
            self._trace_writer.write("llm_call_failed", payload)
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


def _parse_key_values(values: list[str], label: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{label} must use KEY=VALUE")
        key, item = value.split("=", 1)
        if not key.strip() or not item.strip():
            raise ValueError(f"{label} key/value cannot be empty")
        parsed[key.strip()] = item.strip()
    return parsed


def _load_task_list(task_path: str | Path) -> list[Mapping[str, Any]]:
    tasks = json.loads(Path(task_path).read_text(encoding="utf-8"))
    if isinstance(tasks, Mapping):
        return [tasks]
    if isinstance(tasks, list):
        if not all(isinstance(item, Mapping) for item in tasks):
            raise ValueError("Every task entry must be an object")
        return tasks
    raise ValueError("Task file must contain an object or list")


def _resolve_model_profile(
    cli_value: str, payload: Mapping[str, Any]
) -> Optional[OpenAIResponsesModelProfile]:
    configured = cli_value or payload.get("model_profile", "legacy")
    if isinstance(configured, Mapping):
        configured = configured.get("name", "")
    name = str(configured).strip() or "legacy"
    if name == "legacy":
        return None
    if name != "gpt51_reference":
        raise ValueError(f"Unknown model profile {name!r}")
    return OpenAIResponsesModelProfile().with_id()


def _usage_observer(
    trace_writer: JsonlTraceWriter,
    profile: OpenAIResponsesModelProfile,
    purpose: str,
):
    call_count = 0

    def observe(usage: ResponseUsage) -> None:
        nonlocal call_count
        call_count += 1
        trace_writer.write(
            "model_profile_usage",
            {
                "profile_id": profile.profile_id,
                "model": profile.model,
                "reasoning_effort": profile.reasoning_effort,
                "purpose": purpose,
                "call_count": call_count,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "reasoning_tokens": usage.reasoning_tokens,
                "total_tokens": usage.total_tokens,
            },
        )

    return observe


def _profile_chat_model(
    profile: OpenAIResponsesModelProfile,
    purpose: str,
    trace_writer: JsonlTraceWriter,
) -> TracedChatModel:
    adapter = OpenAIResponsesChatAdapter(
        profile=profile,
        purpose=purpose,
        usage_observer=_usage_observer(trace_writer, profile, purpose),
    )
    return TracedChatModel(
        adapter,
        trace_writer,
        purpose,
        include_error_detail=False,
    )


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
    parser.add_argument(
        "--model-profile",
        choices=("legacy", "gpt51_reference"),
        default="",
        help="Explicit chat provider profile; legacy remains the default.",
    )
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
    parser.add_argument("--real-experiment-blueprint", type=Path)
    parser.add_argument("--real-experiment-binding", type=Path)
    parser.add_argument("--real-experiment-phase-state", type=Path)
    parser.add_argument("--real-experiment-phase", default="")
    parser.add_argument("--real-experiment-task", default="")
    parser.add_argument("--real-experiment-seed", default="")
    parser.add_argument("--real-experiment-run-manifest-id", action="append", default=[])
    parser.add_argument("--dry-run-campaign", type=Path)
    parser.add_argument("--dry-run-entry-id", default="")
    parser.add_argument("--dry-run-output-root", type=Path)
    parser.add_argument("--dry-run-receipt", type=Path)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.openai_key:
        parser.error("openai_key is required, set --openai_key or OPENAI_API_KEY")
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
    try:
        model_profile = _resolve_model_profile(args.model_profile, payload)
    except ValueError as exc:
        parser.error(str(exc))
    if model_profile is None:
        if not args.gpt_model_name:
            parser.error("gpt_model_name is required, set --gpt_model_name or GPT_MODEL_NAME")
    else:
        if not os.environ.get(model_profile.api_key_environment_variable, ""):
            parser.error(
                "gpt51_reference requires OPENAI_API_KEY in the environment"
            )
        args.gpt_model_name = model_profile.model
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
    dry_run_enabled = any(
        (
            args.dry_run_campaign,
            args.dry_run_entry_id,
            args.dry_run_output_root,
            args.dry_run_receipt,
        )
    )
    if dry_run_enabled:
        missing = [
            name
            for name, value in (
                ("--dry-run-campaign", args.dry_run_campaign),
                ("--dry-run-entry-id", args.dry_run_entry_id),
                ("--dry-run-output-root", args.dry_run_output_root),
                ("--dry-run-receipt", args.dry_run_receipt),
                ("--real-experiment-blueprint", args.real_experiment_blueprint),
            )
            if not value
        ]
        if missing:
            parser.error("dry-run receipt mode requires " + ", ".join(missing))
        runtime_config = replace(
            runtime_config,
            memory_mode=MemoryMode.DISABLED.value,
            record_legacy_workflow_memory=False,
            record_multimodal_memory=False,
            acquisition_log_dir="",
        )
        os.environ["MP5_DISABLE_MEMORY"] = "1"
    runtime_config.validate()
    hybrid_config = HybridProbabilityConfig.from_mapping(
        payload.get("hybrid_probability", {})
    )
    dual_config = DualChainConfig.from_mapping(payload.get("dual_chain", {}))
    trigger_config = AdaptiveTriggerConfig.from_mapping(
        payload.get("adaptive_trigger", {})
    )
    real_experiment_trace_payload = None
    dry_run_campaign = None
    dry_run_entry = None
    if args.real_experiment_blueprint:
        if dry_run_enabled:
            dry_run_campaign = load_campaign(args.dry_run_campaign)
            matching = [
                entry
                for entry in dry_run_campaign.entries
                if entry.entry_id == args.dry_run_entry_id
            ]
            if not matching:
                parser.error("--dry-run-entry-id is not in the campaign")
            dry_run_entry = matching[0]
            if runtime_config.max_execution_attempts > dry_run_entry.maximum_replans + 1:
                parser.error("max_execution_attempts exceeds dry-run entry budget")
            task_list = _load_task_list(args.task)
            if len(task_list) != 1:
                parser.error("dry-run receipt mode requires exactly one task entry")
            requested_task = str(task_list[0].get("task", "")).strip()
            if requested_task != dry_run_entry.task:
                parser.error(
                    f"task file contains {requested_task!r}, "
                    f"expected dry-run task {dry_run_entry.task!r}"
                )
            mark_dry_run_output_root(
                args.dry_run_output_root,
                campaign_id=dry_run_campaign.campaign_id,
                entry_id=dry_run_entry.entry_id,
            )
            args.real_experiment_phase = "dry_run_completed"
            args.real_experiment_task = dry_run_entry.task
            args.real_experiment_seed = dry_run_entry.seed
        else:
            missing = [
                name
                for name, value in (
                    ("--real-experiment-phase", args.real_experiment_phase),
                    ("--real-experiment-task", args.real_experiment_task),
                    ("--real-experiment-seed", args.real_experiment_seed),
                )
                if not str(value).strip()
            ]
            if missing:
                parser.error(
                    "--real-experiment-blueprint requires " + ", ".join(missing)
                )
        real_experiment_trace_payload = validate_real_experiment_launch(
            blueprint=load_blueprint(args.real_experiment_blueprint),
            binding=load_binding(args.real_experiment_binding)
            if args.real_experiment_binding
            else None,
            phase_state=load_state(args.real_experiment_phase_state)
            if args.real_experiment_phase_state
            else None,
            phase=args.real_experiment_phase,
            task=args.real_experiment_task,
            seed=args.real_experiment_seed,
            max_execution_attempts=runtime_config.max_execution_attempts,
            run_manifest_ids=_parse_key_values(
                args.real_experiment_run_manifest_id,
                "--real-experiment-run-manifest-id",
            ),
        ).to_trace_payload()

    requested_environment_seed = None
    if model_profile is not None and args.real_experiment_blueprint:
        try:
            requested_environment_seed = int(args.real_experiment_seed)
        except (TypeError, ValueError):
            parser.error("GPT-5.1 reference runs require a positive integer experiment seed")
        if requested_environment_seed <= 0:
            parser.error("GPT-5.1 reference runs require a positive integer experiment seed")
        os.environ["DC3PA_WORLD_SEED"] = str(requested_environment_seed)
        os.environ["DC3PA_SIM_SEED"] = str(requested_environment_seed)

    def write_dry_run_receipt(result=None, exception: Optional[BaseException] = None) -> None:
        if not dry_run_enabled or dry_run_campaign is None or dry_run_entry is None:
            return
        receipt = receipt_from_stage6_result(
            campaign=dry_run_campaign,
            entry_id=dry_run_entry.entry_id,
            result=result,
            output_root=args.dry_run_output_root,
            process_exit_code=0 if exception is None else 1,
            launch_validation_passed=real_experiment_trace_payload is not None,
            formal_memory_used=False,
            exception=exception,
        )
        save_receipt(args.dry_run_receipt, receipt)

    try:
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
            if real_experiment_trace_payload is not None:
                trace_writer.write(
                    "real_experiment_launch_validated",
                    real_experiment_trace_payload,
                )
            if requested_environment_seed is not None:
                effective_world_seed = getattr(evaluator, "effective_world_seed", None)
                effective_simulator_seed = getattr(
                    evaluator, "effective_simulator_seed", None
                )
                if (
                    effective_world_seed != requested_environment_seed
                    or effective_simulator_seed != requested_environment_seed
                ):
                    raise RuntimeError(
                        "MineDojo effective seed does not match the approved seed"
                    )
                trace_writer.write(
                    "environment_seed_applied",
                    {
                        "requested_seed": requested_environment_seed,
                        "effective_world_seed": effective_world_seed,
                        "effective_simulator_seed": effective_simulator_seed,
                        "application_point": "minedojo.make",
                    },
                )
            if model_profile is not None:
                trace_writer.write(
                    "model_profile_activated",
                    {
                        "profile_id": model_profile.profile_id,
                        "model": model_profile.model,
                        "reasoning_effort": model_profile.reasoning_effort,
                    },
                )
                memory.llm = _profile_chat_model(
                    model_profile,
                    "dc3pa_confidence_and_evaluation",
                    trace_writer,
                )
                reflexion.llm = _profile_chat_model(
                    model_profile, "reflection", trace_writer
                )
                planner_instance.llm = _profile_chat_model(
                    model_profile, "planning", trace_writer
                )
            elif hasattr(memory, "llm"):
                memory.llm = TracedChatModel(
                    memory.llm, trace_writer, "dc3pa_confidence_and_evaluation"
                )
            if model_profile is None and hasattr(reflexion, "llm"):
                reflexion.llm = TracedChatModel(
                    reflexion.llm, trace_writer, "reflection"
                )
            if model_profile is None and hasattr(planner_instance, "llm"):
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
                task_list = _load_task_list(args.task)
                underground = False
                all_succeeded = True
                last_result = None
                for task_information in task_list[::-1]:
                    if not isinstance(task_information, Mapping):
                        raise ValueError("Every task entry must be an object")
                    result = bundle.runtime.run_task(task_information, underground=underground)
                    last_result = result
                    underground = result.final_underground
                    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
                    if not result.success:
                        all_succeeded = False
                        break
                write_dry_run_receipt(last_result)
    except Exception as exc:
        write_dry_run_receipt(None, exc)
        raise
    if dry_run_enabled:
        return 0
    return 0 if all_succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
