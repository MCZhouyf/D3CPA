from __future__ import annotations

from ..memory.multimodal_memory import MultimodalMemory
from .config import HybridProbabilityConfig
from .environment import EnvironmentReliabilityStrategy
from .environment_v2 import (
    EnvironmentReliabilityStrategyV2,
    EnvironmentShadowStrategy,
    validate_environment_impl,
)
from .hybrid import HybridProbabilityModel
from .knowledge import KnowledgeReliabilityStrategy
from .knowledge_v2 import (
    HardGatedHybridProbabilityModel,
    KnowledgeReliabilityStrategyV2,
    KnowledgeShadowStrategy,
    validate_knowledge_impl,
)
from .confidence_observation import ConfidenceObservationCollector
from .model import ConfidenceProvider, VerbalConfidenceStrategy
from .ordinal_calibration import OrdinalCalibrationArtifact
from .ordinal_confidence import OrdinalConfidenceStrategy
from .ordinal_levels import validate_model_confidence_impl
from .weights import LinearMemoryWeightPolicy


def build_hybrid_probability_model(
    memory: MultimodalMemory,
    confidence_provider: ConfidenceProvider,
    config: HybridProbabilityConfig = HybridProbabilityConfig(),
    *,
    cache_model_confidence: bool = True,
    confidence_observer: ConfidenceObservationCollector | None = None,
) -> HybridProbabilityModel:
    """Compose the Stage-3 model from Stage-2 memory and a confidence provider.

    The function is deliberately provider-agnostic. Stage 6 may adapt an actual LLM,
    MineCLIP, or environment runtime without changing the reliability model itself.
    """

    config.validate()
    if not isinstance(cache_model_confidence, bool):
        raise ValueError("cache_model_confidence must be bool")
    legacy_knowledge = KnowledgeReliabilityStrategy(memory.dependencies)
    knowledge_impl = validate_knowledge_impl(config.knowledge_impl)
    if knowledge_impl == "legacy_v1":
        knowledge = legacy_knowledge
        model_class = HybridProbabilityModel
    else:
        candidate_knowledge = KnowledgeReliabilityStrategyV2(
            memory.dependencies,
            graph_hard_min_support=config.graph_hard_min_support,
        )
        if knowledge_impl == "shadow_v2":
            knowledge = KnowledgeShadowStrategy(legacy_knowledge, candidate_knowledge)
            model_class = HybridProbabilityModel
        else:
            knowledge = candidate_knowledge
            model_class = HardGatedHybridProbabilityModel

    confidence_impl = validate_model_confidence_impl(config.model_confidence_impl)
    if confidence_impl == "legacy_numeric":
        model_strategy = VerbalConfidenceStrategy(
            confidence_provider,
            failure_mode=config.model_failure_mode,
            cache_enabled=cache_model_confidence,
        )
    else:
        artifact = None
        if confidence_impl in {"ordinal_shadow", "ordinal_calibrated"}:
            artifact = OrdinalCalibrationArtifact.load(
                config.model_confidence_artifact_path
            )
        model_strategy = OrdinalConfidenceStrategy(
            confidence_provider,
            implementation=confidence_impl,
            model_id=config.model_confidence_model_id,
            prompt_version=config.model_confidence_prompt_version,
            artifact=artifact,
            observer=confidence_observer,
            failure_mode=config.model_failure_mode,
            cache_enabled=cache_model_confidence,
        )

    legacy_environment = EnvironmentReliabilityStrategy(
        memory,
        visual_similarity_weight=config.visual_similarity_weight,
        require_text_relevance=config.require_environment_text_relevance,
        task_name_filter=config.task_name_filter_environment,
    )
    environment_impl = validate_environment_impl(config.environment_impl)
    if environment_impl == "legacy_v1":
        environment = legacy_environment
    else:
        candidate_environment = EnvironmentReliabilityStrategyV2(
            memory,
            top_k=config.environment_top_k,
            text_threshold=config.environment_text_threshold,
            match_threshold=config.environment_match_threshold,
            scope=config.environment_scope,
            require_text_relevance=config.require_environment_text_relevance,
            task_name_filter=config.task_name_filter_environment,
            allow_legacy_text_fallback=config.environment_allow_legacy_text_fallback,
        )
        if environment_impl == "shadow_v2":
            environment = EnvironmentShadowStrategy(
                legacy_environment, candidate_environment
            )
        else:
            environment = candidate_environment

    return model_class(
        knowledge=knowledge,
        model=model_strategy,
        environment=environment,
        weight_policy=LinearMemoryWeightPolicy(
            learned_weight_cap=config.learned_weight_cap,
            memory_weight_growth=config.memory_weight_growth,
        ),
        memory_counter=memory,
    )
