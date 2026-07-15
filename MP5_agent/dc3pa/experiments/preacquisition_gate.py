"""Final meta-gate before formal single-chain acquisition may begin."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .final_taskset_release import FinalTasksetRelease


SCHEMA_VERSION = 1


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class PreAcquisitionGateReport:
    source_commit: str
    final_taskset_release_id: str
    taskset_amendment_id: str
    semantic_migration_report_id: str
    blueprint_id: str
    approval_binding_id: str
    blueprint_validation_report_id: str
    closed_model_epoch_id: str
    acquisition_readiness_id: str
    final_taskset_eligible: bool
    migration_eligible: bool
    blueprint_validation_eligible: bool
    readiness_eligible: bool
    phase_can_advance: bool
    formal_acquisition_permitted: bool
    reasons: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    gate_id: str = ""

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("gate_id", None)
        payload["reasons"] = list(self.reasons)
        return payload

    def compute_gate_id(self) -> str:
        return hashlib.sha256(
            _canonical_json(self.payload_without_id())
        ).hexdigest()

    def with_id(self) -> "PreAcquisitionGateReport":
        return replace(self, gate_id=self.compute_gate_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.gate_id else self.with_id()
        payload = item.payload_without_id()
        payload["gate_id"] = item.gate_id
        return payload


def audit_preacquisition_gate(
    *,
    source_commit: str,
    final_taskset: FinalTasksetRelease,
    migration_report: Mapping[str, Any],
    approval_binding: Mapping[str, Any],
    blueprint_validation: Mapping[str, Any],
    closed_model_epoch: Mapping[str, Any],
    acquisition_readiness: Mapping[str, Any],
) -> PreAcquisitionGateReport:
    reasons: list[str] = []
    migration_ok = bool(migration_report.get("eligible", False))
    blueprint_ok = bool(blueprint_validation.get("eligible", False))
    readiness_ok = bool(acquisition_readiness.get("eligible", False))
    taskset_ok = bool(final_taskset.eligible)

    if final_taskset.source_commit != source_commit:
        reasons.append("final taskset source commit mismatch")
    if approval_binding.get("final_taskset_release_id") != (
        final_taskset.release_id
    ):
        reasons.append("approval binding final-taskset mismatch")
    if approval_binding.get("taskset_amendment_id") != (
        final_taskset.amendment_id
    ):
        reasons.append("approval binding taskset-amendment mismatch")
    if approval_binding.get("semantic_migration_report_id") != (
        migration_report.get("report_id")
    ):
        reasons.append("approval binding semantic-migration mismatch")
    if approval_binding.get("task_semantic_smoke_report_id") != (
        final_taskset.task_semantic_smoke_report_id
    ):
        reasons.append("approval binding task-semantic-smoke mismatch")
    if not migration_ok:
        reasons.append("semantic migration is ineligible")
    if not blueprint_ok:
        reasons.append("Blueprint validation is ineligible")
    if blueprint_validation.get("blueprint_id") != (
        approval_binding.get("blueprint_id")
    ):
        reasons.append("Blueprint/approval identity mismatch")
    if not readiness_ok:
        reasons.append("acquisition readiness is ineligible")
    if acquisition_readiness.get("source_commit") != source_commit:
        reasons.append("readiness source commit mismatch")
    if acquisition_readiness.get("task_asset_validation_report_id") != (
        final_taskset.task_asset_validation_report_id
    ):
        reasons.append("readiness task-asset report mismatch")
    if acquisition_readiness.get("final_taskset_release_id") != (
        final_taskset.release_id
    ):
        reasons.append("readiness final-taskset mismatch")
    epoch_id = str(closed_model_epoch.get("epoch_id", ""))
    if closed_model_epoch.get("status") != "closed" or not epoch_id:
        reasons.append("model epoch is not validly closed")
    if acquisition_readiness.get("model_epoch_id") != epoch_id:
        reasons.append("readiness/model-epoch mismatch")

    permitted = not reasons
    return PreAcquisitionGateReport(
        source_commit=source_commit,
        final_taskset_release_id=final_taskset.release_id,
        taskset_amendment_id=final_taskset.amendment_id,
        semantic_migration_report_id=str(
            migration_report.get("report_id", "")
        ),
        blueprint_id=str(approval_binding.get("blueprint_id", "")),
        approval_binding_id=str(approval_binding.get("binding_id", "")),
        blueprint_validation_report_id=str(
            blueprint_validation.get("report_id", "")
        ),
        closed_model_epoch_id=epoch_id,
        acquisition_readiness_id=str(
            acquisition_readiness.get("readiness_id", "")
        ),
        final_taskset_eligible=taskset_ok,
        migration_eligible=migration_ok,
        blueprint_validation_eligible=blueprint_ok,
        readiness_eligible=readiness_ok,
        phase_can_advance=permitted,
        formal_acquisition_permitted=permitted,
        reasons=tuple(dict.fromkeys(reasons)),
    ).with_id()
