"""Full-environment gate before formal experience acquisition."""

from __future__ import annotations
import hashlib, json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence
from .final_taskset_release import FinalTasksetRelease
from .model_epoch import ModelEpoch
from .log_fallback import assert_readiness_receipts_are_natural
from .provider_model_alias import ProviderModelAliasPolicy


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class SeedProviderSmokeReceipt:
    receipt_id: str
    task: str
    difficulty: str
    requested_seed: str
    effective_seed: str
    process_exit_code: int
    environment_started: bool
    controller_started: bool
    requested_model: str
    returned_models: tuple[str, ...]
    model_profile_id: str
    reasoning_effort: str
    expected_provider_call_count: int
    actual_provider_call_count: int
    provider_call_count_matches_expected: bool
    formal_memory_used: bool
    technical_failure_count: int
    dry_run_root_guard_passed: bool
    trace_sha256: str
    fallback_enabled: bool = False
    fallback_triggered: bool = False
    total_injected_logs: int = 0
    provider_model_alias_policy_id: str = ""
    provider_model_identity_validation: str = "strict_identity_match"

    def __post_init__(self):
        if not self.receipt_id or not self.task or not self.difficulty:
            raise ValueError("Receipt identity is required")
        if min(self.expected_provider_call_count,
               self.actual_provider_call_count,
               self.technical_failure_count) < 0:
            raise ValueError("Counts must be nonnegative")

    def to_dict(self):
        value = asdict(self)
        value["returned_models"] = list(self.returned_models)
        return value


@dataclass(frozen=True)
class AcquisitionReadinessReport:
    blueprint_id: str
    source_commit: str
    final_taskset_release_id: str
    migration_report_id: str
    model_epoch_id: str
    dry_run_audit_sha256: str
    smoke_receipt_ids: tuple[str, ...]
    task_asset_validation_report_id: str
    minedojo_marker_passed: bool
    blueprint_validation_eligible: bool
    migration_eligible: bool
    model_epoch_closed_valid: bool
    dry_run_audit_eligible: bool
    task_asset_validation_eligible: bool
    eligible: bool
    reasons: tuple[str, ...]
    schema_version: int = 1
    readiness_id: str = ""

    def payload(self):
        value = asdict(self)
        value.pop("readiness_id", None)
        value["smoke_receipt_ids"] = list(self.smoke_receipt_ids)
        value["reasons"] = list(self.reasons)
        return value

    def compute_id(self):
        return hashlib.sha256(canonical(self.payload())).hexdigest()

    def with_id(self):
        return replace(self, readiness_id=self.compute_id())

    def to_dict(self):
        value = self.payload()
        value["readiness_id"] = self.readiness_id or self.compute_id()
        return value


def audit_readiness(*, blueprint_id: str, source_commit: str,
                    final_taskset: FinalTasksetRelease,
                    migration_report: Mapping[str, Any],
                    approval_binding: Mapping[str, Any],
                    task_asset_validation: Mapping[str, Any],
                    blueprint_validation: Mapping[str, Any],
                    model_epoch: ModelEpoch,
                    dry_run_audit: Mapping[str, Any],
                    dry_run_audit_sha256: str,
                    smoke_receipts: Sequence[SeedProviderSmokeReceipt],
                    minedojo_marker_passed: bool,
                    required_difficulties=("basic", "medium", "complex"),
                    provider_model_alias_policy: ProviderModelAliasPolicy | None = None,
                    ) -> AcquisitionReadinessReport:
    reasons = []
    migration_ok = bool(migration_report.get("eligible", False))
    blueprint_ok = bool(blueprint_validation.get("eligible", False))
    dry_ok = bool(dry_run_audit.get("eligible", False))
    task_assets_ok = bool(task_asset_validation.get("eligible", False))
    epoch_ok = model_epoch.status == "closed" and not model_epoch.invariant_errors()
    if not migration_ok:
        reasons.append("semantic migration is not eligible")
    if not final_taskset.eligible:
        reasons.append("final taskset release is not eligible")
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
    if approval_binding.get("task_semantic_smoke_report_id") != (
        final_taskset.task_semantic_smoke_report_id
    ):
        reasons.append("approval binding task-semantic-smoke mismatch")
    if approval_binding.get("blueprint_id") != blueprint_id:
        reasons.append("approval binding Blueprint mismatch")
    approval_migration_id = approval_binding.get(
        "semantic_migration_report_id",
        approval_binding.get("migration_report_id"),
    )
    if approval_migration_id != migration_report.get("report_id"):
        reasons.append("approval binding migration mismatch")
    if not approval_binding.get("mutable_alias_risk_acknowledged", False):
        reasons.append("mutable-alias risk is not acknowledged")
    if not str(approval_binding.get("binding_id", "")):
        reasons.append("approval binding ID is missing")
    if provider_model_alias_policy is not None:
        try:
            provider_model_alias_policy.assert_activation_allowed(
                scope="natural_readiness",
                requested_model="gpt-5.1",
            )
        except ValueError as exc:
            reasons.append(str(exc))
        if approval_binding.get("provider_model_alias_policy_id") != (
            provider_model_alias_policy.policy_id
        ):
            reasons.append("approval binding provider model-alias policy mismatch")
        if model_epoch.policy.provider_model_alias_policy_id != (
            provider_model_alias_policy.policy_id
        ):
            reasons.append("model epoch provider model-alias policy mismatch")
    elif model_epoch.policy.provider_model_alias_policy_id:
        reasons.append("model epoch has an unapproved provider model-alias policy")
    if not task_assets_ok:
        reasons.append("task-asset validation is not eligible")
    if approval_binding.get("task_asset_validation_report_id") != (
        task_asset_validation.get("report_id")
    ):
        reasons.append("approval binding task-asset report mismatch")
    if approval_binding.get("runtime_task_tree_sha256") != (
        task_asset_validation.get("runtime_task_tree_sha256")
    ):
        reasons.append("approval binding runtime-task tree mismatch")
    if final_taskset.task_asset_validation_report_id != (
        task_asset_validation.get("report_id")
    ):
        reasons.append("final taskset task-asset report mismatch")
    if final_taskset.runtime_task_tree_sha256 != (
        task_asset_validation.get("runtime_task_tree_sha256")
    ):
        reasons.append("final taskset runtime-task tree mismatch")
    if task_asset_validation.get("source_commit") != source_commit:
        reasons.append("task-asset validation source commit mismatch")
    if not blueprint_ok:
        reasons.append("Blueprint validation is not eligible")
    if not dry_ok:
        reasons.append("tiny dry-run audit is not eligible")
    if not epoch_ok:
        reasons.append("model epoch is not validly closed")
    if model_epoch.blueprint_id != blueprint_id:
        reasons.append("model epoch Blueprint mismatch")
    if model_epoch.source_commit != source_commit:
        reasons.append("model epoch source commit mismatch")
    if blueprint_validation.get("blueprint_id") != blueprint_id:
        reasons.append("Blueprint validation identity mismatch")
    if blueprint_validation.get("source_commit") not in (None, "", source_commit):
        reasons.append("Blueprint validation source commit mismatch")
    if blueprint_validation.get("model_profile_id") not in (
        None, "", model_epoch.model_profile_id
    ):
        reasons.append("Blueprint validation profile mismatch")
    summary = dry_run_audit.get("summary", {})
    if summary.get("expected_entry_count") != 6 or summary.get("receipt_count") != 6:
        reasons.append("tiny dry-run audit is not six-entry complete")
    if not minedojo_marker_passed:
        reasons.append("MineDojo marker gate failed")
    if not smoke_receipts:
        reasons.append("no smoke receipts")
    try:
        assert_readiness_receipts_are_natural(
            [
                {
                    "entry_id": item.receipt_id,
                    "fallback_metrics": {
                        "fallback_enabled": item.fallback_enabled,
                        "fallback_triggered": item.fallback_triggered,
                        "total_injected_logs": item.total_injected_logs,
                    },
                }
                for item in smoke_receipts
            ]
        )
    except ValueError as exc:
        reasons.append(str(exc))
    missing = set(required_difficulties) - {x.difficulty for x in smoke_receipts}
    if missing:
        reasons.append(f"missing smoke difficulties: {sorted(missing)}")
    for item in smoke_receipts:
        prefix = item.receipt_id
        if item.process_exit_code != 0:
            reasons.append(f"{prefix}: nonzero exit")
        if not item.environment_started or not item.controller_started:
            reasons.append(f"{prefix}: environment/controller not started")
        if item.requested_seed != item.effective_seed:
            reasons.append(f"{prefix}: seed mismatch")
        if item.requested_model != "gpt-5.1":
            reasons.append(f"{prefix}: requested model mismatch")
        if provider_model_alias_policy is None:
            if not item.returned_models or set(item.returned_models) != {"gpt-5.1"}:
                reasons.append(f"{prefix}: returned model mismatch")
            if item.provider_model_alias_policy_id:
                reasons.append(f"{prefix}: unapproved provider model-alias policy")
        else:
            if item.provider_model_alias_policy_id != (
                provider_model_alias_policy.policy_id
            ):
                reasons.append(f"{prefix}: provider model-alias policy mismatch")
            if item.provider_model_identity_validation != "approved_alias_policy":
                reasons.append(f"{prefix}: provider model-alias mode mismatch")
            if not item.returned_models or not all(
                provider_model_alias_policy.accepts_returned_model(value)
                for value in item.returned_models
            ):
                reasons.append(f"{prefix}: returned model identity missing")
        if item.model_profile_id != model_epoch.model_profile_id:
            reasons.append(f"{prefix}: profile mismatch")
        if item.reasoning_effort != "low":
            reasons.append(f"{prefix}: effort mismatch")
        if item.expected_provider_call_count != item.actual_provider_call_count or (
            not item.provider_call_count_matches_expected
        ):
            reasons.append(f"{prefix}: provider call mismatch")
        if item.formal_memory_used:
            reasons.append(f"{prefix}: formal memory used")
        if item.technical_failure_count:
            reasons.append(f"{prefix}: technical failure")
        if not item.dry_run_root_guard_passed:
            reasons.append(f"{prefix}: dry-run root guard failed")
        if not item.trace_sha256:
            reasons.append(f"{prefix}: trace hash missing")
    return AcquisitionReadinessReport(
        blueprint_id=blueprint_id,
        source_commit=source_commit,
        final_taskset_release_id=final_taskset.release_id,
        migration_report_id=str(migration_report.get("report_id", "")),
        model_epoch_id=model_epoch.epoch_id,
        dry_run_audit_sha256=dry_run_audit_sha256,
        smoke_receipt_ids=tuple(x.receipt_id for x in smoke_receipts),
        task_asset_validation_report_id=str(
            task_asset_validation.get("report_id", "")
        ),
        minedojo_marker_passed=minedojo_marker_passed,
        blueprint_validation_eligible=blueprint_ok,
        migration_eligible=migration_ok,
        model_epoch_closed_valid=epoch_ok,
        dry_run_audit_eligible=dry_ok,
        task_asset_validation_eligible=task_assets_ok,
        eligible=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
    ).with_id()


def load_receipt(path: str | Path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    fallback_metrics = value.get("fallback_metrics")
    if not isinstance(fallback_metrics, Mapping):
        raise ValueError("Readiness receipt is missing structured fallback metrics")
    metadata = value.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ValueError("Readiness receipt metadata must be an object")
    selected = {
        "receipt_id": value.get("receipt_id") or value.get("truth_receipt_id", ""),
        "task": value.get("task", ""),
        "difficulty": value.get("difficulty", ""),
        "requested_seed": value.get("requested_seed", ""),
        "effective_seed": value.get("effective_seed", ""),
        "process_exit_code": value.get("process_exit_code", 1),
        "environment_started": value.get("environment_started", False),
        "controller_started": value.get("controller_started", False),
        "requested_model": value.get("requested_model", ""),
        "returned_models": tuple(value.get("returned_models", ())),
        "model_profile_id": value.get("model_profile_id", ""),
        "reasoning_effort": value.get("reasoning_effort", ""),
        "expected_provider_call_count": value.get("expected_provider_call_count", 0),
        "actual_provider_call_count": value.get("actual_provider_call_count", 0),
        "provider_call_count_matches_expected": value.get(
            "provider_call_count_matches_expected", False
        ),
        "formal_memory_used": value.get("formal_memory_used", True),
        "technical_failure_count": value.get("technical_failure_count", 1),
        "dry_run_root_guard_passed": value.get("dry_run_root_guard_passed", False),
        "trace_sha256": value.get("trace_sha256", ""),
        "fallback_enabled": bool(
            fallback_metrics.get("fallback_enabled", False)
        ),
        "fallback_triggered": bool(
            fallback_metrics.get("fallback_triggered", False)
        ),
        "total_injected_logs": int(
            fallback_metrics.get("total_injected_logs", 0) or 0
        ),
        "provider_model_alias_policy_id": str(
            metadata.get("provider_model_alias_policy_id", "")
        ),
        "provider_model_identity_validation": str(
            metadata.get(
                "provider_model_identity_validation",
                "strict_identity_match",
            )
        ),
    }
    return SeedProviderSmokeReceipt(**selected)
