from __future__ import annotations

from pathlib import Path

import pytest

from dc3pa.reliability.holdout_lock import (
    HoldoutLockManifest,
    save_holdout_lock,
    sha256_file,
)


def _lock(dataset, artifact):
    return HoldoutLockManifest(
        lock_name="lock",
        holdout_dataset_sha256=sha256_file(dataset),
        development_protocol_id="protocol",
        activation_policy_id="policy",
        fusion_artifact_id="artifact-id",
        fusion_artifact_sha256=sha256_file(artifact),
        final_test_exclusion_id="exclusion",
        collection_manifest_id="collection",
        memory_snapshot_sha256="memory",
        confidence_artifact_id="confidence",
        environment_parameter_sha256="environment",
        source_commit="commit",
        created_at="2026-07-15T00:00:00+00:00",
    ).with_id()


def test_holdout_lock_detects_dataset_mutation(tmp_path):
    dataset = tmp_path / "holdout.jsonl"
    artifact = tmp_path / "artifact.json"
    dataset.write_text("a\n")
    artifact.write_text("{}\n")
    lock = _lock(dataset, artifact)
    dataset.write_text("b\n")
    with pytest.raises(ValueError):
        lock.validate_files(holdout_dataset=dataset, fusion_artifact=artifact)


def test_lock_refuses_overwrite(tmp_path):
    dataset = tmp_path / "holdout.jsonl"
    artifact = tmp_path / "artifact.json"
    output = tmp_path / "lock.json"
    dataset.write_text("a\n")
    artifact.write_text("{}\n")
    lock = _lock(dataset, artifact)
    save_holdout_lock(output, lock)
    with pytest.raises(FileExistsError):
        save_holdout_lock(output, lock)
