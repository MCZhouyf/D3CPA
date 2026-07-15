from __future__ import annotations

import pytest

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.reliability import (
    CallableConfidenceProvider,
    ConfidenceObservationCollector,
    DimensionScore,
    HybridProbabilityModel,
    LinearMemoryWeightPolicy,
    OrdinalCalibrationArtifact,
    OrdinalConfidenceStrategy,
    ordinal_prompt_template_sha256,
)


class StaticStrategy:
    def __init__(self, score):
        self.score_value = score

    def score(self, plan, step_index, state, context=None):
        return self.score_value


def _artifact():
    return OrdinalCalibrationArtifact(
        schema_version=1,
        artifact_id="artifact-shadow",
        model_id="gpt-test",
        prompt_version="ordinal-v1",
        prompt_sha256=ordinal_prompt_template_sha256(),
        dataset_sha256="dataset",
        created_from_commit="commit",
        base_mapping={
            "very_unlikely": 0.1,
            "unlikely": 0.3,
            "uncertain": 0.5,
            "likely": 0.7,
            "very_likely": 0.9,
        },
        calibrated_mapping={
            "very_unlikely": 0.2,
            "unlikely": 0.4,
            "uncertain": 0.6,
            "likely": 0.8,
            "very_likely": 0.95,
        },
        sample_counts={
            level: {"total": 1, "positive": 1, "negative": 0}
            for level in (
                "very_unlikely",
                "unlikely",
                "uncertain",
                "likely",
                "very_likely",
            )
        },
        metrics={},
    )


def _plan():
    return Plan(
        task="log",
        plan_id="p",
        steps=[PlanStep(step_id="s", actions=[Action("find", {"obj": "log"})])],
    )


def test_ordinal_shadow_has_same_decision_and_call_count_as_base():
    calls = {"base": 0, "shadow": 0}

    base = OrdinalConfidenceStrategy(
        CallableConfidenceProvider(
            lambda request: calls.__setitem__("base", calls["base"] + 1)
            or {"confidence_level": "likely"}
        ),
        implementation="ordinal_v2",
        model_id="gpt-test",
        observer=ConfidenceObservationCollector(),
    )
    shadow_observer = ConfidenceObservationCollector()
    shadow = OrdinalConfidenceStrategy(
        CallableConfidenceProvider(
            lambda request: calls.__setitem__("shadow", calls["shadow"] + 1)
            or {"confidence_level": "likely"}
        ),
        implementation="ordinal_shadow",
        model_id="gpt-test",
        artifact=_artifact(),
        observer=shadow_observer,
    )

    plan = _plan()
    state = AgentState(task="log")
    base_score = base.score(plan, 0, state)
    shadow_score = shadow.score(plan, 0, state)

    assert calls == {"base": 1, "shadow": 1}
    assert shadow_score.probability == base_score.probability == pytest.approx(0.7)
    assert shadow_score.evidence["calibrated_probability"] == pytest.approx(0.8)
    assert shadow_observer.snapshot()[0].calibrated_probability == pytest.approx(0.8)


def test_calibrated_mode_changes_only_model_dimension_and_hard_conflict_still_surfaces():
    calibrated = OrdinalConfidenceStrategy(
        CallableConfidenceProvider(lambda request: {"confidence_level": "likely"}),
        implementation="ordinal_calibrated",
        model_id="gpt-test",
        artifact=_artifact(),
    )
    plan = _plan()
    model_score = calibrated.score(plan, 0, AgentState(task="log"))
    assert model_score.probability == pytest.approx(0.8)

    hybrid = HybridProbabilityModel(
        knowledge=StaticStrategy(
            DimensionScore(
                "knowledge",
                0.0,
                True,
                reason="missing hard prerequisite",
                hard_conflict=True,
            )
        ),
        model=StaticStrategy(model_score),
        environment=StaticStrategy(DimensionScore.unavailable("environment", "empty")),
        weight_policy=LinearMemoryWeightPolicy(),
    )
    result = hybrid.score_step(plan, 0, AgentState(task="log"), successful_memory_count=0)
    assert result.hard_conflict is True

