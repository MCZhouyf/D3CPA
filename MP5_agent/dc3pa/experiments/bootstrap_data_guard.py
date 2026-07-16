"""Prevent mixing natural and formal-bootstrap experiment data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class BootstrapDataBinding:
    binding_name: str
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    source_commit: str
    blueprint_id: str
    scope: str
    method_id: str
    task_catalog_sha256: str
    prompt_hash_bundle_id: str
    controller_identity_sha256: str
    evaluator_identity_sha256: str
    memory_snapshot_id: str = ""
    memory_snapshot_sha256: str = ""
    all_records_require_policy_id: bool = True
    mixed_bootstrap_conditions_forbidden: bool = True
    natural_and_assisted_success_must_be_separate: bool = True
    schema_version: int = SCHEMA_VERSION
    binding_id: str = ""

    def __post_init__(self) -> None:
        required = (
            self.binding_name,
            self.bootstrap_policy_id,
            self.bootstrap_amendment_id,
            self.source_commit,
            self.blueprint_id,
            self.scope,
            self.method_id,
            self.task_catalog_sha256,
            self.prompt_hash_bundle_id,
            self.controller_identity_sha256,
            self.evaluator_identity_sha256,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Bootstrap data binding is incomplete")
        if not all(
            (
                self.all_records_require_policy_id,
                self.mixed_bootstrap_conditions_forbidden,
                self.natural_and_assisted_success_must_be_separate,
            )
        ):
            raise ValueError("Bootstrap data safeguards are incomplete")
        if bool(self.memory_snapshot_id) != bool(self.memory_snapshot_sha256):
            raise ValueError("Memory snapshot ID/SHA must appear together")
        expected = self.compute_binding_id()
        if self.binding_id and self.binding_id != expected:
            raise ValueError("Bootstrap data binding hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("binding_id", None)
        return payload

    def compute_binding_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "BootstrapDataBinding":
        return replace(self, binding_id=self.compute_binding_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.binding_id else self.with_id()
        payload = item.payload_without_id()
        payload["binding_id"] = item.binding_id
        return payload


def load_bootstrap_data_binding(path: str | Path) -> BootstrapDataBinding:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Bootstrap data binding must be a JSON object")
    binding = BootstrapDataBinding(**dict(payload))
    if not binding.binding_id:
        raise ValueError("Bootstrap data binding must be frozen")
    return binding


def assert_bootstrap_snapshot_binding(
    metadata: Mapping[str, Any],
    *,
    expected_policy_id: str,
    expected_amendment_id: str,
    expected_binding_id: str,
) -> None:
    expected = {
        "bootstrap_policy_id": expected_policy_id,
        "formal_bootstrap_amendment_id": expected_amendment_id,
        "bootstrap_data_binding_id": expected_binding_id,
    }
    mismatches = [
        key for key, value in expected.items() if metadata.get(key) != value
    ]
    if mismatches:
        raise ValueError(
            "Memory snapshot bootstrap binding mismatch: " + ", ".join(mismatches)
        )


@dataclass(frozen=True)
class BootstrapDatasetAudit:
    expected_policy_id: str
    expected_binding_id: str
    record_count: int
    policy_ids_observed: tuple[str, ...]
    binding_ids_observed: tuple[str, ...]
    natural_completion_count: int
    bootstrap_assisted_completion_count: int
    incomplete_count: int
    eligible: bool
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("audit_id", None)
        payload["policy_ids_observed"] = list(self.policy_ids_observed)
        payload["binding_ids_observed"] = list(self.binding_ids_observed)
        payload["errors"] = list(self.errors)
        return payload

    def compute_audit_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "BootstrapDatasetAudit":
        return replace(self, audit_id=self.compute_audit_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.audit_id else self.with_id()
        payload = item.payload_without_id()
        payload["audit_id"] = item.audit_id
        return payload


def audit_bootstrap_records(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_policy_id: str,
    expected_binding_id: str,
) -> BootstrapDatasetAudit:
    errors: list[str] = []
    policy_ids = sorted(
        {str(item.get("bootstrap_policy_id", "")) for item in records}
    )
    binding_ids = sorted(
        {str(item.get("bootstrap_data_binding_id", "")) for item in records}
    )
    natural = assisted = incomplete = 0

    for index, item in enumerate(records):
        label = f"record[{index}]"
        if item.get("bootstrap_policy_id") != expected_policy_id:
            errors.append(f"{label}: bootstrap policy mismatch")
        if item.get("bootstrap_data_binding_id") != expected_binding_id:
            errors.append(f"{label}: bootstrap data binding mismatch")
        for key in (
            "formal_bootstrap_amendment_id",
            "bootstrap_event_ids",
            "injected_log_count",
            "source_commit",
            "blueprint_id",
        ):
            if key not in item:
                errors.append(f"{label}: missing {key}")
        natural_flag = bool(item.get("natural_completion", False))
        assisted_flag = bool(
            item.get("bootstrap_assisted_completion", False)
        )
        task_completed = bool(item.get("task_completed", False))
        if natural_flag and assisted_flag:
            errors.append(f"{label}: completion classes overlap")
        if task_completed and not (natural_flag or assisted_flag):
            errors.append(f"{label}: completed task lacks completion class")
        if not task_completed and (natural_flag or assisted_flag):
            errors.append(f"{label}: incomplete task has completion class")
        if natural_flag:
            natural += 1
        elif assisted_flag:
            assisted += 1
        else:
            incomplete += 1

    if policy_ids != [expected_policy_id]:
        errors.append(f"mixed or missing policy IDs: {policy_ids}")
    if binding_ids != [expected_binding_id]:
        errors.append(f"mixed or missing binding IDs: {binding_ids}")

    return BootstrapDatasetAudit(
        expected_policy_id=expected_policy_id,
        expected_binding_id=expected_binding_id,
        record_count=len(records),
        policy_ids_observed=tuple(policy_ids),
        binding_ids_observed=tuple(binding_ids),
        natural_completion_count=natural,
        bootstrap_assisted_completion_count=assisted,
        incomplete_count=incomplete,
        eligible=not errors,
        errors=tuple(errors),
    ).with_id()
