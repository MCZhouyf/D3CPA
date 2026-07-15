from __future__ import annotations

import pytest

from dc3pa.errors import ContractValidationError
from dc3pa.memory import MultimodalMemory
from dc3pa.reliability import (
    CallableConfidenceProvider,
    EnvironmentReliabilityStrategy,
    EnvironmentReliabilityStrategyV2,
    EnvironmentShadowStrategy,
    HybridProbabilityConfig,
    build_hybrid_probability_model,
)


def _provider():
    return CallableConfidenceProvider(
        lambda request: {"confidence": 0.5, "reason": "offline test"}
    )


def test_round4_config_defaults_preserve_legacy_environment():
    config = HybridProbabilityConfig()
    assert config.environment_impl == "legacy_v1"
    assert config.environment_scope == "legacy_all_steps"
    assert config.to_dict()["environment_impl"] == "legacy_v1"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"environment_impl": "v3"},
        {"environment_scope": "future"},
        {"environment_top_k": 0},
        {"environment_top_k": True},
        {"environment_text_threshold": -0.01},
        {"environment_match_threshold": 1.01},
        {"environment_allow_legacy_text_fallback": "yes"},
    ],
)
def test_round4_config_rejects_unsafe_environment_values(kwargs):
    with pytest.raises(ContractValidationError):
        HybridProbabilityConfig(**kwargs).validate()


def test_factory_selects_environment_modes_without_changing_other_dimensions(tmp_path):
    with MultimodalMemory(tmp_path / "memory") as memory:
        legacy = build_hybrid_probability_model(
            memory,
            _provider(),
            HybridProbabilityConfig(),
        )
        shadow = build_hybrid_probability_model(
            memory,
            _provider(),
            HybridProbabilityConfig(environment_impl="shadow_v2"),
        )
        topk = build_hybrid_probability_model(
            memory,
            _provider(),
            HybridProbabilityConfig(environment_impl="topk_v2"),
        )

    assert isinstance(legacy.environment, EnvironmentReliabilityStrategy)
    assert isinstance(shadow.environment, EnvironmentShadowStrategy)
    assert isinstance(topk.environment, EnvironmentReliabilityStrategyV2)
    assert type(legacy.knowledge) is type(shadow.knowledge) is type(topk.knowledge)
    assert type(legacy.model) is type(shadow.model) is type(topk.model)
    assert legacy.weight_policy == shadow.weight_policy == topk.weight_policy
