from __future__ import annotations

import json

import pytest

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.errors import ContractValidationError
from dc3pa.integration.providers import ChatModelConfidenceProvider, ChatModelTextAdapter
from dc3pa.memory import CallableTextEncoder, MultimodalMemory
from dc3pa.reliability import (
    CallableConfidenceProvider,
    ConfidenceObservationCollector,
    HybridProbabilityConfig,
    OrdinalCalibrationArtifact,
    OrdinalConfidenceStrategy,
    VerbalConfidenceStrategy,
    build_hybrid_probability_model,
    ordinal_prompt_template_sha256,
)


def _artifact(path, *, model_id="gpt-test", prompt_version="ordinal-v1"):
    artifact = OrdinalCalibrationArtifact(
        schema_version=1,
        artifact_id="artifact-test",
        model_id=model_id,
        prompt_version=prompt_version,
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
            "unlikely": 0.35,
            "uncertain": 0.55,
            "likely": 0.75,
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
        metrics={"base_brier": 0.1, "calibrated_brier": 0.1},
    )
    artifact.save(path)
    return artifact


def test_legacy_numeric_default_uses_existing_strategy(tmp_path):
    calls = []
    provider = CallableConfidenceProvider(
        lambda request: calls.append(request) or {"confidence": 0.8, "reason": "ok"}
    )
    with MultimodalMemory(
        tmp_path / "memory",
        text_encoder=CallableTextEncoder(lambda text: [1.0, 0.0]),
    ) as memory:
        model = build_hybrid_probability_model(
            memory,
            provider,
            HybridProbabilityConfig(),
        )

    assert isinstance(model.model, VerbalConfidenceStrategy)
    assert not isinstance(model.model, OrdinalConfidenceStrategy)


def test_ordinal_config_validation_and_factory_modes(tmp_path):
    with pytest.raises(ContractValidationError):
        HybridProbabilityConfig(model_confidence_impl="ordinal_v2").validate()
    with pytest.raises(ContractValidationError):
        HybridProbabilityConfig(
            model_confidence_impl="ordinal_shadow",
            model_confidence_model_id="gpt-test",
        ).validate()

    artifact_path = tmp_path / "artifact.json"
    _artifact(artifact_path)
    observer = ConfidenceObservationCollector()
    provider = CallableConfidenceProvider(
        lambda request: {"confidence_level": "likely", "reason": "ok"}
    )
    with MultimodalMemory(tmp_path / "memory") as memory:
        model = build_hybrid_probability_model(
            memory,
            provider,
            HybridProbabilityConfig(
                model_confidence_impl="ordinal_shadow",
                model_confidence_model_id="gpt-test",
                model_confidence_artifact_path=str(artifact_path),
            ),
            confidence_observer=observer,
        )

    assert isinstance(model.model, OrdinalConfidenceStrategy)


def test_ordinal_artifact_fails_closed_on_incompatibility(tmp_path):
    artifact_path = tmp_path / "artifact.json"
    _artifact(artifact_path, model_id="other-model")
    with MultimodalMemory(tmp_path / "memory") as memory:
        with pytest.raises(ValueError, match="incompatible calibration artifact"):
            build_hybrid_probability_model(
                memory,
                CallableConfidenceProvider(
                    lambda request: {"confidence_level": "likely"}
                ),
                HybridProbabilityConfig(
                    model_confidence_impl="ordinal_calibrated",
                    model_confidence_model_id="gpt-test",
                    model_confidence_artifact_path=str(artifact_path),
                ),
            )


def test_chat_provider_uses_exactly_one_selected_prompt():
    prompts = []
    provider = ChatModelConfidenceProvider(
        ChatModelTextAdapter(lambda prompt: prompts.append(prompt) or '{"confidence_level":"likely"}'),
        prompt_builder=lambda request: "ordinal prompt only",
    )
    plan = Plan(
        task="log",
        steps=[PlanStep(actions=[Action("find", {"obj": "log"})])],
    )
    provider.confidence(
        type(
            "Req",
            (),
            {
                "to_prompt_payload": lambda self: {},
                "plan": plan,
                "state": AgentState(task="log"),
                "step_index": 0,
                "context": None,
            },
        )()
    )
    assert prompts == ["ordinal prompt only"]
