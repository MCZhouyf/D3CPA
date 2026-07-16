"""Immutable approval and Blueprint validation for Round 5.9.4."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .blueprint import RealExperimentBlueprint
from .formal_bootstrap_authorization import (
    OLD_GATE_ID,
    ZYF_APPROVAL_SHA256,
)
from .formal_bootstrap_amendment import (
    MODEL_IDENTITY_APPROVAL_SHA256,
    RECORD_ONLY_IDENTITY_POLICY,
    STABLE_IDENTITY_POLICY,
)


SCHEMA_VERSION = 1
EXPECTED_MODEL = "gpt-5.1"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class FormalBootstrapApprovalBinding:
    binding_name: str
    source_commit: str
    blueprint_id: str
    approved_blueprint_content_sha256: str
    zyf_approval_sha256: str
    formal_log_bootstrap_policy_id: str
    formal_bootstrap_amendment_id: str
    previous_preacquisition_gate_id: str
    final_taskset_release_id: str
    semantic_migration_report_id: str
    controller_source_sha256: str
    evaluator_source_sha256: str
    task_catalog_sha256: str
    final_seeds_sha256: str
    prompt_hashes: Mapping[str, str]
    requested_model: str
    returned_identity_policy: str
    requested_returned_equality_required: bool
    all_formal_methods_use_bootstrap: bool
    all_formal_scopes_use_bootstrap: bool
    memory_records_bootstrap_metadata: bool
    development_records_bootstrap_metadata: bool
    final_results_report_natural_and_assisted_separately: bool
    prompts_changed: bool
    controller_success_logic_changed: bool
    evaluator_success_logic_changed: bool
    task_catalog_changed: bool
    final_seeds_changed: bool
    holdout_opened: bool
    model_identity_approval_sha256: str = ""
    schema_version: int = SCHEMA_VERSION
    binding_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported formal approval schema")
        required = (
            self.binding_name,
            self.source_commit,
            self.blueprint_id,
            self.approved_blueprint_content_sha256,
            self.formal_log_bootstrap_policy_id,
            self.formal_bootstrap_amendment_id,
            self.final_taskset_release_id,
            self.semantic_migration_report_id,
            self.controller_source_sha256,
            self.evaluator_source_sha256,
            self.task_catalog_sha256,
            self.final_seeds_sha256,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Formal approval binding identity is incomplete")
        if self.zyf_approval_sha256 != ZYF_APPROVAL_SHA256:
            raise ValueError("ZYF approval SHA256 mismatch")
        if self.previous_preacquisition_gate_id != OLD_GATE_ID:
            raise ValueError("Previous Pre-Acquisition gate mismatch")
        if self.requested_model != EXPECTED_MODEL:
            raise ValueError("Requested model must remain gpt-5.1")
        if self.returned_identity_policy not in {
            STABLE_IDENTITY_POLICY,
            RECORD_ONLY_IDENTITY_POLICY,
        }:
            raise ValueError("Returned-model identity policy mismatch")
        if self.returned_identity_policy == RECORD_ONLY_IDENTITY_POLICY and (
            self.model_identity_approval_sha256
            != MODEL_IDENTITY_APPROVAL_SHA256
        ):
            raise ValueError("Record-only identity approval SHA256 mismatch")
        if self.requested_returned_equality_required:
            raise ValueError("Requested/returned string equality is not required")
        if not self.prompt_hashes:
            raise ValueError("Prompt hash bundle is required")
        required_guards = (
            self.all_formal_methods_use_bootstrap,
            self.all_formal_scopes_use_bootstrap,
            self.memory_records_bootstrap_metadata,
            self.development_records_bootstrap_metadata,
            self.final_results_report_natural_and_assisted_separately,
        )
        if not all(required_guards):
            raise ValueError("Formal bootstrap scope/data safeguards are incomplete")
        protected_changes = (
            self.prompts_changed,
            self.controller_success_logic_changed,
            self.evaluator_success_logic_changed,
            self.task_catalog_changed,
            self.final_seeds_changed,
            self.holdout_opened,
        )
        if any(protected_changes):
            raise ValueError("Formal approval changes protected experiment content")
        expected = self.compute_binding_id()
        if self.binding_id and self.binding_id != expected:
            raise ValueError("Formal approval binding hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("binding_id", None)
        payload["prompt_hashes"] = dict(sorted(self.prompt_hashes.items()))
        return payload

    def compute_binding_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalBootstrapApprovalBinding":
        return replace(self, binding_id=self.compute_binding_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.binding_id else self.with_id()
        return {**item.payload_without_id(), "binding_id": item.binding_id}


@dataclass(frozen=True)
class FormalBootstrapBlueprintValidation:
    source_commit: str
    blueprint_id: str
    approval_binding_id: str
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    eligible: bool
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    report_id: str = ""

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("report_id", None)
        payload["errors"] = list(self.errors)
        return payload

    def compute_report_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalBootstrapBlueprintValidation":
        return replace(self, report_id=self.compute_report_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.report_id else self.with_id()
        return {**item.payload_without_id(), "report_id": item.report_id}


def validate_formal_bootstrap_blueprint(
    *,
    blueprint: RealExperimentBlueprint,
    binding: FormalBootstrapApprovalBinding,
    policy: Mapping[str, Any],
    amendment: Mapping[str, Any],
    controller_source: str | Path,
    evaluator_source: str | Path,
) -> FormalBootstrapBlueprintValidation:
    errors: list[str] = []
    blueprint.validate_author_approval()
    blueprint_id = blueprint.blueprint_id or blueprint.compute_blueprint_id()
    expected = {
        "source commit": (binding.source_commit, blueprint.source_commit),
        "Blueprint": (binding.blueprint_id, blueprint_id),
        "Blueprint content": (
            binding.approved_blueprint_content_sha256,
            blueprint.content_sha256_before_approval(),
        ),
        "prompt hashes": (
            dict(binding.prompt_hashes),
            dict(blueprint.prompt_hashes),
        ),
        "policy": (
            binding.formal_log_bootstrap_policy_id,
            policy.get("policy_id"),
        ),
        "amendment": (
            binding.formal_bootstrap_amendment_id,
            amendment.get("amendment_id"),
        ),
        "amendment policy": (
            amendment.get("formal_log_bootstrap_policy_id"),
            policy.get("policy_id"),
        ),
        "Controller source": (
            binding.controller_source_sha256,
            sha256_file(controller_source),
        ),
        "Evaluator source": (
            binding.evaluator_source_sha256,
            sha256_file(evaluator_source),
        ),
    }
    for name, (actual, wanted) in expected.items():
        if actual != wanted:
            errors.append(f"{name} mismatch")
    if blueprint.author_approval.approval_record_id != (
        "DC3PA-ZYF-FORMAL-LOG-BOOTSTRAP-005"
    ):
        errors.append("Blueprint author approval record mismatch")
    return FormalBootstrapBlueprintValidation(
        source_commit=blueprint.source_commit,
        blueprint_id=blueprint_id,
        approval_binding_id=binding.binding_id,
        bootstrap_policy_id=str(policy.get("policy_id", "")),
        bootstrap_amendment_id=str(amendment.get("amendment_id", "")),
        eligible=not errors,
        errors=tuple(errors),
    ).with_id()


def load_formal_bootstrap_approval(
    path: str | Path,
) -> FormalBootstrapApprovalBinding:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Formal approval binding must be a JSON object")
    binding = FormalBootstrapApprovalBinding(**dict(payload))
    if not binding.binding_id:
        raise ValueError("Formal approval binding must be frozen")
    return binding
