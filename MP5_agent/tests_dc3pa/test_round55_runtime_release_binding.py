from __future__ import annotations

import json

import pytest

from dc3pa.memory import MultimodalMemory
from dc3pa.reliability import (
    CallableConfidenceProvider,
    HybridProbabilityConfig,
    build_hybrid_probability_model,
)
from dc3pa.reliability.development_protocol import sha256_file
from dc3pa.reliability.fusion_artifact import FusionArtifact
from dc3pa.reliability.fusion_features import FEATURE_SCHEMA_VERSION
from dc3pa.reliability.fusion_model import MonotonicLogisticHybridModel
from dc3pa.reliability.holdout_evaluation import HoldoutActivationReport
from dc3pa.reliability.holdout_lock import HoldoutLockManifest
from dc3pa.reliability.ordinal_calibration import OrdinalCalibrationArtifact
from dc3pa.reliability.ordinal_confidence import ordinal_prompt_template_sha256
from dc3pa.reliability.paper_release import PaperFusionRelease


def _release():
    return PaperFusionRelease(
        release_name="paper",
        fusion_artifact_id="artifact",
        fusion_artifact_sha256="artifact-sha",
        holdout_report_id="report",
        holdout_report_sha256="report-sha",
        development_protocol_id="protocol",
        activation_policy_id="policy",
        memory_snapshot_sha256="memory",
        confidence_artifact_id="confidence",
        environment_parameters={"top_k": 3, "text_threshold": 0.5},
        source_commit="commit",
        eligible=True,
        final_test_exclusion_id="exclusion",
        holdout_lock_id="lock",
        holdout_attempt_ledger_sha256="ledger-sha",
        environment_parameter_sha256="environment-sha",
    ).with_id()


def test_runtime_environment_parameter_mismatch_fails_closed():
    with pytest.raises(ValueError):
        _release().validate_runtime(
            fusion_artifact_id="artifact",
            holdout_report_id="report",
            memory_snapshot_sha256="memory",
            confidence_artifact_id="confidence",
            environment_parameters={"top_k": 5, "text_threshold": 0.5},
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


def _fusion_artifact(path):
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
        memory_snapshot_sha256="memory-hash",
        confidence_artifact_id="confidence-artifact",
        created_from_commit="commit",
    ).with_id()
    path.write_text(
        json.dumps(artifact.to_dict(), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def _holdout_report(path, artifact):
    report = HoldoutActivationReport(
        artifact_id=artifact.artifact_id,
        policy_id="policy",
        protocol_id="protocol",
        holdout_dataset_sha256="holdout",
        group_count=2,
        example_count=4,
        positive_count=2,
        negative_count=2,
        comparisons={},
        candidate_metrics={},
        legacy_metrics={},
        equal_weight_metrics={},
        stratified_metrics={},
        eligible=True,
        eligibility_reasons=(),
        source_commit="commit",
    ).with_id()
    path.write_text(
        json.dumps(report.to_dict(), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _holdout_lock(path, *, artifact_path, artifact):
    lock = HoldoutLockManifest(
        lock_name="lock",
        holdout_dataset_sha256="dataset-sha",
        development_protocol_id="protocol",
        activation_policy_id="policy",
        fusion_artifact_id=artifact.artifact_id,
        fusion_artifact_sha256=sha256_file(artifact_path),
        final_test_exclusion_id="exclusion",
        collection_manifest_id="collection",
        memory_snapshot_sha256="memory-hash",
        confidence_artifact_id="confidence-artifact",
        environment_parameter_sha256="environment-sha",
        source_commit="commit",
        created_at="2026-07-15T00:00:00+00:00",
    ).with_id()
    path.write_text(
        json.dumps(lock.to_dict(), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return lock


def _paper_release(
    path,
    *,
    artifact_path,
    report_path,
    ledger_path,
    artifact,
    report,
    lock,
):
    release = PaperFusionRelease(
        release_name="paper",
        fusion_artifact_id=artifact.artifact_id,
        fusion_artifact_sha256=sha256_file(artifact_path),
        holdout_report_id=report.report_id,
        holdout_report_sha256=sha256_file(report_path),
        development_protocol_id="protocol",
        activation_policy_id="policy",
        memory_snapshot_sha256="memory-hash",
        confidence_artifact_id="confidence-artifact",
        environment_parameters={
            "top_k": 3,
            "text_threshold": 0.5,
            "match_threshold": 0.5,
            "scope": "current_context_only",
        },
        source_commit="commit",
        eligible=True,
        final_test_exclusion_id="exclusion",
        holdout_lock_id=lock.lock_id,
        holdout_attempt_ledger_sha256=sha256_file(ledger_path),
        environment_parameter_sha256="environment-sha",
    ).with_id()
    path.write_text(
        json.dumps(release.to_dict(), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return release


def _paper_config(
    confidence_path,
    fusion_path,
    release_path,
    report_path,
    lock_path,
    ledger_path,
    **updates,
):
    payload = dict(
        knowledge_impl="hard_gate_v2",
        model_confidence_impl="ordinal_calibrated",
        model_confidence_model_id="gpt-test",
        model_confidence_artifact_path=str(confidence_path),
        environment_impl="topk_v2",
        environment_scope="current_context_only",
        fusion_impl="monotonic_logistic_v2",
        fusion_artifact_path=str(fusion_path),
        fusion_memory_snapshot_sha256="memory-hash",
        fusion_paper_release_path=str(release_path),
        fusion_holdout_report_path=str(report_path),
        fusion_holdout_lock_path=str(lock_path),
        fusion_attempt_ledger_path=str(ledger_path),
        fusion_final_test_exclusion_id="exclusion",
        fusion_environment_parameter_sha256="environment-sha",
        fusion_source_commit="commit",
    )
    payload.update(updates)
    return HybridProbabilityConfig(**payload)


def test_factory_accepts_eligible_release_binding(tmp_path):
    confidence_path = tmp_path / "confidence.json"
    fusion_path = tmp_path / "fusion.json"
    report_path = tmp_path / "holdout.json"
    lock_path = tmp_path / "lock.json"
    ledger_path = tmp_path / "attempt.json"
    release_path = tmp_path / "release.json"
    _ordinal_artifact(confidence_path)
    artifact = _fusion_artifact(fusion_path)
    report = _holdout_report(report_path, artifact)
    ledger_path.write_text('{"status":"completed"}\n', encoding="utf-8")
    lock = _holdout_lock(lock_path, artifact_path=fusion_path, artifact=artifact)
    _paper_release(
        release_path,
        artifact_path=fusion_path,
        report_path=report_path,
        ledger_path=ledger_path,
        artifact=artifact,
        report=report,
        lock=lock,
    )

    with MultimodalMemory(tmp_path / "memory") as memory:
        model = build_hybrid_probability_model(
            memory,
            CallableConfidenceProvider(lambda request: {"confidence_level": "likely"}),
            _paper_config(
                confidence_path,
                fusion_path,
                release_path,
                report_path,
                lock_path,
                ledger_path,
            ),
        )

    assert isinstance(model, MonotonicLogisticHybridModel)


def test_factory_rejects_paper_release_environment_mismatch(tmp_path):
    confidence_path = tmp_path / "confidence.json"
    fusion_path = tmp_path / "fusion.json"
    report_path = tmp_path / "holdout.json"
    lock_path = tmp_path / "lock.json"
    ledger_path = tmp_path / "attempt.json"
    release_path = tmp_path / "release.json"
    _ordinal_artifact(confidence_path)
    artifact = _fusion_artifact(fusion_path)
    report = _holdout_report(report_path, artifact)
    ledger_path.write_text('{"status":"completed"}\n', encoding="utf-8")
    lock = _holdout_lock(lock_path, artifact_path=fusion_path, artifact=artifact)
    _paper_release(
        release_path,
        artifact_path=fusion_path,
        report_path=report_path,
        ledger_path=ledger_path,
        artifact=artifact,
        report=report,
        lock=lock,
    )

    with MultimodalMemory(tmp_path / "memory") as memory:
        with pytest.raises(ValueError, match="Paper release runtime mismatch"):
            build_hybrid_probability_model(
                memory,
                CallableConfidenceProvider(
                    lambda request: {"confidence_level": "likely"}
                ),
                _paper_config(
                    confidence_path,
                    fusion_path,
                    release_path,
                    report_path,
                    lock_path,
                    ledger_path,
                    environment_text_threshold=0.6,
                ),
            )


def test_factory_rejects_attempt_ledger_hash_mismatch(tmp_path):
    confidence_path = tmp_path / "confidence.json"
    fusion_path = tmp_path / "fusion.json"
    report_path = tmp_path / "holdout.json"
    lock_path = tmp_path / "lock.json"
    ledger_path = tmp_path / "attempt.json"
    release_path = tmp_path / "release.json"
    _ordinal_artifact(confidence_path)
    artifact = _fusion_artifact(fusion_path)
    report = _holdout_report(report_path, artifact)
    ledger_path.write_text('{"status":"completed"}\n', encoding="utf-8")
    lock = _holdout_lock(lock_path, artifact_path=fusion_path, artifact=artifact)
    _paper_release(
        release_path,
        artifact_path=fusion_path,
        report_path=report_path,
        ledger_path=ledger_path,
        artifact=artifact,
        report=report,
        lock=lock,
    )
    ledger_path.write_text('{"status":"tampered"}\n', encoding="utf-8")

    with MultimodalMemory(tmp_path / "memory") as memory:
        with pytest.raises(ValueError, match="attempt ledger hash mismatch"):
            build_hybrid_probability_model(
                memory,
                CallableConfidenceProvider(
                    lambda request: {"confidence_level": "likely"}
                ),
                _paper_config(
                    confidence_path,
                    fusion_path,
                    release_path,
                    report_path,
                    lock_path,
                    ledger_path,
                ),
            )
