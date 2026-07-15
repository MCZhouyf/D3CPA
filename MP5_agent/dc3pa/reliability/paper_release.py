"""Immutable paper-release manifest for activated fusion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from .fusion_artifact import FusionArtifact
from .holdout_evaluation import HoldoutActivationReport


PAPER_RELEASE_SCHEMA_VERSION = 2


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class PaperFusionRelease:
    release_name: str
    fusion_artifact_id: str
    fusion_artifact_sha256: str
    holdout_report_id: str
    holdout_report_sha256: str
    development_protocol_id: str
    activation_policy_id: str
    memory_snapshot_sha256: str
    confidence_artifact_id: str
    environment_parameters: Mapping[str, Any]
    source_commit: str
    eligible: bool
    final_test_exclusion_id: str = ""
    holdout_lock_id: str = ""
    holdout_attempt_ledger_sha256: str = ""
    environment_parameter_sha256: str = ""
    notes: str = ""
    schema_version: int = PAPER_RELEASE_SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version not in {1, PAPER_RELEASE_SCHEMA_VERSION}:
            raise ValueError("Unsupported paper release schema")
        if not self.eligible:
            raise ValueError("Cannot create a paper release from an ineligible report")
        required = [
            self.release_name,
            self.fusion_artifact_id,
            self.fusion_artifact_sha256,
            self.holdout_report_id,
            self.holdout_report_sha256,
            self.development_protocol_id,
            self.activation_policy_id,
            self.memory_snapshot_sha256,
            self.confidence_artifact_id,
            self.source_commit,
        ]
        if self.schema_version >= PAPER_RELEASE_SCHEMA_VERSION:
            required.extend(
                [
                    self.final_test_exclusion_id,
                    self.holdout_lock_id,
                    self.holdout_attempt_ledger_sha256,
                    self.environment_parameter_sha256,
                ]
            )
        if any(not str(value).strip() for value in required):
            raise ValueError("Paper release fields cannot be empty")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("Paper release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        payload["environment_parameters"] = dict(
            sorted(self.environment_parameters.items())
        )
        return payload

    def compute_release_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "PaperFusionRelease":
        return replace(self, release_id=self.compute_release_id())

    def to_dict(self) -> dict[str, Any]:
        release = self if self.release_id else self.with_id()
        payload = release.payload_without_id()
        payload["release_id"] = release.release_id
        return payload

    def validate_runtime(
        self,
        *,
        fusion_artifact_id: str,
        holdout_report_id: str,
        memory_snapshot_sha256: str,
        confidence_artifact_id: str,
        environment_parameters: Mapping[str, Any],
        final_test_exclusion_id: str = "",
        holdout_lock_id: str = "",
        holdout_attempt_ledger_sha256: str = "",
        environment_parameter_sha256: str = "",
        source_commit: str = "",
    ) -> None:
        expected = {
            "fusion_artifact_id": self.fusion_artifact_id,
            "holdout_report_id": self.holdout_report_id,
            "memory_snapshot_sha256": self.memory_snapshot_sha256,
            "confidence_artifact_id": self.confidence_artifact_id,
            "environment_parameters": dict(self.environment_parameters),
        }
        actual = {
            "fusion_artifact_id": fusion_artifact_id,
            "holdout_report_id": holdout_report_id,
            "memory_snapshot_sha256": memory_snapshot_sha256,
            "confidence_artifact_id": confidence_artifact_id,
            "environment_parameters": dict(environment_parameters),
        }
        if self.schema_version >= PAPER_RELEASE_SCHEMA_VERSION:
            expected.update(
                {
                    "final_test_exclusion_id": self.final_test_exclusion_id,
                    "holdout_lock_id": self.holdout_lock_id,
                    "holdout_attempt_ledger_sha256": self.holdout_attempt_ledger_sha256,
                    "environment_parameter_sha256": self.environment_parameter_sha256,
                    "source_commit": self.source_commit,
                }
            )
            actual.update(
                {
                    "final_test_exclusion_id": final_test_exclusion_id,
                    "holdout_lock_id": holdout_lock_id,
                    "holdout_attempt_ledger_sha256": holdout_attempt_ledger_sha256,
                    "environment_parameter_sha256": environment_parameter_sha256,
                    "source_commit": source_commit,
                }
            )
        mismatches = {
            key: {"expected": expected[key], "actual": actual[key]}
            for key in expected
            if expected[key] != actual[key]
        }
        if mismatches:
            raise ValueError(f"Paper release runtime mismatch: {mismatches}")


def build_paper_release(
    *,
    release_name: str,
    artifact: FusionArtifact,
    artifact_sha256: str,
    report: HoldoutActivationReport,
    report_sha256: str,
    development_protocol_id: str,
    activation_policy_id: str,
    environment_parameters: Mapping[str, Any],
    source_commit: str,
    final_test_exclusion_id: str = "",
    holdout_lock_id: str = "",
    holdout_attempt_ledger_sha256: str = "",
    environment_parameter_sha256: str = "",
) -> PaperFusionRelease:
    if not report.eligible:
        raise ValueError(
            "Holdout activation report is ineligible; keep fusion in shadow mode"
        )
    artifact_id = artifact.artifact_id or artifact.compute_artifact_id()
    if artifact_id != report.artifact_id:
        raise ValueError("Holdout report does not evaluate this artifact")
    if activation_policy_id != report.policy_id:
        raise ValueError("Activation policy ID mismatch")
    if development_protocol_id != report.protocol_id:
        raise ValueError("Development protocol ID mismatch")
    return PaperFusionRelease(
        release_name=release_name,
        fusion_artifact_id=artifact_id,
        fusion_artifact_sha256=artifact_sha256,
        holdout_report_id=report.report_id or report.compute_report_id(),
        holdout_report_sha256=report_sha256,
        development_protocol_id=development_protocol_id,
        activation_policy_id=activation_policy_id,
        memory_snapshot_sha256=artifact.memory_snapshot_sha256,
        confidence_artifact_id=artifact.confidence_artifact_id,
        environment_parameters=dict(environment_parameters),
        source_commit=source_commit,
        eligible=True,
        final_test_exclusion_id=final_test_exclusion_id,
        holdout_lock_id=holdout_lock_id,
        holdout_attempt_ledger_sha256=holdout_attempt_ledger_sha256,
        environment_parameter_sha256=environment_parameter_sha256,
    ).with_id()


def save_paper_release(path: str | Path, release: PaperFusionRelease) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    release = release.with_id()
    output.write_text(
        json.dumps(release.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return release.release_id


def load_paper_release(path: str | Path) -> PaperFusionRelease:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 1)) == 1:
        payload.setdefault("final_test_exclusion_id", "")
        payload.setdefault("holdout_lock_id", "")
        payload.setdefault("holdout_attempt_ledger_sha256", "")
        payload.setdefault("environment_parameter_sha256", "")
    return PaperFusionRelease(**payload)
