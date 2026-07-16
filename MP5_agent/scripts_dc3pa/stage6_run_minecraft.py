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
import time
from dataclasses import replace
from datetime import datetime, timezone
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
    dry_run_marker_for,
    load_campaign,
    mark_dry_run_output_root,
    receipt_from_stage6_result,
    save_receipt,
)
from dc3pa.experiments.log_fallback import (  # noqa: E402
    DiagnosticLogFallbackSession,
    LogFallbackPolicy,
    load_log_fallback_policy,
    receipt_metrics_from_events,
)
from dc3pa.experiments.bootstrap_data_guard import (  # noqa: E402
    assert_bootstrap_snapshot_binding,
    load_bootstrap_data_binding,
)
from dc3pa.experiments.formal_bootstrap_amendment import (  # noqa: E402
    load_formal_bootstrap_amendment,
)
from dc3pa.experiments.formal_log_bootstrap import (  # noqa: E402
    FormalBootstrapRunReceipt,
    FormalLogBootstrapSession,
    load_formal_log_bootstrap_policy,
    mark_formal_bootstrap_output_root,
    validate_events_for_receipt,
)
from dc3pa.experiments.acquisition_binding import (  # noqa: E402
    AcquisitionRecordProvenance,
    finalize_staged_acquisition,
)
from dc3pa.experiments.formal_acquisition_execution import (  # noqa: E402
    FormalAcquisitionCampaign,
    TechnicalRetryPolicy,
    deterministic_attempt_id,
    load_ledger,
)
from dc3pa.experiments.paired_dry_run import (  # noqa: E402
    load_paired_protocol,
)
from dc3pa.experiments.provider_model_alias import (  # noqa: E402
    load_provider_model_alias_policy,
)
from dc3pa.memory import (  # noqa: E402
    HashingTextEncoder,
    MultimodalMemory,
    RGBHistogramEncoder,
)
from dc3pa.memory.modes import MemoryMode  # noqa: E402
from dc3pa.memory.acquisition import AcquisitionStore  # noqa: E402
from dc3pa.memory.acquisition_scene_only import (  # noqa: E402
    SceneOnlyDependencyExtractor,
)
from dc3pa.memory.snapshot import (  # noqa: E402
    MemorySnapshotManifest,
    resolve_snapshot_database,
)
from dc3pa.observability.trace import JsonlTraceWriter  # noqa: E402
from dc3pa.providers import (  # noqa: E402
    OpenAIResponsesChatAdapter,
    OpenAIResponsesModelProfile,
    ResponseUsage,
    SafeResponseMetadata,
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
        metadata_observer=None,
        requested_model: str = "",
    ):
        self._model = model
        self._trace_writer = trace_writer
        self._purpose = purpose
        self._include_error_detail = include_error_detail
        self._metadata_observer = metadata_observer
        self._requested_model = requested_model

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
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()
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
        if self._metadata_observer is not None:
            metadata = _legacy_response_metadata(
                result,
                requested_model=self._requested_model,
                purpose=self._purpose,
                request_started_at=started_at,
                request_duration_seconds=time.monotonic() - started,
            )
            if metadata is not None:
                self._metadata_observer(metadata)
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


def _legacy_response_metadata(
    result: Any,
    *,
    requested_model: str,
    purpose: str,
    request_started_at: str,
    request_duration_seconds: float,
) -> Optional[SafeResponseMetadata]:
    """Extract only safe identity/usage fields from a LangChain AIMessage."""
    response = getattr(result, "response_metadata", None)
    if not isinstance(response, Mapping):
        return None
    returned_model = str(
        response.get("model_name", response.get("model", ""))
    ).strip()
    if not returned_model:
        return None
    raw_usage = response.get("token_usage", {})
    if not isinstance(raw_usage, Mapping):
        raw_usage = {}
    usage = ResponseUsage(
        input_tokens=int(
            raw_usage.get("prompt_tokens", raw_usage.get("input_tokens", 0)) or 0
        ),
        output_tokens=int(
            raw_usage.get(
                "completion_tokens", raw_usage.get("output_tokens", 0)
            )
            or 0
        ),
        total_tokens=int(raw_usage.get("total_tokens", 0) or 0),
    )
    return SafeResponseMetadata(
        requested_model=requested_model,
        returned_model=returned_model,
        profile_id="legacy",
        reasoning_effort="none",
        purpose=purpose,
        request_started_at=request_started_at,
        request_duration_seconds=request_duration_seconds,
        response_id_sha256="",
        usage=usage,
    )


def _configure_real_experiment_seed(
    *, real_experiment_blueprint: Any, raw_seed: Any
) -> Optional[int]:
    if real_experiment_blueprint is None:
        return None
    try:
        requested_seed = int(raw_seed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Real experiment runs require a positive integer experiment seed"
        ) from exc
    if requested_seed <= 0:
        raise ValueError(
            "Real experiment runs require a positive integer experiment seed"
        )
    os.environ["DC3PA_WORLD_SEED"] = str(requested_seed)
    os.environ["DC3PA_SIM_SEED"] = str(requested_seed)
    return requested_seed


def _formal_acquisition_provenance(
    *, campaign, entry: Mapping[str, Any], attempt_id: str, receipt
) -> AcquisitionRecordProvenance:
    def value(name: str):
        if isinstance(receipt, Mapping):
            return receipt[name]
        return getattr(receipt, name)

    return AcquisitionRecordProvenance(
        campaign_id=campaign.campaign_id,
        schedule_id=campaign.schedule_id,
        formal_authorization_id=campaign.formal_authorization_id,
        execution_tooling_binding_id=campaign.execution_tooling_binding_id,
        episode_index=int(entry["episode_index"]),
        run_id=attempt_id,
        attempt_id=attempt_id,
        stage6_receipt_id=str(value("receipt_id")),
        source_commit=campaign.source_commit,
        blueprint_id=campaign.blueprint_id,
        bootstrap_policy_id=campaign.bootstrap_policy_id,
        bootstrap_amendment_id=campaign.bootstrap_amendment_id,
        bootstrap_data_binding_id=campaign.bootstrap_data_binding_id,
        prompt_hash_bundle_id=campaign.prompt_hash_bundle_id,
        model_profile_id=campaign.model_profile_id,
        requested_model=str(value("requested_model")),
        returned_model_identities=tuple(value("returned_model_identities")),
        task=str(entry["task"]),
        seed=str(entry["seed"]),
        difficulty=str(entry["difficulty"]),
        method_id=str(entry["method_id"]),
        bootstrap_event_ids=tuple(value("event_ids")),
        injected_log_count=int(value("total_injected_logs")),
        naturally_collected_log_count=int(value("total_naturally_collected_logs")),
        natural_completion=bool(value("natural_completion")),
        bootstrap_assisted_completion=bool(value("bootstrap_assisted_completion")),
        planner_calls=int(value("planner_calls")),
        reflection_calls=int(value("reflection_calls")),
        evaluation_chain_calls=int(value("evaluation_chain_calls")),
        trace_sha256=str(value("trace_sha256")),
        taskset_amendment_id=campaign.taskset_amendment_id,
    ).with_id()


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


def _runtime_target_matches_catalog_task(
    *, runtime_target: str, catalog_task: str
) -> bool:
    """Match an agent target to its approved action-prefixed catalog label."""
    target = " ".join(runtime_target.strip().lower().split())
    label = " ".join(catalog_task.strip().lower().split())
    if target == label:
        return True
    action_and_target = label.split(" ", 1)
    return (
        len(action_and_target) == 2
        and action_and_target[0] in {"craft", "mine", "obtain", "smelt"}
        and action_and_target[1] == target
    )


def _expected_reasoning_only_provider_calls(
    *, task_count: int, result: Any
) -> int:
    """Derive calls from the frozen single-attempt reasoning-only protocol."""
    if task_count < 0:
        raise ValueError("task_count cannot be negative")
    final_failure_reflection = int(
        result is not None and not bool(getattr(result, "success", False))
    )
    return task_count + final_failure_reflection


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
    metadata_observer=None,
    *,
    verify_returned_model: bool = True,
) -> TracedChatModel:
    adapter = OpenAIResponsesChatAdapter(
        profile=profile,
        purpose=purpose,
        usage_observer=_usage_observer(trace_writer, profile, purpose),
        metadata_observer=metadata_observer,
        verify_returned_model=verify_returned_model,
    )
    return TracedChatModel(
        adapter,
        trace_writer,
        purpose,
        include_error_detail=False,
    )


def _returned_model_validation(
    *, provider_alias_policy, formal_bootstrap_enabled: bool
) -> tuple[str, bool]:
    if provider_alias_policy is not None:
        return "approved_alias_policy", False
    if formal_bootstrap_enabled:
        return "formal_record_only_policy", False
    return "strict_identity_match", True


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
    parser.add_argument("--dry-run-max-explore-steps", type=int, default=16)
    parser.add_argument(
        "--enable-diagnostic-log-fallback", action="store_true"
    )
    parser.add_argument("--provider-model-alias-policy", type=Path)
    parser.add_argument("--provider-model-alias-approval", type=Path)
    parser.add_argument("--log-fallback-policy", type=Path)
    parser.add_argument("--paired-dry-run-protocol", type=Path)
    parser.add_argument("--formal-log-bootstrap-policy", type=Path)
    parser.add_argument("--formal-bootstrap-amendment", type=Path)
    parser.add_argument("--formal-bootstrap-data-binding", type=Path)
    parser.add_argument("--formal-bootstrap-scope", default="")
    parser.add_argument("--formal-bootstrap-method-id", default="")
    parser.add_argument("--formal-bootstrap-output-root", type=Path)
    parser.add_argument("--formal-bootstrap-receipt", type=Path)
    parser.add_argument("--formal-acquisition-campaign", type=Path)
    parser.add_argument("--formal-acquisition-entry", type=Path)
    parser.add_argument("--formal-acquisition-ledger", type=Path)
    parser.add_argument("--formal-acquisition-retry-policy", type=Path)
    parser.add_argument("--formal-acquisition-attempt-index", type=int)
    parser.add_argument("--formal-acquisition-root", type=Path)
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
    fallback_arguments_present = any(
        (
            args.enable_diagnostic_log_fallback,
            args.log_fallback_policy,
            args.paired_dry_run_protocol,
        )
    )
    formal_bootstrap_arguments = (
        args.formal_log_bootstrap_policy,
        args.formal_bootstrap_amendment,
        args.formal_bootstrap_data_binding,
        args.formal_bootstrap_scope,
        args.formal_bootstrap_method_id,
        args.formal_bootstrap_output_root,
        args.formal_bootstrap_receipt,
    )
    formal_bootstrap_enabled = any(formal_bootstrap_arguments)
    if formal_bootstrap_enabled and not all(formal_bootstrap_arguments):
        parser.error("formal log bootstrap requires all formal bootstrap arguments")
    if formal_bootstrap_enabled and fallback_arguments_present:
        parser.error("diagnostic fallback and formal bootstrap are mutually exclusive")
    if formal_bootstrap_enabled and not args.real_experiment_blueprint:
        parser.error("formal log bootstrap requires a real experiment Blueprint")
    formal_acquisition_arguments = (
        args.formal_acquisition_campaign,
        args.formal_acquisition_entry,
        args.formal_acquisition_ledger,
        args.formal_acquisition_retry_policy,
        args.formal_acquisition_attempt_index,
        args.formal_acquisition_root,
    )
    formal_acquisition_enabled = any(
        value is not None for value in formal_acquisition_arguments
    )
    if formal_acquisition_enabled and not all(
        value is not None for value in formal_acquisition_arguments
    ):
        parser.error("formal acquisition requires all formal acquisition arguments")
    if formal_acquisition_enabled and not formal_bootstrap_enabled:
        parser.error("formal acquisition requires formal Log Bootstrap")
    if formal_acquisition_enabled and not args.real_experiment_phase_state:
        parser.error("formal acquisition requires a frozen phase-state ledger")
    if formal_acquisition_enabled and args.mode != "reasoning_only":
        parser.error("formal acquisition requires single-chain reasoning_only mode")
    if formal_acquisition_enabled and (
        args.formal_bootstrap_scope != "formal_acquisition"
        or args.formal_bootstrap_method_id
        != "single_chain_reactive_acquisition"
    ):
        parser.error("formal acquisition scope/method is incorrect")
    if fallback_arguments_present and not dry_run_enabled:
        parser.error("diagnostic log fallback is allowed only in dry-run receipt mode")
    if not args.enable_diagnostic_log_fallback and (
        args.log_fallback_policy or args.paired_dry_run_protocol
    ):
        parser.error("fallback policy/protocol require --enable-diagnostic-log-fallback")
    alias_arguments_present = any(
        (
            args.provider_model_alias_policy,
            args.provider_model_alias_approval,
        )
    )
    if alias_arguments_present and not all(
        (
            args.provider_model_alias_policy,
            args.provider_model_alias_approval,
        )
    ):
        parser.error(
            "provider model aliasing requires --provider-model-alias-policy "
            "and --provider-model-alias-approval"
        )
    if alias_arguments_present and not args.real_experiment_blueprint:
        parser.error(
            "provider model aliasing requires a bound real experiment Blueprint"
        )
    if alias_arguments_present and model_profile is None:
        parser.error("provider model aliasing requires an explicit model profile")
    if args.enable_diagnostic_log_fallback:
        missing = [
            name
            for name, value in (
                ("--log-fallback-policy", args.log_fallback_policy),
                ("--paired-dry-run-protocol", args.paired_dry_run_protocol),
            )
            if not value
        ]
        if missing:
            parser.error("diagnostic log fallback requires " + ", ".join(missing))
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
            telemetry_enabled=True,
            record_legacy_workflow_memory=False,
            record_multimodal_memory=False,
            acquisition_log_dir="",
        )
        os.environ["MP5_DISABLE_MEMORY"] = "1"
        if args.dry_run_max_explore_steps <= 0:
            parser.error("--dry-run-max-explore-steps must be positive")
        os.environ["DC3PA_MAX_EXPLORE_STEPS"] = str(
            args.dry_run_max_explore_steps
        )
    runtime_config.validate()
    hybrid_config = HybridProbabilityConfig.from_mapping(
        payload.get("hybrid_probability", {})
    )
    dual_config = DualChainConfig.from_mapping(payload.get("dual_chain", {}))
    trigger_config = AdaptiveTriggerConfig.from_mapping(
        payload.get("adaptive_trigger", {})
    )
    real_experiment_trace_payload = None
    real_experiment_blueprint = None
    dry_run_campaign = None
    dry_run_entry = None
    dry_run_difficulty = ""
    expected_provider_call_count = 0
    provider_metadata = []
    provider_alias_policy = None
    effective_environment_seed = None
    environment_started = False
    fallback_policy = LogFallbackPolicy().with_id()
    fallback_session = None
    formal_bootstrap_policy = None
    formal_bootstrap_amendment = None
    formal_bootstrap_binding = None
    formal_bootstrap_session = None
    formal_acquisition_campaign = None
    formal_acquisition_entry = None
    formal_acquisition_attempt_id = ""
    formal_acquisition_staging_root = None
    if formal_acquisition_enabled:
        try:
            campaign_payload = _load_json(args.formal_acquisition_campaign)
            formal_acquisition_campaign = FormalAcquisitionCampaign(
                **campaign_payload
            )
            formal_acquisition_entry = _load_json(
                args.formal_acquisition_entry
            )
            retry_payload = _load_json(args.formal_acquisition_retry_policy)
            retry_payload["allowed_categories"] = tuple(
                retry_payload["allowed_categories"]
            )
            retry_payload["scientific_categories"] = tuple(
                retry_payload["scientific_categories"]
            )
            retry_policy = TechnicalRetryPolicy(**retry_payload)
            ledger = load_ledger(args.formal_acquisition_ledger)
            attempt_index = int(args.formal_acquisition_attempt_index)
            if formal_acquisition_campaign.retry_policy_id != retry_policy.policy_id:
                raise ValueError("campaign/retry-policy ID mismatch")
            if ledger.campaign_id != formal_acquisition_campaign.campaign_id:
                raise ValueError("campaign/ledger ID mismatch")
            if attempt_index != len(ledger.attempts):
                raise ValueError("formal attempt index is not next in the ledger")
            if ledger.resolved:
                raise ValueError("formal schedule entry is already resolved")
            if ledger.attempts:
                if ledger.attempts[-1].status != "technical_failure":
                    raise ValueError("only technical failures may be retried")
                if ledger.technical_retry_count >= retry_policy.maximum_technical_retries_per_entry:
                    raise ValueError("formal technical retry maximum exceeded")
            expected_assignment = (
                ledger.episode_index,
                ledger.group_id,
                ledger.task,
                str(ledger.seed),
            )
            actual_assignment = (
                int(formal_acquisition_entry["episode_index"]),
                str(formal_acquisition_entry["group_id"]),
                str(formal_acquisition_entry["task"]),
                str(formal_acquisition_entry["seed"]),
            )
            if actual_assignment != expected_assignment:
                raise ValueError("formal entry/ledger assignment mismatch")
            current_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT.parent,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if current_commit != formal_acquisition_campaign.source_commit:
                raise ValueError("current source commit/campaign mismatch")
            formal_acquisition_attempt_id = deterministic_attempt_id(
                formal_acquisition_campaign.campaign_id,
                ledger.episode_index,
                attempt_index,
            )
            formal_acquisition_staging_root = (
                args.formal_bootstrap_output_root
                / "staging_acquisition"
                / formal_acquisition_attempt_id
            ).resolve()
            args.formal_acquisition_root = args.formal_acquisition_root.resolve()
            runtime_config = replace(
                runtime_config,
                mode="reasoning_only",
                max_execution_attempts=4,
                memory_mode=MemoryMode.ACQUIRE.value,
                telemetry_enabled=True,
                record_legacy_workflow_memory=False,
                record_multimodal_memory=True,
                acquisition_log_dir=str(formal_acquisition_staging_root),
                calibration_log_dir="",
                model_confidence_collection="disabled",
            )
            os.environ["MP5_DISABLE_MEMORY"] = "1"
            expected_provider_call_count = 1
        except (KeyError, OSError, TypeError, ValueError) as exc:
            parser.error(str(exc))
    if args.real_experiment_blueprint:
        real_experiment_blueprint = load_blueprint(args.real_experiment_blueprint)
        if formal_bootstrap_enabled:
            try:
                formal_bootstrap_policy = load_formal_log_bootstrap_policy(
                    args.formal_log_bootstrap_policy
                )
                formal_bootstrap_amendment = load_formal_bootstrap_amendment(
                    args.formal_bootstrap_amendment
                )
                formal_bootstrap_binding = load_bootstrap_data_binding(
                    args.formal_bootstrap_data_binding
                )
                formal_bootstrap_policy.assert_scope(args.formal_bootstrap_scope)
                expected_bindings = {
                    "policy": (
                        formal_bootstrap_binding.bootstrap_policy_id,
                        formal_bootstrap_policy.policy_id,
                    ),
                    "amendment": (
                        formal_bootstrap_binding.bootstrap_amendment_id,
                        formal_bootstrap_amendment.amendment_id,
                    ),
                    "amendment policy": (
                        formal_bootstrap_amendment.formal_log_bootstrap_policy_id,
                        formal_bootstrap_policy.policy_id,
                    ),
                    "Blueprint": (
                        formal_bootstrap_binding.blueprint_id,
                        real_experiment_blueprint.blueprint_id,
                    ),
                    "scope": (
                        formal_bootstrap_binding.scope,
                        args.formal_bootstrap_scope,
                    ),
                    "method": (
                        formal_bootstrap_binding.method_id,
                        args.formal_bootstrap_method_id,
                    ),
                }
                mismatches = [
                    name for name, (actual, expected) in expected_bindings.items()
                    if actual != expected
                ]
                if mismatches:
                    raise ValueError(
                        "Formal bootstrap binding mismatch: " + ", ".join(mismatches)
                    )
                if formal_acquisition_campaign is not None:
                    campaign_bindings = {
                        "Blueprint": (
                            formal_acquisition_campaign.blueprint_id,
                            real_experiment_blueprint.blueprint_id,
                        ),
                        "policy": (
                            formal_acquisition_campaign.bootstrap_policy_id,
                            formal_bootstrap_policy.policy_id,
                        ),
                        "amendment": (
                            formal_acquisition_campaign.bootstrap_amendment_id,
                            formal_bootstrap_amendment.amendment_id,
                        ),
                        "data binding": (
                            formal_acquisition_campaign.bootstrap_data_binding_id,
                            formal_bootstrap_binding.binding_id,
                        ),
                        "data-binding source": (
                            formal_bootstrap_binding.source_commit,
                            formal_acquisition_campaign.source_commit,
                        ),
                        "data-binding tooling": (
                            formal_bootstrap_binding.execution_tooling_binding_id,
                            formal_acquisition_campaign.execution_tooling_binding_id,
                        ),
                        "data-binding authorization": (
                            formal_bootstrap_binding.parent_formal_authorization_id,
                            formal_acquisition_campaign.formal_authorization_id,
                        ),
                    }
                    bad_campaign_bindings = [
                        name
                        for name, (actual, expected) in campaign_bindings.items()
                        if actual != expected
                    ]
                    if bad_campaign_bindings:
                        raise ValueError(
                            "Formal acquisition campaign mismatch: "
                            + ", ".join(bad_campaign_bindings)
                        )
                mark_formal_bootstrap_output_root(
                    args.formal_bootstrap_output_root,
                    policy_id=formal_bootstrap_policy.policy_id,
                    amendment_id=formal_bootstrap_amendment.amendment_id,
                    blueprint_id=real_experiment_blueprint.blueprint_id,
                    scope=args.formal_bootstrap_scope,
                    method_id=args.formal_bootstrap_method_id,
                )
            except (OSError, TypeError, ValueError) as exc:
                parser.error(str(exc))
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
            if not _runtime_target_matches_catalog_task(
                runtime_target=requested_task,
                catalog_task=dry_run_entry.task,
            ):
                parser.error(
                    f"task file contains {requested_task!r}, "
                    f"expected dry-run task {dry_run_entry.task!r}"
                )
            assignments = [
                item for item in real_experiment_blueprint.development_assignments
                if item.group_id == dry_run_entry.group_id
                and item.task == dry_run_entry.task
                and str(item.seed) == str(dry_run_entry.seed)
            ]
            if len(assignments) != 1:
                parser.error("dry-run entry does not resolve to one Blueprint assignment")
            dry_run_difficulty = assignments[0].difficulty
            if formal_bootstrap_enabled and args.formal_bootstrap_scope != (
                "bootstrap_readiness_dry_run"
            ):
                parser.error(
                    "formal bootstrap dry runs require bootstrap_readiness_dry_run scope"
                )
            if model_profile is not None:
                if args.mode != "reasoning_only":
                    parser.error("formal GPT-5.1 dry runs must use reasoning_only")
                if runtime_config.max_execution_attempts != 1:
                    parser.error(
                        "formal GPT-5.1 dry-run provider calls are derived only "
                        "for one execution attempt"
                    )
                expected_provider_call_count = len(task_list)
            mark_dry_run_output_root(
                args.dry_run_output_root,
                campaign_id=dry_run_campaign.campaign_id,
                entry_id=dry_run_entry.entry_id,
            )
            if args.enable_diagnostic_log_fallback:
                try:
                    fallback_policy = load_log_fallback_policy(
                        args.log_fallback_policy
                    )
                    paired_protocol = load_paired_protocol(
                        args.paired_dry_run_protocol
                    )
                    marker_path = dry_run_marker_for(args.dry_run_output_root)
                    marker = (
                        _load_json(marker_path) if marker_path is not None else {}
                    )
                    fallback_policy.assert_activation_allowed(
                        scope="diagnostic_dry_run",
                        explicit_cli_enable=True,
                        dry_run_campaign_present=True,
                        dry_run_output_marker_present=bool(marker_path),
                    )
                    if paired_protocol.fallback_policy_id != fallback_policy.policy_id:
                        raise ValueError("paired protocol fallback policy ID mismatch")
                    if dry_run_campaign.campaign_id != paired_protocol.diagnostic_campaign_id:
                        raise ValueError("fallback requires the paired diagnostic campaign")
                    if marker.get("campaign_id") != dry_run_campaign.campaign_id:
                        raise ValueError("dry-run marker campaign ID mismatch")
                    if marker.get("entry_id") != dry_run_entry.entry_id:
                        raise ValueError("dry-run marker entry ID mismatch")
                    if paired_protocol.source_commit != real_experiment_blueprint.source_commit:
                        raise ValueError("paired protocol source commit mismatch")
                    fallback_session = DiagnosticLogFallbackSession(
                        policy=fallback_policy,
                        source_commit=paired_protocol.source_commit,
                        task=dry_run_entry.task,
                        seed=dry_run_entry.seed,
                    )
                except (OSError, TypeError, ValueError) as exc:
                    parser.error(str(exc))
            if alias_arguments_present:
                try:
                    provider_alias_policy = load_provider_model_alias_policy(
                        args.provider_model_alias_policy,
                        approval_record=args.provider_model_alias_approval,
                    )
                    alias_scope = (
                        "fallback_diagnostic"
                        if args.enable_diagnostic_log_fallback
                        else "natural_readiness"
                    )
                    provider_alias_policy.assert_activation_allowed(
                        scope=alias_scope,
                        requested_model=model_profile.model,
                    )
                except (OSError, TypeError, ValueError) as exc:
                    parser.error(str(exc))
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
            if formal_bootstrap_enabled:
                expected_scope = {
                    "experience_acquisition": "formal_acquisition",
                    "acquisition_completed": "formal_acquisition",
                    "final_evaluation": "final_evaluation",
                }.get(args.real_experiment_phase)
                if expected_scope and args.formal_bootstrap_scope != expected_scope:
                    parser.error(
                        "formal bootstrap scope does not match real experiment phase"
                    )
            if formal_acquisition_campaign is not None:
                if args.real_experiment_phase != "acquisition_completed":
                    parser.error("formal acquisition requires acquisition_completed phase")
                entry = formal_acquisition_entry
                assert entry is not None
                if (
                    args.real_experiment_task != str(entry["task"])
                    or str(args.real_experiment_seed) != str(entry["seed"])
                ):
                    parser.error("real experiment task/seed differs from schedule entry")
                task_list = _load_task_list(args.task)
                if len(task_list) != 1 or not _runtime_target_matches_catalog_task(
                    runtime_target=str(task_list[0].get("task", "")),
                    catalog_task=str(entry["task"]),
                ):
                    parser.error("task JSON differs from formal schedule entry")
            if alias_arguments_present:
                try:
                    provider_alias_policy = load_provider_model_alias_policy(
                        args.provider_model_alias_policy,
                        approval_record=args.provider_model_alias_approval,
                    )
                    alias_scope = {
                        "experience_acquisition": "formal_acquisition",
                        "final_evaluation": "final_evaluation",
                    }.get(args.real_experiment_phase, "development_experiment")
                    provider_alias_policy.assert_activation_allowed(
                        scope=alias_scope,
                        requested_model=model_profile.model,
                    )
                except (OSError, TypeError, ValueError) as exc:
                    parser.error(str(exc))
        real_experiment_trace_payload = validate_real_experiment_launch(
            blueprint=real_experiment_blueprint,
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
        if formal_bootstrap_enabled:
            formal_bootstrap_session = FormalLogBootstrapSession(
                policy=formal_bootstrap_policy,
                amendment_id=formal_bootstrap_amendment.amendment_id,
                source_commit=(
                    formal_acquisition_campaign.source_commit
                    if formal_acquisition_campaign is not None
                    else formal_bootstrap_binding.source_commit
                ),
                blueprint_id=real_experiment_blueprint.blueprint_id,
                scope=args.formal_bootstrap_scope,
                method_id=args.formal_bootstrap_method_id,
                task=args.real_experiment_task,
                seed=args.real_experiment_seed,
            )

    if formal_acquisition_campaign is not None:
        receipt_path = args.formal_bootstrap_receipt
        pending_receipt_path = receipt_path.with_suffix(
            receipt_path.suffix + ".pending"
        )
        final_episode_path = AcquisitionStore(
            args.formal_acquisition_root
        ).episode_path(formal_acquisition_attempt_id)
        staged_episode_path = AcquisitionStore(
            formal_acquisition_staging_root
        ).episode_path(formal_acquisition_attempt_id)
        if receipt_path.exists():
            existing = _load_json(receipt_path)
            if bool(existing.get("task_completed")) and not final_episode_path.is_file():
                raise RuntimeError(
                    "successful formal receipt exists without its acquisition record"
                )
            print(json.dumps({
                "resume": "formal attempt already has a raw receipt",
                "attempt_id": formal_acquisition_attempt_id,
                "receipt": str(receipt_path),
            }, sort_keys=True))
            return 0 if bool(existing.get("pipeline_pass")) else 1
        if pending_receipt_path.exists():
            pending = dict(_load_json(pending_receipt_path))
            pending["returned_model_identities"] = tuple(
                pending.get("returned_model_identities", ())
            )
            pending["event_ids"] = tuple(pending.get("event_ids", ()))
            receipt = FormalBootstrapRunReceipt(**pending)
            if not receipt.task_completed:
                raise RuntimeError("pending formal receipt is not a successful run")
            provenance = _formal_acquisition_provenance(
                campaign=formal_acquisition_campaign,
                entry=formal_acquisition_entry,
                attempt_id=formal_acquisition_attempt_id,
                receipt=receipt,
            )
            finalize_staged_acquisition(
                staging_root=formal_acquisition_staging_root,
                final_root=args.formal_acquisition_root,
                episode_id=formal_acquisition_attempt_id,
                provenance=provenance,
            )
            os.replace(pending_receipt_path, receipt_path)
            print(json.dumps({
                "resume": "reconciled staged successful acquisition without rerun",
                "attempt_id": formal_acquisition_attempt_id,
                "receipt": str(receipt_path),
            }, sort_keys=True))
            return 0
        if staged_episode_path.exists():
            raise RuntimeError(
                "staged successful acquisition has no pending receipt; refusing "
                "to rerun Minecraft or create a duplicate"
            )

    try:
        requested_environment_seed = _configure_real_experiment_seed(
            real_experiment_blueprint=real_experiment_blueprint,
            raw_seed=args.real_experiment_seed,
        )
    except ValueError as exc:
        parser.error(str(exc))

    def write_dry_run_receipt(result=None, exception: Optional[BaseException] = None) -> None:
        if not dry_run_enabled or dry_run_campaign is None or dry_run_entry is None:
            return
        trace_sha256 = ""
        if args.trace.exists():
            from dc3pa.experiments.dry_run import sha256_file

            trace_sha256 = sha256_file(args.trace)
        expected_calls = expected_provider_call_count
        if model_profile is not None and args.mode == "reasoning_only":
            expected_calls = _expected_reasoning_only_provider_calls(
                task_count=expected_provider_call_count,
                result=result,
            )
        receipt = receipt_from_stage6_result(
            campaign=dry_run_campaign,
            entry_id=dry_run_entry.entry_id,
            result=result,
            output_root=args.dry_run_output_root,
            process_exit_code=0 if exception is None else 1,
            launch_validation_passed=real_experiment_trace_payload is not None,
            formal_memory_used=False,
            exception=exception,
            truth_evidence={
                "requested_seed": args.real_experiment_seed,
                "effective_seed": effective_environment_seed,
                "environment_started": environment_started,
                "requested_model": model_profile.model if model_profile else "",
                "returned_models": [item.returned_model for item in provider_metadata],
                "model_profile_id": model_profile.profile_id if model_profile else "",
                "reasoning_effort": model_profile.reasoning_effort if model_profile else "",
                "expected_provider_call_count": expected_calls,
                "actual_provider_call_count": len(provider_metadata),
                "dry_run_root_guard_passed": (
                    dry_run_marker_for(args.dry_run_output_root) is not None
                ),
                "provider_model_alias_policy_id": (
                    provider_alias_policy.policy_id
                    if provider_alias_policy is not None
                    else ""
                ),
                "trace_sha256": trace_sha256,
                "task": dry_run_entry.task,
                "difficulty": dry_run_difficulty,
            },
            fallback_metrics=receipt_metrics_from_events(
                policy=fallback_policy,
                enabled=fallback_session is not None,
                events=fallback_session.events if fallback_session is not None else (),
                task_completed=bool(result is not None and result.success),
                planner_calls=sum(
                    item.purpose == "planning" for item in provider_metadata
                ),
                reflection_calls=sum(
                    item.purpose == "reflection" for item in provider_metadata
                ),
                evaluation_chain_calls=(
                    int(getattr(result, "evaluation_count", 0) or 0)
                    if result is not None
                    else 0
                ),
            ).to_dict(),
        )
        save_receipt(args.dry_run_receipt, receipt)

    def build_formal_bootstrap_receipt(
        result=None, exception: Optional[BaseException] = None
    ):
        if formal_bootstrap_session is None:
            return None
        from dc3pa.experiments.dry_run import sha256_file

        trace_sha256 = sha256_file(args.trace) if args.trace.exists() else ""
        returned_identities = tuple(
            item.returned_model for item in provider_metadata
            if str(item.returned_model).strip()
        )
        identity_stable = bool(returned_identities) and (
            len(set(returned_identities)) == 1
        )
        expected_calls = expected_provider_call_count
        if model_profile is not None and args.mode == "reasoning_only":
            expected_calls = _expected_reasoning_only_provider_calls(
                task_count=expected_provider_call_count,
                result=result,
            )
        provider_contract = expected_calls == len(provider_metadata)
        event_items = formal_bootstrap_session.events
        triggered = tuple(
            item for item in event_items if item.intervention_triggered
        )
        result_events = tuple(getattr(result, "events", ()) or ())
        acquisition_writes = sum(
            item.event_type == "acquisition_record_committed"
            for item in result_events
        )
        task_completed = bool(result is not None and result.success)
        pipeline_pass = bool(
            exception is None
            and environment_started
            and provider_contract
            and returned_identities
            and trace_sha256
        )
        receipt = FormalBootstrapRunReceipt(
            run_id=(
                formal_acquisition_attempt_id
                if formal_acquisition_attempt_id
                else dry_run_entry.entry_id
                if dry_run_entry is not None
                else f"{args.real_experiment_task}:{args.real_experiment_seed}"
            ),
            readiness_campaign_id=(
                dry_run_campaign.campaign_id
                if dry_run_campaign is not None
                else ""
            ),
            policy_id=formal_bootstrap_policy.policy_id,
            bootstrap_amendment_id=formal_bootstrap_amendment.amendment_id,
            bootstrap_data_binding_id=formal_bootstrap_binding.binding_id,
            scope=args.formal_bootstrap_scope,
            method_id=args.formal_bootstrap_method_id,
            task=args.real_experiment_task,
            seed=args.real_experiment_seed,
            source_commit=(
                formal_acquisition_campaign.source_commit
                if formal_acquisition_campaign is not None
                else formal_bootstrap_binding.source_commit
            ),
            blueprint_id=real_experiment_blueprint.blueprint_id,
            model_profile_id=model_profile.profile_id if model_profile else "legacy",
            requested_model=model_profile.model if model_profile else args.gpt_model_name,
            returned_model_identities=returned_identities,
            returned_identity_stable_within_run=identity_stable,
            process_exit_code=0 if exception is None else 1,
            pipeline_pass=pipeline_pass,
            task_completed=task_completed,
            planner_calls=sum(item.purpose == "planning" for item in provider_metadata),
            reflection_calls=sum(
                item.purpose == "reflection" for item in provider_metadata
            ),
            evaluation_chain_calls=(
                int(getattr(result, "evaluation_count", 0) or 0)
                if result is not None
                else 0
            ),
            controller_execution_count=(
                int(getattr(result, "controller_execution_count", 0) or 0)
                if result is not None
                else 0
            ),
            event_ids=tuple(item.event_id for item in triggered),
            intervention_trigger_count=len(triggered),
            total_injected_logs=sum(item.injected_logs for item in triggered),
            total_naturally_collected_logs=sum(
                item.naturally_collected_logs for item in event_items
            ),
            natural_completion=bool(task_completed and not triggered),
            bootstrap_assisted_completion=bool(task_completed and triggered),
            formal_memory_write_count=int(
                bool(result is not None and result.memory_recorded)
            ),
            acquisition_write_count=acquisition_writes,
            provider_call_contract_passed=provider_contract,
            output_root_guard_passed=(
                args.formal_bootstrap_output_root
                / ".dc3pa-formal-log-bootstrap-output.json"
            ).is_file(),
            trace_sha256=trace_sha256,
        ).with_id()
        validate_events_for_receipt(
            policy=formal_bootstrap_policy,
            receipt=receipt,
            events=triggered,
        )
        return receipt

    def save_formal_bootstrap_receipt(receipt) -> None:
        if receipt is None:
            return
        output = args.formal_bootstrap_receipt
        if output.exists():
            raise FileExistsError(
                f"Refusing to overwrite formal bootstrap receipt: {output}"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        pending = output.with_suffix(output.suffix + ".pending")
        serialized = json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n"
        if pending.exists():
            if pending.read_text(encoding="utf-8") != serialized:
                raise FileExistsError("pending formal receipt content mismatch")
            os.replace(pending, output)
            return
        output.write_text(serialized, encoding="utf-8")

    def stage_formal_bootstrap_receipt(receipt) -> None:
        if receipt is None:
            return
        output = args.formal_bootstrap_receipt
        pending = output.with_suffix(output.suffix + ".pending")
        serialized = json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        if pending.exists():
            if pending.read_text(encoding="utf-8") != serialized:
                raise FileExistsError("pending formal receipt content mismatch")
            return
        with pending.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())

    def write_formal_bootstrap_receipt(
        result=None, exception: Optional[BaseException] = None
    ) -> None:
        save_formal_bootstrap_receipt(
            build_formal_bootstrap_receipt(result, exception)
        )

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
            environment_started = evaluator.env is not None
            effective_environment_seed = getattr(
                evaluator, "effective_world_seed", None
            )
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
                returned_model_validation, verify_returned_model = (
                    _returned_model_validation(
                        provider_alias_policy=provider_alias_policy,
                        formal_bootstrap_enabled=formal_bootstrap_enabled,
                    )
                )
                trace_writer.write(
                    "model_profile_activated",
                    {
                        "profile_id": model_profile.profile_id,
                        "model": model_profile.model,
                        "reasoning_effort": model_profile.reasoning_effort,
                        "returned_model_validation": returned_model_validation,
                        "provider_model_alias_policy_id": (
                            provider_alias_policy.policy_id
                            if provider_alias_policy is not None
                            else ""
                        ),
                    },
                )
                memory.llm = _profile_chat_model(
                    model_profile,
                    "dc3pa_confidence_and_evaluation",
                    trace_writer,
                    provider_metadata.append,
                    verify_returned_model=verify_returned_model,
                )
                reflexion.llm = _profile_chat_model(
                    model_profile,
                    "reflection",
                    trace_writer,
                    provider_metadata.append,
                    verify_returned_model=verify_returned_model,
                )
                planner_instance.llm = _profile_chat_model(
                    model_profile,
                    "planning",
                    trace_writer,
                    provider_metadata.append,
                    verify_returned_model=verify_returned_model,
                )
            elif hasattr(memory, "llm"):
                memory.llm = TracedChatModel(
                    memory.llm,
                    trace_writer,
                    "dc3pa_confidence_and_evaluation",
                    metadata_observer=provider_metadata.append,
                    requested_model=args.gpt_model_name,
                )
            if model_profile is None and hasattr(reflexion, "llm"):
                reflexion.llm = TracedChatModel(
                    reflexion.llm,
                    trace_writer,
                    "reflection",
                    metadata_observer=provider_metadata.append,
                    requested_model=args.gpt_model_name,
                )
            if model_profile is None and hasattr(planner_instance, "llm"):
                planner_instance.llm = TracedChatModel(
                    planner_instance.llm,
                    trace_writer,
                    "planning",
                    metadata_observer=provider_metadata.append,
                    requested_model=args.gpt_model_name,
                )
            controller = legacy_runner.Controller(memory=memory, checker=reflexion)
            active_log_session = formal_bootstrap_session or fallback_session
            if active_log_session is not None:
                controller._dc3pa_log_fallback_session = active_log_session
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
                if formal_bootstrap_binding is not None:
                    assert_bootstrap_snapshot_binding(
                        manifest.metadata,
                        expected_policy_id=formal_bootstrap_policy.policy_id,
                        expected_amendment_id=formal_bootstrap_amendment.amendment_id,
                        expected_binding_id=formal_bootstrap_binding.binding_id,
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
                    dependency_extractor=(
                        SceneOnlyDependencyExtractor()
                        if formal_acquisition_enabled
                        else None
                    ),
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
                    record_metadata_provider=(
                        lambda task_completed: {
                            **formal_bootstrap_session.record_metadata(
                                task_completed=task_completed
                            ),
                            "bootstrap_data_binding_id": (
                                formal_bootstrap_binding.binding_id
                            ),
                            **(
                                {
                                    "campaign_id": formal_acquisition_campaign.campaign_id,
                                    "schedule_id": formal_acquisition_campaign.schedule_id,
                                    "attempt_id": formal_acquisition_attempt_id,
                                    "seed": str(formal_acquisition_entry["seed"]),
                                    "difficulty": str(formal_acquisition_entry["difficulty"]),
                                }
                                if formal_acquisition_campaign is not None
                                else {}
                            ),
                        }
                        if formal_bootstrap_session is not None
                        else None
                    ),
                    episode_id_provider=(
                        (lambda _attempt_index: formal_acquisition_attempt_id)
                        if formal_acquisition_enabled
                        else None
                    ),
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
                formal_receipt = build_formal_bootstrap_receipt(last_result)
                if (
                    formal_acquisition_campaign is not None
                    and last_result is not None
                    and last_result.success
                ):
                    entry = formal_acquisition_entry
                    assert entry is not None
                    assert formal_receipt is not None
                    stage_formal_bootstrap_receipt(formal_receipt)
                    provenance = _formal_acquisition_provenance(
                        campaign=formal_acquisition_campaign,
                        entry=entry,
                        attempt_id=formal_acquisition_attempt_id,
                        receipt=formal_receipt,
                    )
                    finalize_staged_acquisition(
                        staging_root=formal_acquisition_staging_root,
                        final_root=args.formal_acquisition_root,
                        episode_id=formal_acquisition_attempt_id,
                        provenance=provenance,
                    )
                save_formal_bootstrap_receipt(formal_receipt)
    except Exception as exc:
        if not dry_run_enabled or not args.dry_run_receipt.exists():
            write_dry_run_receipt(None, exc)
        if (
            not formal_bootstrap_enabled
            or (
                not args.formal_bootstrap_receipt.exists()
                and not args.formal_bootstrap_receipt.with_suffix(
                    args.formal_bootstrap_receipt.suffix + ".pending"
                ).exists()
            )
        ):
            write_formal_bootstrap_receipt(None, exc)
        raise
    if dry_run_enabled:
        return 0
    return 0 if all_succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
