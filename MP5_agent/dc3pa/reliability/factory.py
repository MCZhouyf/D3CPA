from __future__ import annotations

from ..memory.multimodal_memory import MultimodalMemory
from .config import HybridProbabilityConfig
from .environment import EnvironmentReliabilityStrategy
from .hybrid import HybridProbabilityModel
from .knowledge import KnowledgeReliabilityStrategy
from .model import ConfidenceProvider, VerbalConfidenceStrategy
from .weights import LinearMemoryWeightPolicy


def build_hybrid_probability_model(
    memory: MultimodalMemory,
    confidence_provider: ConfidenceProvider,
    config: HybridProbabilityConfig = HybridProbabilityConfig(),
    *,
    cache_model_confidence: bool = True,
) -> HybridProbabilityModel:
    """Compose the Stage-3 model from Stage-2 memory and a confidence provider.

    The function is deliberately provider-agnostic. Stage 6 may adapt an actual LLM,
    MineCLIP, or environment runtime without changing the reliability model itself.
    """

    config.validate()
    if not isinstance(cache_model_confidence, bool):
        raise ValueError("cache_model_confidence must be bool")
    return HybridProbabilityModel(
        knowledge=KnowledgeReliabilityStrategy(memory.dependencies),
        model=VerbalConfidenceStrategy(
            confidence_provider,
            failure_mode=config.model_failure_mode,
            cache_enabled=cache_model_confidence,
        ),
        environment=EnvironmentReliabilityStrategy(
            memory,
            visual_similarity_weight=config.visual_similarity_weight,
            require_text_relevance=config.require_environment_text_relevance,
            task_name_filter=config.task_name_filter_environment,
        ),
        weight_policy=LinearMemoryWeightPolicy(
            learned_weight_cap=config.learned_weight_cap,
            memory_weight_growth=config.memory_weight_growth,
        ),
        memory_counter=memory,
    )
