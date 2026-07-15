from __future__ import annotations

import pytest

from dc3pa.reliability.holdout_lock import (
    HoldoutLockManifest,
    claim_holdout_attempt,
)


def _lock():
    return HoldoutLockManifest(
        lock_name="lock",
        holdout_dataset_sha256="dataset",
        development_protocol_id="protocol",
        activation_policy_id="policy",
        fusion_artifact_id="artifact",
        fusion_artifact_sha256="artifact-file",
        final_test_exclusion_id="exclusion",
        collection_manifest_id="collection",
        memory_snapshot_sha256="memory",
        confidence_artifact_id="confidence",
        environment_parameter_sha256="environment",
        source_commit="commit",
        created_at="2026-07-15T00:00:00+00:00",
    ).with_id()


def test_attempt_ledger_is_single_use(tmp_path):
    path = tmp_path / "attempt.json"
    claim_holdout_attempt(
        path,
        lock=_lock(),
        output_report_path=tmp_path / "report.json",
        source_commit="commit",
    )
    with pytest.raises(FileExistsError):
        claim_holdout_attempt(
            path,
            lock=_lock(),
            output_report_path=tmp_path / "other.json",
            source_commit="commit",
        )
