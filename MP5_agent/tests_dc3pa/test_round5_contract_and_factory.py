from __future__ import annotations

import json

import numpy as np
import pytest

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.errors import ContractValidationError
from dc3pa.memory import MultimodalMemory
from dc3pa.reliability import (
    CallableConfidenceProvider,
    FusionEvidence,
    HybridProbabilityConfig,
    ReliabilityContext,
    ReliabilityResult,
    StrategyWeights,
    build_hybrid_probability_model,
)
from dc3pa.reliability.contracts import DimensionScore
from dc3pa.reliability.fusion_artifact import FusionArtifact
from dc3pa.reliability.fusion_features import FEATURE_SCHEMA_VERSION
from dc3pa.reliability.fusion_model import (
    LogisticFusionShadowModel,
    MonotonicLogisticHybridModel,
)
from dc3pa.reliability.ordinal_calibration import OrdinalCalibrationArtifact
from dc3pa.reliability.ordinal_confidence import ordinal_prompt_template_sha256


def _plan() -> Plan:
    return Plan(
        task="obtain cobblestone",
        plan_id="plan-1",
        version=1,
        steps=[
            PlanStep(
                step_id="step-1",
                actions=[
                    Action("mine", {"obj": "cobblestone", "tool": "wooden_pickaxe"})
                ],
                metadata={"local_subgoal": "mine cobblestone"},
            )
        ],
    )


def _ordinal_artifact(path):
    artifact = OrdinalCalibrationArtifact(
        schema_version=1,
        artifact_id="confidence-artifact",
        model_id="gpt-test",
        prompt_version="ordinal-v1",
        prompt_sha256=ordinal_prompt_template_sha256(),
        dataset_sha256="confidence-dataset",
        created_from_commit="commit",
        base_mapping={
            "very_unlikely": 0.1,
            "unlikely": 0.3,
            "uncertain": 0.5,
            "likely": 0.7,
            "very_likely": 0.9,
        },
        calibrated_mapping={
            "very_unlikely": 0.1,
            "unlikely": 0.3,
            "uncertain": 0.5,
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
        metrics={"calibrated_brier": 0.1},
    )
    artifact.save(path)
    return artifact


def _fusion_artifact(path, *, memory_hash="memory-hash"):
    artifact = FusionArtifact(
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        knowledge_impl="hard_gate_v2",
        model_confidence_impl="ordinal_calibrated",
        environment_impl="topk_v2",
        environment_scope="current_context_only",
        knowledge_unknown_prior=0.5,
        environment_unknown_compatibility=0.5,
        intercept=-0.2,
        coefficients={
            "knowledge": 0.5,
            "model": 1.0,
            "environment": 0.5,
            "environment_coverage": 0.25,
        },
        dataset_sha256="dataset",
        memory_snapshot_sha256=memory_hash,
        confidence_artifact_id="confidence-artifact",
        created_from_commit="commit",
    ).with_id()
    path.write_text(json.dumps(artifact.to_dict(), sort_keys=True), encoding="utf-8")
    return artifact


def test_reliability_result_supports_legacy_and_logistic_contracts():
    scores = {
        "knowledge": DimensionScore("knowledge", 1.0, True),
        "model": DimensionScore("model", 0.5, True),
        "environment": DimensionScore("environment", 0.5, True),
    }
    legacy = ReliabilityResult(
        plan_id="plan",
        plan_version=1,
        step_id="step",
        step_index=0,
        probability=0.6,
        scores=scores,
        base_weights=StrategyWeights(0.2, 0.6, 0.2),
        effective_weights=StrategyWeights(0.2, 0.6, 0.2),
        successful_memory_count=10,
        fusion=FusionEvidence(method="memory_weighted_v1", probability=0.6),
    )
    assert legacy.to_dict()["base_weights"]["model"] == 0.6

    logistic = ReliabilityResult(
        plan_id="plan",
        plan_version=1,
        step_id="step",
        step_index=0,
        probability=0.7,
        scores=scores,
        fusion=FusionEvidence(
            method="monotonic_logistic_v2",
            probability=0.7,
            artifact_id="artifact",
            features={"knowledge": 1.0},
        ),
    )
    assert logistic.to_dict()["base_weights"] is None
    assert logistic.to_dict()["successful_memory_count"] is None

    with pytest.raises(ContractValidationError):
        ReliabilityResult(
            plan_id="plan",
            plan_version=1,
            step_id="step",
            step_index=0,
            probability=0.7,
            scores=scores,
            base_weights=StrategyWeights(0.2, 0.6, 0.2),
            fusion=FusionEvidence(method="monotonic_logistic_v2", probability=0.7),
        )


def test_factory_selects_shadow_and_active_fusion_modes(tmp_path):
    confidence_path = tmp_path / "confidence.json"
    fusion_path = tmp_path / "fusion.json"
    _ordinal_artifact(confidence_path)
    _fusion_artifact(fusion_path)
    provider = CallableConfidenceProvider(
        lambda request: {"confidence_level": "likely", "reason": "ok"}
    )
    with MultimodalMemory(tmp_path / "memory") as memory:
        shadow = build_hybrid_probability_model(
            memory,
            provider,
            HybridProbabilityConfig(
                knowledge_impl="hard_gate_v2",
                model_confidence_impl="ordinal_calibrated",
                model_confidence_model_id="gpt-test",
                model_confidence_artifact_path=str(confidence_path),
                environment_impl="topk_v2",
                environment_scope="current_context_only",
                fusion_impl="monotonic_logistic_shadow",
                fusion_artifact_path=str(fusion_path),
            ),
        )
        active = build_hybrid_probability_model(
            memory,
            provider,
            HybridProbabilityConfig(
                knowledge_impl="hard_gate_v2",
                model_confidence_impl="ordinal_calibrated",
                model_confidence_model_id="gpt-test",
                model_confidence_artifact_path=str(confidence_path),
                environment_impl="topk_v2",
                environment_scope="current_context_only",
                fusion_impl="monotonic_logistic_v2",
                fusion_artifact_path=str(fusion_path),
                fusion_memory_snapshot_sha256="memory-hash",
            ),
        )

    assert isinstance(shadow, LogisticFusionShadowModel)
    assert isinstance(active, MonotonicLogisticHybridModel)


def test_active_factory_rejects_memory_binding_mismatch(tmp_path):
    confidence_path = tmp_path / "confidence.json"
    fusion_path = tmp_path / "fusion.json"
    _ordinal_artifact(confidence_path)
    _fusion_artifact(fusion_path, memory_hash="expected-memory")
    with MultimodalMemory(tmp_path / "memory") as memory:
        with pytest.raises(ValueError, match="runtime mismatch"):
            build_hybrid_probability_model(
                memory,
                CallableConfidenceProvider(
                    lambda request: {"confidence_level": "likely"}
                ),
                HybridProbabilityConfig(
                    knowledge_impl="hard_gate_v2",
                    model_confidence_impl="ordinal_calibrated",
                    model_confidence_model_id="gpt-test",
                    model_confidence_artifact_path=str(confidence_path),
                    environment_impl="topk_v2",
                    environment_scope="current_context_only",
                    fusion_impl="monotonic_logistic_v2",
                    fusion_artifact_path=str(fusion_path),
                    fusion_memory_snapshot_sha256="actual-memory",
                ),
            )


def test_active_factory_scores_without_legacy_weights(tmp_path):
    confidence_path = tmp_path / "confidence.json"
    fusion_path = tmp_path / "fusion.json"
    _ordinal_artifact(confidence_path)
    _fusion_artifact(fusion_path)
    provider = CallableConfidenceProvider(
        lambda request: {"confidence_level": "likely", "reason": "ok"}
    )
    with MultimodalMemory(tmp_path / "memory") as memory:
        model = build_hybrid_probability_model(
            memory,
            provider,
            HybridProbabilityConfig(
                knowledge_impl="hard_gate_v2",
                model_confidence_impl="ordinal_calibrated",
                model_confidence_model_id="gpt-test",
                model_confidence_artifact_path=str(confidence_path),
                environment_impl="topk_v2",
                environment_scope="current_context_only",
                fusion_impl="monotonic_logistic_v2",
                fusion_artifact_path=str(fusion_path),
                fusion_memory_snapshot_sha256="memory-hash",
            ),
        )
        result = model.score_step(
            _plan(),
            0,
            AgentState(task="obtain cobblestone"),
            ReliabilityContext(
                image_vector=np.asarray([1.0, 0.0]),
                metadata={"environment_step_index": 0},
            ),
            successful_memory_count=1000,
        )

    assert result.probability is not None
    assert result.base_weights is None
    assert result.effective_weights is None
    assert result.successful_memory_count is None
    assert result.fusion.method == "monotonic_logistic_v2"
