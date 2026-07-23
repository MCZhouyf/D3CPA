from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

from ..evaluation import StructuredEvaluationChain
from ..memory.acquisition import AcquisitionStore
from ..memory.calibration_store import CalibrationEpisodeStore
from ..memory.modes import MemoryMode
from ..memory.multimodal_memory import MultimodalMemory
from ..observability.trace import JsonlTraceWriter
from ..planner.cognitive_control import AdaptiveCognitiveControlPlanner
from ..reliability import (
    AdaptiveTriggerConfig,
    DualChainConfig,
    HybridProbabilityConfig,
    build_hybrid_probability_model,
)
from ..reliability.confidence_observation import ConfidenceObservationCollector
from ..reliability.ordinal_confidence import (
    OrdinalConfidenceStrategy,
    build_ordinal_confidence_prompt,
)
from ..reliability.ordinal_levels import validate_model_confidence_impl
from ..reliability.model import build_verbal_confidence_prompt
from .controller import LegacyControllerAdapter
from .execution_observer import InMemoryExecutionObserver
from .legacy import (
    LegacyGoalChecker,
    LegacyMP5ReasoningChain,
    LegacyModePlanSource,
    LegacyReflexionAdapter,
    LegacyWorkflowMemorySink,
)
from .providers import (
    ChatModelConfidenceProvider,
    ChatModelEvaluationProvider,
    ChatModelTextAdapter,
)
from .runtime import Stage6ClosedLoopRunner
from .stage6_config import Stage6RuntimeConfig
from .state import LegacyMP5StateProvider, StateProvider


@dataclass(frozen=True)
class Stage6RuntimeBundle:
    runtime: Stage6ClosedLoopRunner
    reasoning_chain: LegacyMP5ReasoningChain
    cognitive_planner: Optional[AdaptiveCognitiveControlPlanner]
    multimodal_memory: Optional[MultimodalMemory]
    confidence_observer: Optional[ConfidenceObservationCollector] = None
    development_shadow_observer: Any = None


def build_legacy_state_provider(
    *,
    env: Any,
    legacy_memory: Any,
    share_memory: Callable[[Any, Any], None],
    noop_action: Optional[Sequence[int]] = None,
    refresh_environment: bool = True,
    initial_observation: Any = None,
) -> LegacyMP5StateProvider:
    if not isinstance(refresh_environment, bool):
        raise TypeError("refresh_environment must be bool")
    action = list(noop_action or [0, 0, 0, 12, 12, 0, 0, 0])
    cached_observation = [initial_observation]

    def refresh_observation() -> Any:
        if refresh_environment:
            result = env.step(action)
            observation = result[0] if isinstance(result, tuple) else result
            cached_observation[0] = observation
            share_memory(legacy_memory, observation)
            return observation
        return cached_observation[0]

    def inventory_provider() -> Mapping[str, Any]:
        value = getattr(legacy_memory, "inventory", {})
        return value if isinstance(value, Mapping) else {}

    return LegacyMP5StateProvider(
        refresh_observation=refresh_observation,
        inventory_provider=inventory_provider,
    )


def build_stage6_runtime(
    *,
    env: Any,
    runtime_config: Stage6RuntimeConfig,
    legacy_planner: Any,
    legacy_controller: Any,
    legacy_memory: Any,
    state_provider: StateProvider,
    multimodal_memory: Optional[MultimodalMemory] = None,
    chat_model: Any = None,
    legacy_reflexion: Any = None,
    fixed_workflow_provider: Optional[
        Callable[[Mapping[str, Any]], Optional[Mapping[str, Any]]]
    ] = None,
    hybrid_config: HybridProbabilityConfig = HybridProbabilityConfig(),
    dual_chain_config: DualChainConfig = DualChainConfig(),
    trigger_config: AdaptiveTriggerConfig = AdaptiveTriggerConfig(),
    trace_writer: Optional[JsonlTraceWriter] = None,
    record_metadata_provider: Optional[
        Callable[[bool], Mapping[str, Any]]
    ] = None,
    episode_id_provider: Optional[Callable[[int], str]] = None,
    development_shadow_observer: Any = None,
    chrmlite_plan_source: Any = None,
) -> Stage6RuntimeBundle:
    """Compose Stage 0–5 components into the Stage-6 closed loop.

    Real model and encoder selection remains dependency-injected. The factory does not
    silently install a test encoder or invent an environment score.
    """

    runtime_config.validate()
    reasoning_chain = LegacyMP5ReasoningChain(legacy_planner, legacy_memory)
    legacy_plan_source = LegacyModePlanSource(
        reasoning_chain, fixed_workflow_provider=fixed_workflow_provider
    )
    cognitive_planner: Optional[AdaptiveCognitiveControlPlanner] = None
    confidence_impl = validate_model_confidence_impl(hybrid_config.model_confidence_impl)
    use_ordinal_prompt = confidence_impl != "legacy_numeric"
    confidence_observer = (
        ConfidenceObservationCollector()
        if use_ordinal_prompt
        or runtime_config.model_confidence_collection == "passive_final_plan"
        else None
    )
    passive_confidence_scorer = None
    if runtime_config.mode == "dc3pa":
        if multimodal_memory is None:
            raise ValueError("multimodal_memory is required in dc3pa mode")
        if chat_model is None:
            raise ValueError("chat_model is required in dc3pa mode")
        adapter = ChatModelTextAdapter(chat_model)
        reliability_model = build_hybrid_probability_model(
            multimodal_memory,
            ChatModelConfidenceProvider(
                adapter,
                prompt_builder=(
                    build_ordinal_confidence_prompt
                    if use_ordinal_prompt
                    else build_verbal_confidence_prompt
                ),
            ),
            config=hybrid_config,
            confidence_observer=confidence_observer,
        )
        evaluation_chain = StructuredEvaluationChain(
            ChatModelEvaluationProvider(adapter), failure_mode="request_replan"
        )
        cognitive_planner = AdaptiveCognitiveControlPlanner(
            reasoning_chain=reasoning_chain,
            reliability_model=reliability_model,
            evaluation_chain=evaluation_chain,
            trigger_config=trigger_config,
            dual_chain_config=dual_chain_config,
            trace_writer=trace_writer,
        )
    elif runtime_config.model_confidence_collection == "passive_final_plan":
        if chat_model is None:
            raise ValueError("chat_model is required for passive_final_plan collection")

    if runtime_config.model_confidence_collection == "passive_final_plan":
        if not str(hybrid_config.model_confidence_model_id).strip():
            raise ValueError(
                "passive_final_plan collection requires model_confidence_model_id"
            )
        assert confidence_observer is not None
        passive_confidence_scorer = OrdinalConfidenceStrategy(
            ChatModelConfidenceProvider(
                ChatModelTextAdapter(chat_model),
                prompt_builder=build_ordinal_confidence_prompt,
            ),
            implementation="ordinal_v2",
            model_id=hybrid_config.model_confidence_model_id,
            prompt_version=hybrid_config.model_confidence_prompt_version,
            observer=confidence_observer,
            failure_mode=hybrid_config.model_failure_mode,
        )

    execution_observer = (
        InMemoryExecutionObserver() if runtime_config.telemetry_enabled else None
    )
    memory_mode = MemoryMode.parse(runtime_config.memory_mode)
    acquisition_store = None
    if runtime_config.acquisition_log_dir and memory_mode is MemoryMode.ACQUIRE:
        acquisition_store = AcquisitionStore(runtime_config.acquisition_log_dir)
    calibration_store = None
    if runtime_config.calibration_log_dir and memory_mode in {
        MemoryMode.ACQUIRE,
        MemoryMode.CALIBRATE,
    }:
        calibration_store = CalibrationEpisodeStore(runtime_config.calibration_log_dir)

    runtime = Stage6ClosedLoopRunner(
        env=env,
        config=runtime_config,
        reasoning_chain=reasoning_chain,
        legacy_plan_source=legacy_plan_source,
        cognitive_planner=cognitive_planner,
        controller=LegacyControllerAdapter(
            legacy_controller,
            observer=execution_observer,
        ),
        state_provider=state_provider,
        goal_checker=LegacyGoalChecker(legacy_controller, legacy_memory),
        reflexion=(
            LegacyReflexionAdapter(legacy_reflexion)
            if legacy_reflexion is not None
            else None
        ),
        legacy_memory_sink=LegacyWorkflowMemorySink(legacy_memory),
        multimodal_memory_sink=multimodal_memory,
        acquisition_store=acquisition_store,
        calibration_store=calibration_store,
        confidence_observer=confidence_observer,
        passive_confidence_scorer=passive_confidence_scorer,
        trace_writer=trace_writer,
        record_metadata_provider=record_metadata_provider,
        episode_id_provider=episode_id_provider,
        development_shadow_observer=development_shadow_observer,
        chrmlite_plan_source=chrmlite_plan_source,
    )
    return Stage6RuntimeBundle(
        runtime=runtime,
        reasoning_chain=reasoning_chain,
        cognitive_planner=cognitive_planner,
        multimodal_memory=multimodal_memory,
        confidence_observer=confidence_observer,
        development_shadow_observer=development_shadow_observer,
    )
