from __future__ import annotations

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.reliability.contracts import DimensionScore, ReliabilityContext
from dc3pa.reliability.fusion_artifact import FusionArtifact
from dc3pa.reliability.fusion_features import FEATURE_SCHEMA_VERSION
from dc3pa.reliability.fusion_model import (
    MonotonicLogisticFusion,
    MonotonicLogisticHybridModel,
)


class _StaticStrategy:
    def __init__(self, score):
        self.score_value = score
        self.calls = 0

    def score(self, plan, step_index, state, context=None):
        self.calls += 1
        return self.score_value


def _artifact():
    return FusionArtifact(
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        knowledge_impl="hard_gate_v2",
        model_confidence_impl="ordinal_calibrated",
        environment_impl="topk_v2",
        environment_scope="current_context_only",
        knowledge_unknown_prior=0.5,
        environment_unknown_compatibility=0.5,
        intercept=0.0,
        coefficients={
            "knowledge": 1.0,
            "model": 1.0,
            "environment": 1.0,
            "environment_coverage": 1.0,
        },
        dataset_sha256="dataset",
        memory_snapshot_sha256="memory",
        confidence_artifact_id="confidence",
        created_from_commit="commit",
    ).with_id()


def _plan():
    return Plan(
        task="task",
        steps=[
            PlanStep(
                actions=[Action("find", {"obj": "tree"})],
                metadata={"local_subgoal": "find tree"},
            )
        ],
    )


def _model(*, hard=False):
    knowledge = _StaticStrategy(
        DimensionScore(
            "knowledge",
            0.8,
            True,
            evidence={"knowledge_v2": {"coverage": 0.8}},
            hard_conflict=hard,
        )
    )
    model = _StaticStrategy(
        DimensionScore(
            "model",
            0.7,
            True,
            evidence={
                "decision_probability_source": "calibrated",
                "calibration_artifact_id": "confidence",
            },
        )
    )
    environment = _StaticStrategy(
        DimensionScore(
            "environment",
            0.6,
            True,
            evidence={"status": "matched", "coverage": 0.9},
        )
    )
    return MonotonicLogisticHybridModel(
        knowledge=knowledge,
        model=model,
        environment=environment,
        fusion=MonotonicLogisticFusion(_artifact()),
    ), (knowledge, model, environment)


def test_active_v2_ignores_successful_memory_count_and_calls_each_strategy_once():
    probabilities = []
    for count in (0, 10, 1000):
        active, strategies = _model()
        result = active.score_step(
            _plan(),
            0,
            AgentState(task="task"),
            ReliabilityContext(),
            successful_memory_count=count,
        )
        probabilities.append(result.probability)
        assert result.successful_memory_count is None
        assert result.base_weights is None
        assert result.effective_weights is None
        assert [strategy.calls for strategy in strategies] == [1, 1, 1]
    assert probabilities[0] == probabilities[1] == probabilities[2]


def test_hard_conflict_forces_probability_zero_even_with_high_features():
    active, _ = _model(hard=True)
    result = active.score_step(
        _plan(),
        0,
        AgentState(task="task"),
        ReliabilityContext(),
    )
    assert result.probability == 0.0
    assert result.fusion.hard_gate_applied
