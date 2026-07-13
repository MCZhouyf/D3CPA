from __future__ import annotations

import pytest

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.errors import ContractValidationError
from dc3pa.memory import MultimodalMemory
from dc3pa.reliability import (
    CallableConfidenceProvider,
    HardGatedHybridProbabilityModel,
    HybridProbabilityConfig,
    HybridProbabilityModel,
    KnowledgeShadowStrategy,
    build_hybrid_probability_model,
)
from dc3pa.reliability.contracts import DimensionScore
from dc3pa.reliability.weights import LinearMemoryWeightPolicy


class FixedStrategy:
    def __init__(self, score):
        self._score = score

    def score(self, plan, step_index, state, context=None):
        return self._score


def test_hard_gate_forces_overall_probability_to_zero():
    model = HardGatedHybridProbabilityModel(
        knowledge=FixedStrategy(
            DimensionScore(
                dimension="knowledge",
                probability=0.8,
                available=True,
                reason="one mandatory prerequisite is missing",
                hard_conflict=True,
            )
        ),
        model=FixedStrategy(
            DimensionScore(
                dimension="model",
                probability=0.99,
                available=True,
                reason="high confidence",
            )
        ),
        environment=FixedStrategy(
            DimensionScore(
                dimension="environment",
                probability=0.99,
                available=True,
                reason="high similarity",
            )
        ),
        weight_policy=LinearMemoryWeightPolicy(),
    )
    plan = Plan(
        task="mine cobblestone",
        plan_id="hard-gate-plan",
        steps=[
            PlanStep(
                step_id="mine",
                actions=[
                    Action("mine", {"obj": "cobblestone", "tool": "wooden pickaxe"})
                ],
            )
        ],
    )
    result = model.score_step(plan, 0, AgentState(task=plan.task, inventory={}))
    assert result.hard_conflict is True
    assert result.probability == 0.0
    assert any("hard gate" in note.lower() for note in result.notes)


def test_config_rejects_invalid_round2_knowledge_fields():
    with pytest.raises(ContractValidationError):
        HybridProbabilityConfig(knowledge_impl="invented").validate()
    with pytest.raises(ContractValidationError):
        HybridProbabilityConfig(graph_hard_min_support=True).validate()
    with pytest.raises(ContractValidationError):
        HybridProbabilityConfig(graph_hard_min_support=0).validate()


def test_factory_keeps_legacy_default_and_selects_round2_modes(tmp_path):
    confidence = CallableConfidenceProvider(lambda request: {"confidence": 0.9})
    with MultimodalMemory(tmp_path / "memory") as memory:
        legacy = build_hybrid_probability_model(
            memory,
            confidence,
            HybridProbabilityConfig(),
        )
        shadow = build_hybrid_probability_model(
            memory,
            confidence,
            HybridProbabilityConfig(knowledge_impl="shadow_v2"),
        )
        hard_gate = build_hybrid_probability_model(
            memory,
            confidence,
            HybridProbabilityConfig(knowledge_impl="hard_gate_v2"),
        )

    assert type(legacy) is HybridProbabilityModel
    assert type(hard_gate) is HardGatedHybridProbabilityModel
    assert isinstance(shadow, HybridProbabilityModel)
    assert isinstance(shadow.knowledge, KnowledgeShadowStrategy)
