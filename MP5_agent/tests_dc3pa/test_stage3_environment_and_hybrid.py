from pathlib import Path

import numpy as np
import pytest

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.memory import CallableTextEncoder, MultimodalMemory, SceneObservation, SuccessfulEpisode
from dc3pa.reliability import (
    DimensionScore,
    EnvironmentReliabilityStrategy,
    HybridProbabilityModel,
    LinearMemoryWeightPolicy,
    ReliabilityContext,
)


class StaticStrategy:
    def __init__(self, score):
        self.result = score

    def score(self, plan, step_index, state, context=None):
        return self.result


def base_plan():
    return Plan(
        task="obtain cobblestone",
        steps=[PlanStep(actions=[Action("find", {"obj": "stone"})])],
    )


def add_exemplar(memory: MultimodalMemory, plan: Plan, image_vector, text_vector):
    episode = SuccessfulEpisode(
        task_name=plan.task,
        plan=plan,
        scenes=[
            SceneObservation(
                description="stone wall near player",
                task_context="obtain cobblestone",
                inventory={},
                position="surface",
                image_vector=np.asarray(image_vector, dtype=np.float32),
                text_vector=np.asarray(text_vector, dtype=np.float32),
            )
        ],
    )
    return memory.record_success(episode)


def test_environment_score_uses_best_visual_then_text_formula(tmp_path: Path):
    plan = base_plan()
    text_encoder = CallableTextEncoder(lambda text: np.asarray([1.0, 0.0]))
    with MultimodalMemory(tmp_path / "memory", text_encoder=text_encoder) as memory:
        result = add_exemplar(memory, plan, [0.0, 1.0], [1.0, 0.0])
        strategy = EnvironmentReliabilityStrategy(memory, visual_similarity_weight=0.7)
        score = strategy.score(
            plan,
            0,
            AgentState(task=plan.task),
            ReliabilityContext(
                task_context="obtain cobblestone",
                image_vector=np.asarray([1.0, 0.0]),
            ),
        )
        # Orthogonal image vectors have normalized cosine 0.5; text relevance is 1.0.
        assert score.probability == pytest.approx(0.5)
        assert score.evidence["exemplar_id"] == result["exemplar_ids"][0]
        assert score.evidence["visual_similarity"] == pytest.approx(0.5)
        assert score.evidence["task_relevance"] == pytest.approx(1.0)


def test_environment_score_is_unavailable_without_compatible_text_when_required(tmp_path: Path):
    plan = base_plan()
    with MultimodalMemory(tmp_path / "memory") as memory:
        add_exemplar(memory, plan, [1.0, 0.0], [1.0, 0.0])
        strategy = EnvironmentReliabilityStrategy(memory, require_text_relevance=True)
        score = strategy.score(
            plan,
            0,
            AgentState(task=plan.task),
            ReliabilityContext(image_vector=np.asarray([1.0, 0.0])),
        )
        assert score.probability is None


def test_hybrid_probability_fuses_three_dimensions_and_renormalizes():
    plan = base_plan()
    state = AgentState(task=plan.task)
    model = HybridProbabilityModel(
        knowledge=StaticStrategy(DimensionScore("knowledge", 1.0, True)),
        model=StaticStrategy(DimensionScore("model", 0.5, True)),
        environment=StaticStrategy(DimensionScore("environment", 0.0, True)),
        weight_policy=LinearMemoryWeightPolicy(0.4, 0.02),
    )
    result = model.score_step(plan, 0, state, successful_memory_count=10)
    assert result.probability == pytest.approx(0.5)
    assert result.base_weights.as_dict() == {
        "knowledge": 0.2,
        "model": 0.6,
        "environment": 0.2,
    }

    unavailable_environment = HybridProbabilityModel(
        knowledge=StaticStrategy(DimensionScore("knowledge", 1.0, True)),
        model=StaticStrategy(DimensionScore("model", 0.5, True)),
        environment=StaticStrategy(
            DimensionScore.unavailable("environment", "no exemplar")
        ),
        weight_policy=LinearMemoryWeightPolicy(0.4, 0.02),
    )
    second = unavailable_environment.score_step(
        plan, 0, state, successful_memory_count=10
    )
    assert second.probability == pytest.approx(0.625)
    assert second.effective_weights.knowledge == pytest.approx(0.25)
    assert second.effective_weights.model == pytest.approx(0.75)
    assert second.effective_weights.environment == pytest.approx(0.0)


def test_hybrid_preserves_hard_conflict_signal_even_with_model_only_cold_start():
    plan = base_plan()
    result = HybridProbabilityModel(
        knowledge=StaticStrategy(
            DimensionScore(
                "knowledge",
                0.0,
                True,
                hard_conflict=True,
                reason="missing tool",
            )
        ),
        model=StaticStrategy(DimensionScore("model", 0.95, True)),
        environment=StaticStrategy(DimensionScore.unavailable("environment", "empty")),
        weight_policy=LinearMemoryWeightPolicy(),
    ).score_step(plan, 0, AgentState(task=plan.task), successful_memory_count=0)
    assert result.probability == pytest.approx(0.95)
    assert result.hard_conflict


def test_environment_encoder_failure_becomes_unavailable(tmp_path: Path):
    plan = base_plan()
    text_encoder = CallableTextEncoder(
        lambda text: (_ for _ in ()).throw(RuntimeError("encoder unavailable"))
    )
    with MultimodalMemory(tmp_path / "memory", text_encoder=text_encoder) as memory:
        add_exemplar(memory, plan, [1.0, 0.0], [1.0, 0.0])
        score = EnvironmentReliabilityStrategy(memory).score(
            plan,
            0,
            AgentState(task=plan.task),
            ReliabilityContext(image_vector=np.asarray([1.0, 0.0])),
        )
        assert score.probability is None
        assert "failed" in score.reason.lower()


def test_hybrid_rejects_fractional_memory_count():
    plan = base_plan()
    model = HybridProbabilityModel(
        knowledge=StaticStrategy(DimensionScore.unavailable("knowledge", "none")),
        model=StaticStrategy(DimensionScore("model", 0.5, True)),
        environment=StaticStrategy(DimensionScore.unavailable("environment", "none")),
        weight_policy=LinearMemoryWeightPolicy(),
    )
    with pytest.raises(ValueError):
        model.score_step(
            plan,
            0,
            AgentState(task=plan.task),
            successful_memory_count=1.5,  # type: ignore[arg-type]
        )


def test_factory_wires_stage2_memory_into_all_three_strategies(tmp_path: Path):
    from dc3pa.reliability import (
        CallableConfidenceProvider,
        HybridProbabilityConfig,
        build_hybrid_probability_model,
    )

    plan = base_plan()
    with MultimodalMemory(tmp_path / "memory") as memory:
        model = build_hybrid_probability_model(
            memory,
            CallableConfidenceProvider(lambda request: {"confidence": 0.8}),
            HybridProbabilityConfig(memory_weight_growth=0.01),
        )
        assert model.memory_counter is memory
        assert model.knowledge.dependencies is memory.dependencies
        assert model.environment.memory is memory
        assert model.weight_policy.memory_weight_growth == pytest.approx(0.01)
