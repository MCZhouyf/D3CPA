"""Fail-closed contracts for a fresh Round 5.12.6 confirmatory holdout."""

from __future__ import annotations

import fcntl
import hashlib
import inspect
import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .formal_acquisition_execution import TECHNICAL_FAILURE_CATEGORIES


SCHEMA_VERSION = 1
ASSIGNMENT_COUNT = 15
FROZEN_STRATA = {
    "basic": 3,
    "easy": 3,
    "medium": 3,
    "hard": 3,
    "complex": 3,
}
FROZEN_EXECUTION_BUDGET = {
    "action_step_timeout_seconds": 30,
    "episode_timeout_seconds": 3600,
    "max_execution_attempts": 4,
    "max_explore_steps": 120,
    "max_planning_replans": 4,
    "maximum_technical_retries_per_assignment": 2,
    "provider_maximum_retries": 3,
    "provider_request_timeout_seconds": 180.0,
}
PROTECTED_ARTIFACTS = frozenset(
    {
        "monotonic_fusion_candidate",
        "selected_l2_checkpoint",
        "fusion_feature_schema_direction",
        "confidence_calibration",
        "environment_mapping",
        "activation_policy",
        "paper_memory_v5",
        "active_task_catalog_tree",
        "planner_prompt_bundle",
        "controller_behavior",
        "evaluator_success_logic",
        "formal_log_bootstrap_policy",
        "execution_budget_profile",
        "technical_retry_policy",
    }
)
REQUIRED_AUTHORIZATION_STATEMENTS = (
    "observational_set_is_exploratory_only",
    "failed_prelaunch_set_is_permanently_retired",
    "historical_sets_cannot_be_copied_or_rerun",
    "one_replacement_confirmatory_holdout_is_authorized",
    "fusion_candidate_and_activation_policy_are_unchanged",
    "generator_cannot_read_observational_outcomes",
    "holdout_size_and_stratification_are_unchanged",
    "runtime_and_budget_are_frozen_before_generation",
    "new_ledger_may_be_opened_once_only",
    "post_holdout_fitting_and_tuning_are_forbidden",
    "final_evaluation_and_round6_remain_closed",
)


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _atomic_replace(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


@dataclass(frozen=True)
class ArtifactComparison:
    before_id: str
    before_sha256: str
    after_id: str
    after_sha256: str
    authorized_amendment_sha256: str = ""

    def __post_init__(self) -> None:
        if not all((self.before_id, self.before_sha256, self.after_id, self.after_sha256)):
            raise ValueError("Protected artifact comparison is incomplete")

    @property
    def unchanged(self) -> bool:
        return (
            self.before_id == self.after_id
            and self.before_sha256 == self.after_sha256
        )

    @property
    def eligible(self) -> bool:
        return self.unchanged or bool(self.authorized_amendment_sha256)


@dataclass(frozen=True)
class HoldoutPreflightRepairBinding:
    comparison_base_sha: str
    effective_source_sha: str
    protected_artifacts: Mapping[str, ArtifactComparison]
    allowed_source_changes: tuple[str, ...]
    technical_retry_baseline_amendment_sha256: str
    candidate_unchanged: bool
    activation_policy_unchanged: bool
    component_releases_unchanged: bool
    paper_memory_v5_unchanged: bool
    task_catalog_unchanged: bool
    controller_behavior_unchanged: bool
    evaluator_unchanged: bool
    prompt_bundle_unchanged: bool
    execution_budget_unchanged: bool
    only_preflight_path_or_authorized_retry_baseline_changed: bool
    schema_version: int = SCHEMA_VERSION
    binding_id: str = ""

    def __post_init__(self) -> None:
        if set(self.protected_artifacts) != PROTECTED_ARTIFACTS:
            raise ValueError("Protected artifact inventory is incomplete")
        amended = {
            name
            for name, item in self.protected_artifacts.items()
            if not item.unchanged
        }
        if amended - {"technical_retry_policy"}:
            raise ValueError("A protected scientific artifact changed across the repair")
        if not all(item.eligible for item in self.protected_artifacts.values()):
            raise ValueError("A protected artifact changed without authorization")
        retry = self.protected_artifacts["technical_retry_policy"]
        if amended and (
            retry.authorized_amendment_sha256
            != self.technical_retry_baseline_amendment_sha256
        ):
            raise ValueError("Technical retry amendment binding mismatch")
        if not amended and retry.authorized_amendment_sha256:
            raise ValueError("Unchanged retry policy cannot claim an amendment")
        required_flags = (
            self.candidate_unchanged,
            self.activation_policy_unchanged,
            self.component_releases_unchanged,
            self.paper_memory_v5_unchanged,
            self.task_catalog_unchanged,
            self.controller_behavior_unchanged,
            self.evaluator_unchanged,
            self.prompt_bundle_unchanged,
            self.execution_budget_unchanged,
            self.only_preflight_path_or_authorized_retry_baseline_changed,
        )
        if not all(required_flags):
            raise ValueError("Preflight repair binding is ineligible")
        if not all(
            (
                self.comparison_base_sha,
                self.effective_source_sha,
                self.technical_retry_baseline_amendment_sha256,
            )
        ):
            raise ValueError("Preflight repair identity is incomplete")
        expected = self.compute_binding_id()
        if self.binding_id and self.binding_id != expected:
            raise ValueError("Preflight repair binding hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("binding_id", None)
        payload["protected_artifacts"] = {
            key: asdict(value)
            for key, value in sorted(self.protected_artifacts.items())
        }
        payload["allowed_source_changes"] = list(self.allowed_source_changes)
        return payload

    def compute_binding_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "HoldoutPreflightRepairBinding":
        return replace(self, binding_id=self.compute_binding_id())


@dataclass(frozen=True)
class FinalConfirmatoryHoldoutRuntimeRelease:
    source_commit: str
    preflight_repair_binding_id: str
    protected_artifact_ids: Mapping[str, str]
    protected_artifact_sha256: Mapping[str, str]
    execution_budget: Mapping[str, Any]
    memory_readonly: bool
    evaluation_chain_enabled: bool
    fusion_shadow_only: bool
    formal_memory_writes_permitted: bool
    acquisition_writes_permitted: bool
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        if not self.source_commit or not self.preflight_repair_binding_id:
            raise ValueError("Confirmatory runtime identity is incomplete")
        if set(self.protected_artifact_ids) != PROTECTED_ARTIFACTS:
            raise ValueError("Confirmatory runtime artifact IDs are incomplete")
        if set(self.protected_artifact_sha256) != PROTECTED_ARTIFACTS:
            raise ValueError("Confirmatory runtime artifact hashes are incomplete")
        if dict(self.execution_budget) != FROZEN_EXECUTION_BUDGET:
            raise ValueError("Confirmatory execution budget changed")
        if not self.memory_readonly or not self.fusion_shadow_only:
            raise ValueError("Confirmatory runtime opened a protected behavior")
        if any(
            (
                self.evaluation_chain_enabled,
                self.formal_memory_writes_permitted,
                self.acquisition_writes_permitted,
            )
        ):
            raise ValueError("Confirmatory runtime opened a forbidden write or chain")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("Confirmatory runtime hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        payload["execution_budget"] = dict(sorted(self.execution_budget.items()))
        payload["protected_artifact_ids"] = dict(
            sorted(self.protected_artifact_ids.items())
        )
        payload["protected_artifact_sha256"] = dict(
            sorted(self.protected_artifact_sha256.items())
        )
        return payload

    def compute_release_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FinalConfirmatoryHoldoutRuntimeRelease":
        return replace(self, release_id=self.compute_release_id())


@dataclass(frozen=True)
class LockedConfirmatoryHoldoutExecutionManifest:
    source_commit: str
    authorization_id: str
    preflight_repair_binding_id: str
    runtime_release_id: str
    candidate_artifact_id: str
    candidate_artifact_sha256: str
    activation_policy_id: str
    activation_policy_sha256: str
    assignment_seal_id: str
    ledger_id: str
    paper_memory_v5_root_sha256: str
    active_taskset_catalog_sha256: str
    active_taskset_tree_sha256: str
    prompt_bundle_id: str
    controller_id: str
    evaluator_id: str
    evaluator_sha256: str
    bootstrap_policy_id: str
    technical_retry_policy_id: str
    execution_budget: Mapping[str, Any]
    github_actions_run_url: str
    source_worktree_clean: bool
    github_actions_green: bool
    holdout_outcomes_absent: bool
    schema_version: int = SCHEMA_VERSION
    manifest_id: str = ""

    def __post_init__(self) -> None:
        identities = (
            self.source_commit,
            self.authorization_id,
            self.preflight_repair_binding_id,
            self.runtime_release_id,
            self.candidate_artifact_id,
            self.candidate_artifact_sha256,
            self.activation_policy_id,
            self.activation_policy_sha256,
            self.assignment_seal_id,
            self.ledger_id,
            self.paper_memory_v5_root_sha256,
            self.active_taskset_catalog_sha256,
            self.active_taskset_tree_sha256,
            self.prompt_bundle_id,
            self.controller_id,
            self.evaluator_id,
            self.evaluator_sha256,
            self.bootstrap_policy_id,
            self.technical_retry_policy_id,
            self.github_actions_run_url,
        )
        if not all(identities):
            raise ValueError("Confirmatory execution manifest is incomplete")
        if dict(self.execution_budget) != FROZEN_EXECUTION_BUDGET:
            raise ValueError("Confirmatory execution manifest budget changed")
        if not all(
            (
                self.source_worktree_clean,
                self.github_actions_green,
                self.holdout_outcomes_absent,
            )
        ):
            raise ValueError("Confirmatory execution preconditions are not frozen")
        expected = self.compute_manifest_id()
        if self.manifest_id and self.manifest_id != expected:
            raise ValueError("Confirmatory execution manifest hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("manifest_id", None)
        payload["execution_budget"] = dict(sorted(self.execution_budget.items()))
        return payload

    def compute_manifest_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "LockedConfirmatoryHoldoutExecutionManifest":
        return replace(self, manifest_id=self.compute_manifest_id())


@dataclass(frozen=True)
class PriorHoldoutEntry:
    set_id: str
    status: str
    assignment_manifest_id: str
    assignment_manifest_sha256: str
    seal_id: str
    seal_sha256: str
    ledger_id: str
    ledger_state: str
    assignment_count: int
    outcomes_observed: bool
    formal_activation_use_forbidden: bool
    candidate_policy_tuning_forbidden: bool
    assignment_reuse_forbidden: bool
    ledger_reopen_forbidden: bool

    def __post_init__(self) -> None:
        if not all(
            (
                self.set_id,
                self.status,
                self.assignment_manifest_id,
                self.assignment_manifest_sha256,
                self.seal_id,
                self.seal_sha256,
                self.ledger_id,
                self.ledger_state,
            )
        ):
            raise ValueError("Prior holdout entry is incomplete")
        if self.assignment_count != ASSIGNMENT_COUNT:
            raise ValueError("Prior holdout assignment count changed")
        if not all(
            (
                self.formal_activation_use_forbidden,
                self.candidate_policy_tuning_forbidden,
                self.assignment_reuse_forbidden,
                self.ledger_reopen_forbidden,
            )
        ):
            raise ValueError("Prior holdout exclusion is incomplete")
        if self.status == "observational_only":
            if not self.outcomes_observed or self.ledger_state != "claimed":
                raise ValueError("Observational holdout status changed")
        elif self.status == "permanently_retired":
            if self.outcomes_observed or self.ledger_state != "failed_prelaunch":
                raise ValueError("Failed-prelaunch holdout status changed")
        else:
            raise ValueError("Unknown prior holdout status")


@dataclass(frozen=True)
class PriorHoldoutExclusionRegistry:
    observational: PriorHoldoutEntry
    failed_prelaunch: PriorHoldoutEntry
    schema_version: int = SCHEMA_VERSION
    registry_id: str = ""

    def __post_init__(self) -> None:
        if self.observational.status != "observational_only":
            raise ValueError("Observational set is not quarantined")
        if self.failed_prelaunch.status != "permanently_retired":
            raise ValueError("Failed-prelaunch set is not retired")
        if self.observational.set_id == self.failed_prelaunch.set_id:
            raise ValueError("Historical holdout sets are not distinct")
        expected = self.compute_registry_id()
        if self.registry_id and self.registry_id != expected:
            raise ValueError("Prior holdout registry hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("registry_id", None)
        return payload

    def compute_registry_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "PriorHoldoutExclusionRegistry":
        return replace(self, registry_id=self.compute_registry_id())


@dataclass(frozen=True)
class ReplacementHoldoutDesign:
    task_pool_id: str
    task_pool_sha256: str
    assignment_count: int
    strata: Mapping[str, int]
    selection_rule: str
    observational_outcomes_available: bool
    schema_version: int = SCHEMA_VERSION
    design_id: str = ""

    def __post_init__(self) -> None:
        if not self.task_pool_id or not self.task_pool_sha256:
            raise ValueError("Replacement holdout task pool is not bound")
        if self.assignment_count != ASSIGNMENT_COUNT:
            raise ValueError("Replacement holdout size changed")
        if dict(self.strata) != FROZEN_STRATA:
            raise ValueError("Replacement holdout strata changed")
        if self.selection_rule != "one_frozen_task_per_stratum_three_seeds":
            raise ValueError("Replacement holdout selection rule changed")
        if self.observational_outcomes_available:
            raise ValueError("Outcome labels are visible to the holdout design")
        expected = self.compute_design_id()
        if self.design_id and self.design_id != expected:
            raise ValueError("Replacement holdout design hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("design_id", None)
        payload["strata"] = dict(sorted(self.strata.items()))
        return payload

    def compute_design_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "ReplacementHoldoutDesign":
        return replace(self, design_id=self.compute_design_id())


@dataclass(frozen=True)
class FreshHoldoutSeedNamespace:
    namespace_id: str
    salt_commitment_sha256: str
    seed_domain_start: int
    seed_domain_size: int
    prior_domain_audit_id: str

    def __post_init__(self) -> None:
        if not self.namespace_id or not self.salt_commitment_sha256:
            raise ValueError("Fresh seed namespace is incomplete")
        if self.seed_domain_start <= 0 or self.seed_domain_size < ASSIGNMENT_COUNT:
            raise ValueError("Fresh seed namespace domain is invalid")
        if self.seed_domain_start + self.seed_domain_size >= 2**31:
            raise ValueError("Fresh seed namespace exceeds the simulator seed range")
        if not self.prior_domain_audit_id:
            raise ValueError("Fresh seed namespace lacks a disjointness audit")


@dataclass(frozen=True)
class ReplacementHoldoutAuthorization:
    approved_by: str
    approved_at: str
    approval_status: str
    approved_source_sha: str
    preflight_repair_binding_id: str
    runtime_release_id: str
    exclusion_registry_id: str
    design_id: str
    namespace_id: str
    namespace_commitment_sha256: str
    bound_artifact_ids: Mapping[str, str]
    bound_artifact_sha256: Mapping[str, str]
    statements: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    authorization_id: str = ""

    def __post_init__(self) -> None:
        if not all(
            (
                self.approved_by,
                self.approved_at,
                self.approved_source_sha,
                self.preflight_repair_binding_id,
                self.runtime_release_id,
                self.exclusion_registry_id,
                self.design_id,
                self.namespace_id,
                self.namespace_commitment_sha256,
            )
        ):
            raise ValueError("Replacement holdout authorization is incomplete")
        if self.approved_by != "ZYF" or self.approval_status != "approved":
            raise ValueError("Replacement holdout lacks explicit ZYF approval")
        if tuple(self.statements) != REQUIRED_AUTHORIZATION_STATEMENTS:
            raise ValueError("Replacement holdout authorization statements changed")
        if set(self.bound_artifact_ids) != PROTECTED_ARTIFACTS:
            raise ValueError("Authorization does not bind every protected artifact")
        if set(self.bound_artifact_sha256) != PROTECTED_ARTIFACTS:
            raise ValueError("Authorization does not bind every protected hash")
        expected = self.compute_authorization_id()
        if self.authorization_id and self.authorization_id != expected:
            raise ValueError("Replacement authorization hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("authorization_id", None)
        payload["bound_artifact_ids"] = dict(sorted(self.bound_artifact_ids.items()))
        payload["bound_artifact_sha256"] = dict(
            sorted(self.bound_artifact_sha256.items())
        )
        payload["statements"] = list(self.statements)
        return payload

    def compute_authorization_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "ReplacementHoldoutAuthorization":
        return replace(self, authorization_id=self.compute_authorization_id())


def generate_fresh_assignments(
    *,
    authorization: ReplacementHoldoutAuthorization,
    design: ReplacementHoldoutDesign,
    namespace: FreshHoldoutSeedNamespace,
    namespace_secret: bytes,
    task_by_stratum: Mapping[str, str],
    excluded_task_seed_pairs: frozenset[tuple[str, str]],
    excluded_seed_values: frozenset[int],
) -> tuple[Mapping[str, Any], ...]:
    """Generate from frozen identities only; outcome data is not an input."""
    if not authorization.authorization_id:
        raise ValueError("A hash-bound author authorization is required")
    if authorization.authorization_id != authorization.compute_authorization_id():
        raise ValueError("Replacement authorization hash mismatch")
    if not design.design_id:
        raise ValueError("A frozen replacement design is required")
    if authorization.design_id != (design.design_id or design.compute_design_id()):
        raise ValueError("Authorization/design mismatch")
    if authorization.namespace_id != namespace.namespace_id:
        raise ValueError("Authorization/namespace mismatch")
    if authorization.namespace_commitment_sha256 != namespace.salt_commitment_sha256:
        raise ValueError("Authorization/namespace commitment mismatch")
    if hashlib.sha256(namespace_secret).hexdigest() != namespace.salt_commitment_sha256:
        raise ValueError("Seed namespace secret does not match its commitment")
    if set(task_by_stratum) != set(FROZEN_STRATA):
        raise ValueError("Frozen holdout task strata are incomplete")
    domain_end = namespace.seed_domain_start + namespace.seed_domain_size
    if any(
        namespace.seed_domain_start <= seed < domain_end
        for seed in excluded_seed_values
    ):
        raise ValueError("Fresh seed namespace overlaps a historical seed domain")

    assignments: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    sequence = 0
    for difficulty in FROZEN_STRATA:
        task = str(task_by_stratum[difficulty]).strip()
        if not task:
            raise ValueError("Frozen holdout task is empty")
        for replicate in range(FROZEN_STRATA[difficulty]):
            digest = hashlib.sha256(
                b"\0".join(
                    (
                        namespace_secret,
                        namespace.namespace_id.encode("utf-8"),
                        task.encode("utf-8"),
                        str(replicate).encode("ascii"),
                    )
                )
            ).digest()
            offset = int.from_bytes(digest[:8], "big") % namespace.seed_domain_size
            seed = str(namespace.seed_domain_start + offset)
            pair = (task, seed)
            if pair in seen:
                raise ValueError("Fresh deterministic assignments collide")
            if pair in excluded_task_seed_pairs:
                raise ValueError("Fresh assignment overlaps a prior task-seed pair")
            seen.add(pair)
            assignments.append(
                {
                    "difficulty": difficulty,
                    "group_id": (
                        f"confirmatory:{namespace.namespace_id}:"
                        f"{difficulty}:{task}:{replicate + 1}"
                    ),
                    "role": "dev_holdout",
                    "seed": seed,
                    "sequence_index": sequence,
                    "task": task,
                }
            )
            sequence += 1
    if len(assignments) != ASSIGNMENT_COUNT:
        raise AssertionError("Fresh assignment count invariant failed")
    return tuple(assignments)


@dataclass(frozen=True)
class ConfirmatoryPreflightReceipt:
    source_and_artifacts_passed: bool
    active_taskset_passed: bool
    sealed_metadata_passed: bool
    runtime_task_files_checked: int
    formal_task_files_checked: int
    assignments_read: bool
    assignments_decrypted: bool
    ledger_claimed: bool
    minedojo_started: bool
    receipt_id: str = ""

    def __post_init__(self) -> None:
        if not all(
            (
                self.source_and_artifacts_passed,
                self.active_taskset_passed,
                self.sealed_metadata_passed,
            )
        ):
            raise ValueError("Confirmatory preflight did not pass")
        if (self.runtime_task_files_checked, self.formal_task_files_checked) != (
            50,
            50,
        ):
            raise ValueError("Confirmatory preflight did not check all task files")
        if any(
            (
                self.assignments_read,
                self.assignments_decrypted,
                self.ledger_claimed,
                self.minedojo_started,
            )
        ):
            raise ValueError("Confirmatory preflight opened a protected phase")
        expected = self.compute_receipt_id()
        if self.receipt_id and self.receipt_id != expected:
            raise ValueError("Confirmatory preflight receipt hash mismatch")

    def compute_receipt_id(self) -> str:
        payload = asdict(self)
        payload.pop("receipt_id", None)
        return _sha(payload)


def create_fresh_single_use_ledger(
    path: str | Path,
    *,
    manifest_id: str,
    seal_id: str,
    authorization_id: str,
) -> Mapping[str, Any]:
    if not all((manifest_id, seal_id, authorization_id)):
        raise ValueError("Confirmatory ledger binding is incomplete")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "seal_id": seal_id,
        "authorization_id": authorization_id,
        "state": "sealed_unopened",
        "sealed_at": _utc_now(),
        "claimed_at": "",
        "consumed_at": "",
        "claim_count": 0,
    }
    payload["ledger_id"] = _sha(payload)
    _write_exclusive(Path(path), payload)
    return payload


def atomic_claim_then_read_bundle(
    path: str | Path,
    *,
    preflight: ConfirmatoryPreflightReceipt,
    manifest_id: str,
    seal_id: str,
    authorization_id: str,
    source_sha: str,
    candidate_sha256: str,
    activation_policy_sha256: str,
    runtime_release_id: str,
    taskset_tree_sha256: str,
    paper_memory_root_sha256: str,
    claim_nonce: str,
    bundle_reader: Callable[[], Any],
) -> tuple[Mapping[str, Any], Any]:
    """Atomically claim under an OS lock, then and only then invoke the reader."""
    if not preflight.receipt_id:
        preflight = replace(preflight, receipt_id=preflight.compute_receipt_id())
    ledger_path = Path(path)
    lock_path = ledger_path.with_suffix(ledger_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger.get("state") != "sealed_unopened" or ledger.get("claim_count") != 0:
            raise ValueError("Confirmatory holdout ledger has already been opened")
        bindings = {
            "manifest_id": manifest_id,
            "seal_id": seal_id,
            "authorization_id": authorization_id,
        }
        if any(ledger.get(key) != value for key, value in bindings.items()):
            raise ValueError("Confirmatory ledger binding mismatch")
        if not all(
            (
                source_sha,
                candidate_sha256,
                activation_policy_sha256,
                runtime_release_id,
                taskset_tree_sha256,
                paper_memory_root_sha256,
                claim_nonce,
            )
        ):
            raise ValueError("Confirmatory ledger claim binding is incomplete")
        claimed = {
            **ledger,
            "state": "claimed",
            "claimed_at": _utc_now(),
            "claim_count": 1,
            "preflight_receipt_id": preflight.receipt_id,
            "source_sha": source_sha,
            "candidate_sha256": candidate_sha256,
            "activation_policy_sha256": activation_policy_sha256,
            "runtime_release_id": runtime_release_id,
            "taskset_tree_sha256": taskset_tree_sha256,
            "paper_memory_root_sha256": paper_memory_root_sha256,
            "claim_nonce_sha256": hashlib.sha256(claim_nonce.encode("utf-8")).hexdigest(),
        }
        claimed["ledger_id"] = _sha(
            {key: value for key, value in claimed.items() if key != "ledger_id"}
        )
        _atomic_replace(ledger_path, claimed)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return claimed, bundle_reader()


def consume_fresh_single_use_ledger(
    path: str | Path,
    *,
    campaign_summary_sha256: str,
    assignment_count: int,
    pending_count: int,
    unresolved_technical_failures: int,
    retry_limit_violations: int,
    unclassified_technical_failures: int,
    failed_attempt_decision_contamination: int,
    duplicate_accepted_decision_ids: int,
    memory_writes: int,
    acquisition_writes: int,
    evaluation_chain_calls: int,
    one_runtime_profile: bool,
    one_paper_memory_v5_root: bool,
) -> Mapping[str, Any]:
    ledger_path = Path(path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("state") != "claimed" or ledger.get("claim_count") != 1:
        raise ValueError("Only a once-claimed ledger can be consumed")
    if (
        assignment_count,
        pending_count,
        unresolved_technical_failures,
        retry_limit_violations,
        unclassified_technical_failures,
        failed_attempt_decision_contamination,
        duplicate_accepted_decision_ids,
        memory_writes,
        acquisition_writes,
        evaluation_chain_calls,
    ) != (ASSIGNMENT_COUNT, 0, 0, 0, 0, 0, 0, 0, 0, 0):
        raise ValueError("Confirmatory campaign cannot consume its ledger")
    if not one_runtime_profile or not one_paper_memory_v5_root:
        raise ValueError("Confirmatory campaign used more than one frozen runtime")
    consumed = {
        **ledger,
        "state": "consumed",
        "consumed_at": _utc_now(),
        "campaign_summary_sha256": campaign_summary_sha256,
    }
    consumed["ledger_id"] = _sha(
        {key: value for key, value in consumed.items() if key != "ledger_id"}
    )
    _atomic_replace(ledger_path, consumed)
    return consumed


def assert_evaluator_has_no_fitter_import(evaluator: Callable[..., Any]) -> None:
    source = inspect.getsource(inspect.getmodule(evaluator))
    forbidden = ("fusion_training", "fusion_fit", "optimizer", "fit_monotonic")
    if any(token in source for token in forbidden):
        raise ValueError("Locked evaluator imports or references fitting code")


def next_confirmatory_attempt(
    *,
    completed_attempt_indices: Sequence[int],
    last_status: str | None,
    last_failure_category: str | None,
) -> int:
    """Apply the frozen retry policy before an environment can be launched."""
    indices = tuple(int(value) for value in completed_attempt_indices)
    if indices != tuple(range(len(indices))):
        raise ValueError("Confirmatory attempt history is not contiguous")
    if not indices:
        if last_status is not None or last_failure_category is not None:
            raise ValueError("Empty attempt history has a terminal outcome")
        return 0
    if last_status in {"completed_success", "completed_scientific_failure"}:
        raise ValueError("Scientific completion is final and cannot retry")
    if last_status != "technical_failure":
        raise ValueError("Unclassified technical failure blocks the campaign")
    if last_failure_category not in TECHNICAL_FAILURE_CATEGORIES:
        raise ValueError("Unclassified technical failure blocks the campaign")
    next_index = len(indices)
    if next_index >= 3:
        raise RuntimeError("Attempt 3 is rejected before environment launch")
    return next_index


def accepted_decision_rows(
    rows: Sequence[Mapping[str, Any]], *, accepted_attempt_id: str
) -> tuple[Mapping[str, Any], ...]:
    """Exclude quarantined technical-attempt rows from confirmatory evaluation."""
    selected = tuple(
        row
        for row in rows
        if row.get("attempt_id") == accepted_attempt_id
        and row.get("attempt_disposition") == "accepted_scientific"
    )
    if any(row.get("attempt_disposition") != "accepted_scientific" for row in selected):
        raise AssertionError("Quarantined decision row entered evaluation")
    return selected
