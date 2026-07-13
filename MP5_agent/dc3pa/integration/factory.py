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
    if runtime_config.mode == "dc3pa":
        if multimodal_memory is None:
            raise ValueError("multimodal_memory is required in dc3pa mode")
        if chat_model is None:
            raise ValueError("chat_model is required in dc3pa mode")
        adapter = ChatModelTextAdapter(chat_model)
        reliability_model = build_hybrid_probability_model(
            multimodal_memory,
            ChatModelConfidenceProvider(adapter),
            config=hybrid_config,
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
        trace_writer=trace_writer,
    )
    return Stage6RuntimeBundle(
        runtime=runtime,
        reasoning_chain=reasoning_chain,
        cognitive_planner=cognitive_planner,
        multimodal_memory=multimodal_memory,
    )
