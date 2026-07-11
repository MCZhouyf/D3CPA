import pytest

from dc3pa.errors import ContractValidationError
from dc3pa.reliability import (
    AdaptiveTriggerConfig,
    DimensionScore,
    HybridProbabilityConfig,
    LinearMemoryWeightPolicy,
    StrategyWeights,
    effective_weights,
)


def test_linear_memory_weights_preserve_cold_start_and_cap():
    policy = LinearMemoryWeightPolicy(learned_weight_cap=0.4, memory_weight_growth=0.02)
    assert policy.weights(0) == StrategyWeights(0.0, 1.0, 0.0)
    assert policy.weights(10) == StrategyWeights(0.2, 0.6, 0.2)
    capped = policy.weights(1000)
    assert capped.knowledge == pytest.approx(0.4)
    assert capped.model == pytest.approx(0.2)
    assert capped.environment == pytest.approx(0.4)


def test_effective_weights_renormalize_only_positive_available_signals():
    base = StrategyWeights(0.2, 0.6, 0.2)
    scores = {
        "knowledge": DimensionScore("knowledge", 1.0, True),
        "model": DimensionScore("model", 0.5, True),
        "environment": DimensionScore.unavailable("environment", "missing"),
    }
    weights = effective_weights(base, scores)
    assert weights.knowledge == pytest.approx(0.25)
    assert weights.model == pytest.approx(0.75)
    assert weights.environment == pytest.approx(0.0)


def test_cold_start_does_not_promote_zero_weight_knowledge_when_model_fails():
    base = StrategyWeights(0.0, 1.0, 0.0)
    scores = {
        "knowledge": DimensionScore("knowledge", 1.0, True),
        "model": DimensionScore.unavailable("model", "failed"),
        "environment": DimensionScore.unavailable("environment", "empty"),
    }
    assert effective_weights(base, scores) is None


def test_stage3_config_validates_unknown_and_unsafe_values():
    with pytest.raises(ContractValidationError):
        HybridProbabilityConfig.from_mapping({"unknown": 1})
    with pytest.raises(ContractValidationError):
        HybridProbabilityConfig(learned_weight_cap=0.6).validate()
    with pytest.raises(ContractValidationError):
        AdaptiveTriggerConfig(initial_interval=0).validate()


def test_configs_and_weight_policy_reject_bool_nonfinite_and_fractional_counts():
    with pytest.raises(ContractValidationError):
        HybridProbabilityConfig(visual_similarity_weight=True).validate()
    with pytest.raises(ContractValidationError):
        HybridProbabilityConfig(memory_weight_growth=float("nan")).validate()
    with pytest.raises(ContractValidationError):
        AdaptiveTriggerConfig(initial_interval=True).validate()
    with pytest.raises(ValueError):
        LinearMemoryWeightPolicy(memory_weight_growth=True)
    policy = LinearMemoryWeightPolicy()
    with pytest.raises(ValueError):
        policy.weights(True)
    with pytest.raises(ValueError):
        policy.weights(1.5)  # type: ignore[arg-type]
