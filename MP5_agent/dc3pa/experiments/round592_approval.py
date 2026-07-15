"""Strict approval and Blueprint validation contracts for Round 5.9.2."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .blueprint import RealExperimentBlueprint, sha256_file
from .final_taskset_release import FinalTasksetRelease


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class Round592ApprovalBinding:
    approval_record_id: str
    approved_by: str
    approved_at: str
    source_commit: str
    blueprint_id: str
    approved_blueprint_content_sha256: str
    final_taskset_release_id: str
    taskset_amendment_id: str
    task_semantic_smoke_report_id: str
    task_asset_validation_report_id: str
    runtime_task_tree_sha256: str
    semantic_migration_report_id: str
    schema_v2_design_id: str
    prompt_hashes: Mapping[str, str]
    controller_source_sha256: str
    controller_config_sha256: str
    evaluator_source_sha256: str
    evaluator_config_sha256: str
    model_id: str
    reasoning_effort: str
    mutable_alias_risk_acknowledged: bool
    maximum_model_epoch_hours: float
    model_epoch_policy_version: str
    execution_schedule_policy_version: str
    execution_schedule_salt: str
    schema_version: int = 1
    binding_id: str = ""

    def __post_init__(self) -> None:
        required = [
            value
            for name, value in asdict(self).items()
            if name not in {
                "binding_id",
                "mutable_alias_risk_acknowledged",
                "maximum_model_epoch_hours",
                "schema_version",
                "prompt_hashes",
            }
        ]
        if any(not str(value).strip() for value in required):
            raise ValueError("Round 5.9.2 approval binding is incomplete")
        if self.approved_by != "ZYF":
            raise ValueError("Round 5.9.2 approval must be from ZYF")
        if len(self.source_commit) != 40:
            raise ValueError("Approval must bind the full source commit")
        if self.model_id != "gpt-5.1" or self.reasoning_effort != "low":
            raise ValueError("Round 5.9.2 model policy mismatch")
        if not self.mutable_alias_risk_acknowledged:
            raise ValueError("Mutable gpt-5.1 alias risk must be acknowledged")
        if self.maximum_model_epoch_hours != 12.0:
            raise ValueError("Model Epoch policy must be twelve hours")
        if set(self.prompt_hashes) != {
            "planner", "confidence", "evaluation", "reflexion"
        } or any(len(value) != 64 for value in self.prompt_hashes.values()):
            raise ValueError("All four formal prompt hashes are required")
        expected = self.compute_id()
        if self.binding_id and self.binding_id != expected:
            raise ValueError("Round 5.9.2 approval binding hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("binding_id", None)
        payload["prompt_hashes"] = dict(sorted(self.prompt_hashes.items()))
        return payload

    def compute_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "Round592ApprovalBinding":
        return replace(self, binding_id=self.compute_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.binding_id else self.with_id()
        payload = item.payload_without_id()
        payload["binding_id"] = item.binding_id
        return payload


@dataclass(frozen=True)
class Round592BlueprintValidationReport:
    source_commit: str
    blueprint_id: str
    approval_binding_id: str
    final_taskset_release_id: str
    eligible: bool
    errors: tuple[str, ...]
    schema_version: int = 1
    report_id: str = ""

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("report_id", None)
        payload["errors"] = list(self.errors)
        return payload

    def compute_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "Round592BlueprintValidationReport":
        return replace(self, report_id=self.compute_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.report_id else self.with_id()
        payload = item.payload_without_id()
        payload["report_id"] = item.report_id
        return payload


def validate_round592_blueprint(
    *,
    blueprint: RealExperimentBlueprint,
    binding: Round592ApprovalBinding,
    final_taskset: FinalTasksetRelease,
    migration_report: Mapping[str, Any],
    task_asset_validation: Mapping[str, Any],
    semantic_smoke: Mapping[str, Any],
    schema_v2_design: Mapping[str, Any],
    prompt_identity: Mapping[str, Any],
    controller_source: str | Path,
    controller_config: str | Path,
    evaluator_source: str | Path,
    evaluator_config: str | Path,
) -> Round592BlueprintValidationReport:
    errors: list[str] = []
    checks = {
        "Blueprint source commit": blueprint.source_commit == binding.source_commit,
        "Blueprint ID": blueprint.blueprint_id == binding.blueprint_id,
        "Blueprint content approval": blueprint.author_approval.approved_blueprint_content_sha256 == binding.approved_blueprint_content_sha256,
        "final taskset": final_taskset.release_id == binding.final_taskset_release_id,
        "taskset amendment": final_taskset.amendment_id == binding.taskset_amendment_id,
        "semantic smoke": semantic_smoke.get("report_id") == binding.task_semantic_smoke_report_id == final_taskset.task_semantic_smoke_report_id,
        "task asset report": task_asset_validation.get("report_id") == binding.task_asset_validation_report_id == final_taskset.task_asset_validation_report_id,
        "runtime task tree": task_asset_validation.get("runtime_task_tree_sha256") == binding.runtime_task_tree_sha256 == final_taskset.runtime_task_tree_sha256,
        "semantic migration": migration_report.get("report_id") == binding.semantic_migration_report_id,
        "schema-v2 design": schema_v2_design.get("design_id") == binding.schema_v2_design_id,
        "prompt identity": prompt_identity.get("prompt_hashes") == dict(binding.prompt_hashes) == dict(blueprint.prompt_hashes),
        "Controller source": sha256_file(controller_source) == binding.controller_source_sha256,
        "Controller config": sha256_file(controller_config) == binding.controller_config_sha256,
        "Evaluator source": sha256_file(evaluator_source) == binding.evaluator_source_sha256,
        "Evaluator config": sha256_file(evaluator_config) == binding.evaluator_config_sha256,
        "migration eligible": bool(migration_report.get("eligible")),
        "task assets eligible": bool(task_asset_validation.get("eligible")),
        "semantic smoke eligible": bool(semantic_smoke.get("eligible")),
        "final taskset eligible": final_taskset.eligible,
    }
    errors.extend(f"{name} mismatch" for name, passed in checks.items() if not passed)
    return Round592BlueprintValidationReport(
        source_commit=binding.source_commit,
        blueprint_id=blueprint.blueprint_id,
        approval_binding_id=binding.binding_id,
        final_taskset_release_id=final_taskset.release_id,
        eligible=not errors,
        errors=tuple(errors),
    ).with_id()


def load_round592_approval(path: str | Path) -> Round592ApprovalBinding:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return Round592ApprovalBinding(**payload)


__all__ = [
    "Round592ApprovalBinding",
    "Round592BlueprintValidationReport",
    "validate_round592_blueprint",
    "load_round592_approval",
]
