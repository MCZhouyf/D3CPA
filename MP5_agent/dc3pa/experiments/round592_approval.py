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
    provider_model_alias_policy_id: str = ""
    provider_model_alias_approval_sha256: str = ""
    returned_model_identity_match_required: bool = True
    experiment_approval_record_id: str = ""
    controller_revision_id: str = ""
    log_fallback_policy_id: str = ""
    log_fallback_approval_sha256: str = ""
    fallback_allowed_scopes: tuple[str, ...] = ()
    fallback_forbidden_scopes: tuple[str, ...] = ()
    natural_readiness_campaign_id: str = ""
    paired_dry_run_protocol_id: str = ""
    fallback_assisted_runs_excluded_from_readiness: bool = False
    fallback_assisted_runs_excluded_from_paper_performance: bool = False

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
                "provider_model_alias_policy_id",
                "provider_model_alias_approval_sha256",
                "returned_model_identity_match_required",
                "experiment_approval_record_id",
                "controller_revision_id",
                "log_fallback_policy_id",
                "log_fallback_approval_sha256",
                "fallback_allowed_scopes",
                "fallback_forbidden_scopes",
                "natural_readiness_campaign_id",
                "paired_dry_run_protocol_id",
                "fallback_assisted_runs_excluded_from_readiness",
                "fallback_assisted_runs_excluded_from_paper_performance",
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
        if self.provider_model_alias_policy_id:
            if len(self.provider_model_alias_policy_id) != 64:
                raise ValueError("Provider model-alias policy ID is invalid")
            if len(self.provider_model_alias_approval_sha256) != 64:
                raise ValueError("Provider model-alias approval SHA256 is invalid")
            if self.returned_model_identity_match_required:
                raise ValueError("Alias approval must waive returned-model equality")
        elif (
            self.provider_model_alias_approval_sha256
            or not self.returned_model_identity_match_required
        ):
            raise ValueError("Returned-model equality waiver is not policy-bound")
        round593_values = (
            self.experiment_approval_record_id,
            self.controller_revision_id,
            self.log_fallback_policy_id,
            self.log_fallback_approval_sha256,
            self.natural_readiness_campaign_id,
            self.paired_dry_run_protocol_id,
        )
        if any(round593_values):
            if not all(round593_values):
                raise ValueError("Round 5.9.3 approval boundary is incomplete")
            for label, value in (
                ("Controller revision", self.controller_revision_id),
                ("Log Fallback policy", self.log_fallback_policy_id),
                ("Log Fallback approval", self.log_fallback_approval_sha256),
                ("natural readiness campaign", self.natural_readiness_campaign_id),
                ("paired dry-run protocol", self.paired_dry_run_protocol_id),
            ):
                if len(value) != 64:
                    raise ValueError(f"{label} ID/SHA256 is invalid")
            if set(self.fallback_allowed_scopes) != {"diagnostic_dry_run"}:
                raise ValueError("Log Fallback allowed scope is invalid")
            required_forbidden = {
                "dev_holdout", "dev_train", "dev_tune", "final_evaluation",
                "formal_acquisition", "fusion_fitting", "readiness_dry_run",
                "task_semantic_smoke",
            }
            if set(self.fallback_forbidden_scopes) != required_forbidden:
                raise ValueError("Log Fallback forbidden scopes are incomplete")
            if not self.fallback_assisted_runs_excluded_from_readiness:
                raise ValueError("Fallback-assisted runs must be excluded from readiness")
            if not self.fallback_assisted_runs_excluded_from_paper_performance:
                raise ValueError(
                    "Fallback-assisted runs must be excluded from paper performance"
                )
        elif (
            self.fallback_allowed_scopes
            or self.fallback_forbidden_scopes
            or self.fallback_assisted_runs_excluded_from_readiness
            or self.fallback_assisted_runs_excluded_from_paper_performance
        ):
            raise ValueError("Round 5.9.3 fallback boundary is not revision-bound")
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
        if not self.provider_model_alias_policy_id:
            payload.pop("provider_model_alias_policy_id", None)
            payload.pop("provider_model_alias_approval_sha256", None)
            payload.pop("returned_model_identity_match_required", None)
        if not self.controller_revision_id:
            for key in (
                "experiment_approval_record_id",
                "controller_revision_id",
                "log_fallback_policy_id",
                "log_fallback_approval_sha256",
                "fallback_allowed_scopes",
                "fallback_forbidden_scopes",
                "natural_readiness_campaign_id",
                "paired_dry_run_protocol_id",
                "fallback_assisted_runs_excluded_from_readiness",
                "fallback_assisted_runs_excluded_from_paper_performance",
            ):
                payload.pop(key, None)
        else:
            payload["fallback_allowed_scopes"] = sorted(
                self.fallback_allowed_scopes
            )
            payload["fallback_forbidden_scopes"] = sorted(
                self.fallback_forbidden_scopes
            )
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
    controller_revision: Mapping[str, Any] | None = None,
    log_fallback_policy: Mapping[str, Any] | None = None,
    natural_readiness_campaign: Mapping[str, Any] | None = None,
    paired_dry_run_protocol: Mapping[str, Any] | None = None,
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
    if binding.controller_revision_id:
        checks.update(
            {
                "Controller revision": bool(controller_revision)
                and controller_revision.get("revision_id")
                == binding.controller_revision_id,
                "Controller revision source": bool(controller_revision)
                and controller_revision.get("source_commit")
                == binding.source_commit,
                "Log Fallback policy": bool(log_fallback_policy)
                and log_fallback_policy.get("policy_id")
                == binding.log_fallback_policy_id,
                "natural readiness campaign": bool(natural_readiness_campaign)
                and natural_readiness_campaign.get("campaign_id")
                == binding.natural_readiness_campaign_id,
                "natural readiness source": bool(natural_readiness_campaign)
                and natural_readiness_campaign.get("source_commit")
                == binding.source_commit,
                "paired dry-run protocol": bool(paired_dry_run_protocol)
                and paired_dry_run_protocol.get("protocol_id")
                == binding.paired_dry_run_protocol_id,
                "paired protocol source": bool(paired_dry_run_protocol)
                and paired_dry_run_protocol.get("source_commit")
                == binding.source_commit,
                "paired protocol natural campaign": bool(paired_dry_run_protocol)
                and paired_dry_run_protocol.get("natural_campaign_id")
                == binding.natural_readiness_campaign_id,
                "paired protocol fallback policy": bool(paired_dry_run_protocol)
                and paired_dry_run_protocol.get("fallback_policy_id")
                == binding.log_fallback_policy_id,
            }
        )
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
