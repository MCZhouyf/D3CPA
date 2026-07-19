"""Fail-closed contracts for a fresh, prospectively approved Path B campaign."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .round511_remediation import (
    MAXIMUM_TECHNICAL_RETRIES,
    next_attempt_index,
)


SCHEMA_VERSION = 1
ROUND5121_SOURCE_SHA = "2c55182647cb150977c5af398506182995be628e"
OLD_CLOSEOUT_ID = "4c168032881eda6def4235001bcf43e576e8c1f80601f3e5127acb09237e2e8f"
RECONCILIATION_POLICY_ID = "eac84b1daf8f3ec07ccb769a65e6064849d34960cef59b96730066250149c75c"
TECHNICAL_RECONCILIATION_ID = "205a1d4cc9161fd9cfe6715b99926ea12b206e488c8c1bd51f49681ca5bc3a39"
BUDGET_RECONCILIATION_ID = "01deee7bde5b2146e72f2f3f44e7ba168d70521a1481de8df34292ea06347e6f"
SALVAGE_DECISION_ID = "93995a764e669a56c1808b7103b347093754e698c9f91d62048a84e9450692e8"

ASSIGNMENT_MANIFEST_ID = "90553e430d1effc09ef95f6afa995c64e26d60fdcd432212496a1ff3c444c406"
DEVELOPMENT_PROTOCOL_ID = "7e7f0d027ab7d440e20a10f687fe1d063ac11603c347f03638f5d8880723c9cc"
ACTIVE_TASKSET_RELEASE_ID = "a858e28ded81743e9c2f425afa8f62663be37149a819764c6515627e89473215"
PAPER_MEMORY_V5_RELEASE_ID = "cc2310aeb60f63e6a1896a4c05109a1ec391649ce102e11b65b6343605789813"
PAPER_MEMORY_SNAPSHOT_ROOT = "af9523e3fd4fc6958916f4585f3edc0f522568b181f969840f154a720092f353"
PROMPT_HASH_BUNDLE_ID = "e8703f9d7a79612afa6a58ce37dca2f6e8591b943f5dd8c6ece9b89f9d45bd00"
ANALYSIS_POLICY_ID = "5b832b3a66ee89d50fcbd38fdf19a2f6b957d854f3feebad319e01b7c9ba5cab"
TOOLING_BINDING_ID = "f449839ecffe7b2e5541e5ae052444e6eecbdf8e77d84c510315d86fe0e44c60"
DEVELOPMENT_INPUT_RELEASE_ID = "bd2f2e96e3e0fd3e4c8dcf4b2180d15adf971d44181ae51bb84c932af0533f99"
BOOTSTRAP_POLICY_ID = "29373c15b5e83e5841a56a8f82c15792d885d07e13b950282c213a947c823a45"
BOOTSTRAP_AMENDMENT_ID = "4421149a8c632a559a6c0c291eccf3ca500732d9d8fdaef64dbf6549992912d5"

CONTROLLER_SOURCE_SHA256 = "f9b5d52fcef6d5ca2740b395d3d54a19cd01ac034b055a83e90e622e7368e3c3"
STRUCTURED_ACTIONS_SOURCE_SHA256 = "4a65d0cea264d378c6f1b30aa65940e7cd84e61722304a6730796a3837912f96"
SUCCESS_LOGIC_SOURCE_SHA256 = "ff3a443e5b4171e49717b9522876d55d33d31630d19a86c8f63814c5d7e4db10"
FRESH_CAMPAIGN_INPUT_MANIFEST = "fresh_campaign_input_manifest.json"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def load_json(path: str | Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _require_timezone_timestamp(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} timestamp is required")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{label} timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} timestamp must include a timezone")


def fresh_campaign_id(
    *,
    source_commit: str,
    path_b_approval_id: str,
    complete_budget_contract_id: str,
    assignment_manifest_id: str = ASSIGNMENT_MANIFEST_ID,
) -> str:
    return _sha(
        {
            "assignment_manifest_id": assignment_manifest_id,
            "complete_budget_contract_id": complete_budget_contract_id,
            "path_b_approval_id": path_b_approval_id,
            "source_commit": source_commit,
        }
    )


@dataclass(frozen=True)
class CompleteExecutionBudgetContract:
    source_commit: str
    episode_timeout_seconds: int
    author_timeout_decision_id: str
    max_execution_attempts: int = 4
    max_explore_steps: int = 60
    planning_replanning_limit: int = 4
    action_step_limit: int = 30
    environment_task_timeout_seconds: int = 0
    provider_request_timeout_seconds: float = 180.0
    provider_maximum_retries: int = 3
    controller_exploration_step_limit: int = 60
    controller_task_retry_limit: int = 30
    maximum_technical_retries: int = MAXIMUM_TECHNICAL_RETRIES
    controller_source_sha256: str = CONTROLLER_SOURCE_SHA256
    structured_actions_source_sha256: str = STRUCTURED_ACTIONS_SOURCE_SHA256
    success_logic_source_sha256: str = SUCCESS_LOGIC_SOURCE_SHA256
    task_specific_cutoffs_bound_by_source: bool = True
    one_effective_profile_required: bool = True
    schema_version: int = SCHEMA_VERSION
    contract_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source_commit, str) or len(self.source_commit) != 40:
            raise ValueError("Budget contract source commit is incomplete")
        if (
            not isinstance(self.author_timeout_decision_id, str)
            or not self.author_timeout_decision_id.strip()
        ):
            raise ValueError("An explicit author timeout decision is required")
        positive = (
            self.episode_timeout_seconds,
            self.max_execution_attempts,
            self.max_explore_steps,
            self.planning_replanning_limit,
            self.action_step_limit,
            self.environment_task_timeout_seconds,
            self.provider_request_timeout_seconds,
            self.controller_exploration_step_limit,
            self.controller_task_retry_limit,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value <= 0
            for value in positive
        ):
            raise ValueError("Every execution budget must be explicitly positive")
        if self.environment_task_timeout_seconds != self.episode_timeout_seconds:
            raise ValueError("Environment timeout must equal the episode watchdog")
        expected_values = (
            self.max_execution_attempts == 4,
            self.max_explore_steps == 60,
            self.planning_replanning_limit == 4,
            self.action_step_limit == 30,
            self.provider_request_timeout_seconds == 180.0,
            self.provider_maximum_retries == 3,
            self.controller_exploration_step_limit == 60,
            self.controller_task_retry_limit == 30,
            self.maximum_technical_retries == 2,
            self.controller_source_sha256 == CONTROLLER_SOURCE_SHA256,
            self.structured_actions_source_sha256 == STRUCTURED_ACTIONS_SOURCE_SHA256,
            self.success_logic_source_sha256 == SUCCESS_LOGIC_SOURCE_SHA256,
            self.task_specific_cutoffs_bound_by_source,
            self.one_effective_profile_required,
        )
        if not all(expected_values):
            raise ValueError("The accepted runtime budget profile changed")
        expected = self.compute_contract_id()
        if self.contract_id and self.contract_id != expected:
            raise ValueError("Execution budget contract hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("contract_id", None)
        return payload

    def compute_contract_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "CompleteExecutionBudgetContract":
        return replace(self, contract_id=self.compute_contract_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.contract_id else self.with_id()
        payload = item.payload_without_id()
        payload["contract_id"] = item.contract_id
        payload["snapshot_id"] = item.contract_id
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CompleteExecutionBudgetContract":
        values = dict(payload)
        values.pop("snapshot_id", None)
        return cls(**values)


@dataclass(frozen=True)
class PathBRemediationApproval:
    approval_name: str
    approved_by: str
    approved_at: str
    fresh_campaign_source_sha: str
    complete_budget_contract_id: str
    approval_statement: str
    reconciliation_policy_id: str = RECONCILIATION_POLICY_ID
    technical_reconciliation_id: str = TECHNICAL_RECONCILIATION_ID
    budget_reconciliation_id: str = BUDGET_RECONCILIATION_ID
    salvage_decision_id: str = SALVAGE_DECISION_ID
    old_ineligible_closeout_id: str = OLD_CLOSEOUT_ID
    assignment_manifest_id: str = ASSIGNMENT_MANIFEST_ID
    development_protocol_id: str = DEVELOPMENT_PROTOCOL_ID
    active_taskset_release_id: str = ACTIVE_TASKSET_RELEASE_ID
    paper_memory_v5_release_id: str = PAPER_MEMORY_V5_RELEASE_ID
    paper_memory_snapshot_root_sha256: str = PAPER_MEMORY_SNAPSHOT_ROOT
    prompt_hash_bundle_id: str = PROMPT_HASH_BUNDLE_ID
    analysis_policy_id: str = ANALYSIS_POLICY_ID
    development_tooling_binding_id: str = TOOLING_BINDING_ID
    development_input_release_id: str = DEVELOPMENT_INPUT_RELEASE_ID
    bootstrap_policy_id: str = BOOTSTRAP_POLICY_ID
    bootstrap_amendment_id: str = BOOTSTRAP_AMENDMENT_ID
    path_b_authorized: bool = True
    old_decisions_reused: bool = False
    assignments_unchanged: bool = True
    runtime_behavior_unchanged: bool = True
    holdout_sealed: bool = True
    fusion_unfitted: bool = True
    final_evaluation_unopened: bool = True
    maximum_technical_retries: int = 2
    schema_version: int = SCHEMA_VERSION
    approval_id: str = ""

    def __post_init__(self) -> None:
        if self.approved_by != "ZYF":
            raise ValueError("Explicit ZYF approval is required")
        _require_timezone_timestamp(self.approved_at, label="Approval")
        if len(self.fresh_campaign_source_sha) != 40:
            raise ValueError("Approval source SHA is incomplete")
        if len(self.complete_budget_contract_id) != 64:
            raise ValueError("Approval budget binding is incomplete")
        if "Path B" not in self.approval_statement or "60" not in self.approval_statement:
            raise ValueError("Approval statement must authorize fresh Path B 60-unit execution")
        expected_ids = (
            self.reconciliation_policy_id == RECONCILIATION_POLICY_ID,
            self.technical_reconciliation_id == TECHNICAL_RECONCILIATION_ID,
            self.budget_reconciliation_id == BUDGET_RECONCILIATION_ID,
            self.salvage_decision_id == SALVAGE_DECISION_ID,
            self.old_ineligible_closeout_id == OLD_CLOSEOUT_ID,
            self.assignment_manifest_id == ASSIGNMENT_MANIFEST_ID,
            self.development_protocol_id == DEVELOPMENT_PROTOCOL_ID,
            self.active_taskset_release_id == ACTIVE_TASKSET_RELEASE_ID,
            self.paper_memory_v5_release_id == PAPER_MEMORY_V5_RELEASE_ID,
            self.paper_memory_snapshot_root_sha256 == PAPER_MEMORY_SNAPSHOT_ROOT,
            self.prompt_hash_bundle_id == PROMPT_HASH_BUNDLE_ID,
            self.analysis_policy_id == ANALYSIS_POLICY_ID,
            self.development_tooling_binding_id == TOOLING_BINDING_ID,
            self.development_input_release_id == DEVELOPMENT_INPUT_RELEASE_ID,
            self.bootstrap_policy_id == BOOTSTRAP_POLICY_ID,
            self.bootstrap_amendment_id == BOOTSTRAP_AMENDMENT_ID,
        )
        safeguards = (
            self.path_b_authorized,
            not self.old_decisions_reused,
            self.assignments_unchanged,
            self.runtime_behavior_unchanged,
            self.holdout_sealed,
            self.fusion_unfitted,
            self.final_evaluation_unopened,
            self.maximum_technical_retries == 2,
        )
        if not all(expected_ids) or not all(safeguards):
            raise ValueError("Path B approval weakens or changes protected inputs")
        expected = self.compute_approval_id()
        if self.approval_id and self.approval_id != expected:
            raise ValueError("Path B approval hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("approval_id", None)
        return payload

    def compute_approval_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "PathBRemediationApproval":
        return replace(self, approval_id=self.compute_approval_id())

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PathBRemediationApproval":
        return cls(**dict(payload))


@dataclass(frozen=True)
class FreshDevelopmentCampaignAuthorization:
    authorization_name: str
    approved_by: str
    authorized_at: str
    source_commit: str
    path_b_approval_id: str
    complete_budget_contract_id: str
    campaign_id: str
    assignment_count: int = 60
    dev_train_count: int = 45
    dev_tune_count: int = 15
    assignment_manifest_id: str = ASSIGNMENT_MANIFEST_ID
    old_campaign_import_forbidden: bool = True
    output_root_must_start_empty: bool = True
    holdout_unmounted: bool = True
    final_unmounted: bool = True
    evaluation_chain_calls_required: int = 0
    memory_writes_required: int = 0
    acquisition_writes_required: int = 0
    schema_version: int = SCHEMA_VERSION
    authorization_id: str = ""

    def __post_init__(self) -> None:
        if self.approved_by != "ZYF" or len(self.source_commit) != 40:
            raise ValueError("Fresh campaign authorization identity is incomplete")
        _require_timezone_timestamp(self.authorized_at, label="Authorization")
        if len(self.path_b_approval_id) != 64 or len(self.complete_budget_contract_id) != 64:
            raise ValueError("Fresh campaign authorization bindings are incomplete")
        expected_campaign_id = fresh_campaign_id(
            source_commit=self.source_commit,
            path_b_approval_id=self.path_b_approval_id,
            complete_budget_contract_id=self.complete_budget_contract_id,
            assignment_manifest_id=self.assignment_manifest_id,
        )
        if self.campaign_id != expected_campaign_id:
            raise ValueError("Fresh campaign ID is invalid")
        if (self.assignment_count, self.dev_train_count, self.dev_tune_count) != (60, 45, 15):
            raise ValueError("Fresh campaign must contain exactly 45 train and 15 tune units")
        safeguards = (
            self.assignment_manifest_id == ASSIGNMENT_MANIFEST_ID,
            self.old_campaign_import_forbidden,
            self.output_root_must_start_empty,
            self.holdout_unmounted,
            self.final_unmounted,
            self.evaluation_chain_calls_required == 0,
            self.memory_writes_required == 0,
            self.acquisition_writes_required == 0,
        )
        if not all(safeguards):
            raise ValueError("Fresh campaign safeguards are incomplete")
        expected = self.compute_authorization_id()
        if self.authorization_id and self.authorization_id != expected:
            raise ValueError("Fresh campaign authorization hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("authorization_id", None)
        return payload

    def compute_authorization_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FreshDevelopmentCampaignAuthorization":
        return replace(self, authorization_id=self.compute_authorization_id())

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "FreshDevelopmentCampaignAuthorization":
        return cls(**dict(payload))


def canonical_assignment_manifest_id(assignments: Sequence[Mapping[str, Any]]) -> str:
    ordered = sorted(assignments, key=lambda item: int(item["sequence_index"]))
    return _sha(ordered)


def validate_fresh_assignments(assignments: Sequence[Mapping[str, Any]]) -> None:
    if len(assignments) != 60:
        raise ValueError("Fresh campaign requires all 60 assignments")
    roles = {
        role: sum(item.get("role") == role for item in assignments)
        for role in ("dev_train", "dev_tune")
    }
    if roles != {"dev_train": 45, "dev_tune": 15}:
        raise ValueError("Fresh campaign role counts changed")
    if any(item.get("role") not in roles for item in assignments):
        raise ValueError("Holdout/final roles are forbidden")
    if canonical_assignment_manifest_id(assignments) != ASSIGNMENT_MANIFEST_ID:
        raise ValueError("Fresh assignments differ from the immutable protocol")


def validate_campaign_authorization(
    *,
    approval: PathBRemediationApproval,
    authorization: FreshDevelopmentCampaignAuthorization,
    budget: CompleteExecutionBudgetContract,
    assignments: Sequence[Mapping[str, Any]],
    current_source_sha: str,
    output_root: str | Path,
) -> None:
    validate_fresh_assignments(assignments)
    approval = approval.with_id()
    authorization = authorization.with_id()
    budget = budget.with_id()
    if not (
        approval.fresh_campaign_source_sha
        == authorization.source_commit
        == budget.source_commit
        == current_source_sha
    ):
        raise ValueError("Fresh campaign source binding mismatch")
    if authorization.path_b_approval_id != approval.approval_id:
        raise ValueError("Fresh authorization/Path B approval mismatch")
    if not (
        authorization.complete_budget_contract_id
        == approval.complete_budget_contract_id
        == budget.contract_id
    ):
        raise ValueError("Fresh campaign budget binding mismatch")
    expected_campaign_id = fresh_campaign_id(
        source_commit=current_source_sha,
        path_b_approval_id=approval.approval_id,
        complete_budget_contract_id=budget.contract_id,
    )
    if authorization.campaign_id != expected_campaign_id:
        raise ValueError("Fresh campaign ID binding mismatch")
    root = Path(output_root)
    if root.exists() and any(root.iterdir()):
        manifest_path = root / FRESH_CAMPAIGN_INPUT_MANIFEST
        if not manifest_path.is_file():
            raise ValueError("Fresh campaign root contains unbound historical data")
        manifest = load_json(manifest_path)
        expected = fresh_campaign_input_manifest(
            approval=approval,
            authorization=authorization,
            budget=budget,
            assignments=assignments,
        )
        if manifest != expected:
            raise ValueError("Fresh campaign root manifest differs from authorization")
        _validate_existing_fresh_ledgers(
            root=root,
            approval=approval,
            authorization=authorization,
            budget=budget,
        )


def _validate_existing_fresh_ledgers(
    *,
    root: Path,
    approval: PathBRemediationApproval,
    authorization: FreshDevelopmentCampaignAuthorization,
    budget: CompleteExecutionBudgetContract,
) -> None:
    runs_root = root / "runs"
    if not runs_root.exists():
        return
    expected_binding = {
        "collection_id": authorization.campaign_id,
        "fresh_campaign_authorization_id": authorization.authorization_id,
        "path_b_approval_id": approval.approval_id,
        "source_commit": authorization.source_commit,
        "execution_budget_snapshot_id": budget.contract_id,
    }
    for binding_path in runs_root.glob("*/attempt-*/run_binding.json"):
        binding = load_json(binding_path)
        for field_name, expected_value in expected_binding.items():
            if binding.get(field_name) != expected_value:
                raise ValueError("Old campaign attempt import is forbidden")
    for attempt_root in runs_root.glob("*/attempt-*"):
        if (attempt_root / "run_binding.json").is_file():
            continue
        allowed = {"execution_budget_snapshot.json"}
        if any(path.name not in allowed for path in attempt_root.iterdir()):
            raise ValueError("Unbound attempt evidence is forbidden")
    for marker_path in runs_root.glob("*/accepted.json"):
        marker = load_json(marker_path)
        run_id = str(marker.get("run_id", ""))
        bound_run_ids = {
            str(load_json(path).get("run_id", ""))
            for path in marker_path.parent.glob("attempt-*/run_binding.json")
        }
        if not run_id or run_id not in bound_run_ids:
            raise ValueError("Old campaign accepted marker import is forbidden")


def validate_runtime_source_hashes(mp5_root: str | Path) -> None:
    root = Path(mp5_root)
    expected = {
        root / "agent" / "controller.py": CONTROLLER_SOURCE_SHA256,
        root / "agent" / "structured_actions.py": STRUCTURED_ACTIONS_SOURCE_SHA256,
        root / "agent" / "run_agent.py": SUCCESS_LOGIC_SOURCE_SHA256,
    }
    for path, expected_sha256 in expected.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected_sha256:
            raise ValueError(f"Protected runtime source changed: {path.name}")


def fresh_campaign_input_manifest(
    *,
    approval: PathBRemediationApproval,
    authorization: FreshDevelopmentCampaignAuthorization,
    budget: CompleteExecutionBudgetContract,
    assignments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = {
        "assignment_count": len(assignments),
        "assignment_manifest_id": canonical_assignment_manifest_id(assignments),
        "campaign_id": authorization.campaign_id,
        "campaign_authorization_id": authorization.with_id().authorization_id,
        "complete_execution_budget_contract_id": budget.with_id().contract_id,
        "old_campaign_imported": False,
        "path_b_approval_id": approval.with_id().approval_id,
        "schema_version": SCHEMA_VERSION,
        "source_commit": authorization.source_commit,
    }
    payload["manifest_id"] = _sha(payload)
    return payload


def assignment_ledger_name(assignment: Mapping[str, Any]) -> str:
    return hashlib.sha256(str(assignment["group_id"]).encode("utf-8")).hexdigest()[:16]


def ensure_fresh_campaign_ledgers(
    *,
    output_root: str | Path,
    assignments: Sequence[Mapping[str, Any]],
) -> None:
    validate_fresh_assignments(assignments)
    root = Path(output_root)
    if not (root / FRESH_CAMPAIGN_INPUT_MANIFEST).is_file():
        raise ValueError("Fresh campaign input manifest is missing")
    runs_root = root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    expected = {assignment_ledger_name(item) for item in assignments}
    observed = {path.name for path in runs_root.iterdir() if path.is_dir()}
    unexpected = observed - expected
    if unexpected:
        raise ValueError("Fresh campaign contains an unbound historical ledger")
    for ledger_name in sorted(expected):
        (runs_root / ledger_name).mkdir(exist_ok=True)
    for name in ("decision_records", "quarantine", "accepted_datasets"):
        (root / name).mkdir(exist_ok=True)


def initialize_fresh_campaign_root(
    *,
    output_root: str | Path,
    approval: PathBRemediationApproval,
    authorization: FreshDevelopmentCampaignAuthorization,
    budget: CompleteExecutionBudgetContract,
    assignments: Sequence[Mapping[str, Any]],
) -> Path:
    root = Path(output_root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Fresh campaign root must be absent or empty at initialization")
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / FRESH_CAMPAIGN_INPUT_MANIFEST
    payload = fresh_campaign_input_manifest(
        approval=approval,
        authorization=authorization,
        budget=budget,
        assignments=assignments,
    )
    with manifest_path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    ensure_fresh_campaign_ledgers(output_root=root, assignments=assignments)
    return manifest_path


def persist_complete_budget_contract(
    path: str | Path, budget: CompleteExecutionBudgetContract
) -> None:
    target = Path(path)
    payload = budget.with_id().to_dict()
    if target.exists():
        if load_json(target) != payload:
            raise ValueError("Existing complete execution budget differs")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def prelaunch_attempt_gate(
    *,
    approval: PathBRemediationApproval,
    authorization: FreshDevelopmentCampaignAuthorization,
    budget: CompleteExecutionBudgetContract,
    assignment: Mapping[str, Any],
    expected_assignment: Mapping[str, Any],
    current_source_sha: str,
    group_root: str | Path,
    attempt_index: int,
    budget_snapshot_path: str | Path,
) -> None:
    if dict(assignment) != dict(expected_assignment):
        raise ValueError("Attempt assignment differs from frozen manifest")
    if assignment.get("role") not in {"dev_train", "dev_tune"}:
        raise ValueError("Holdout/final role rejected before launch")
    if (
        current_source_sha != authorization.source_commit
        or current_source_sha != budget.source_commit
    ):
        raise ValueError("Source commit changed before attempt launch")
    approval = approval.with_id()
    authorization = authorization.with_id()
    budget = budget.with_id()
    if approval.fresh_campaign_source_sha != current_source_sha:
        raise ValueError("Path B approval source differs from launch source")
    if authorization.path_b_approval_id != approval.approval_id:
        raise ValueError("Attempt lacks valid Path B authorization")
    if not (
        authorization.complete_budget_contract_id
        == approval.complete_budget_contract_id
        == budget.contract_id
    ):
        raise ValueError("Attempt budget profile differs from campaign")
    if authorization.campaign_id != fresh_campaign_id(
        source_commit=current_source_sha,
        path_b_approval_id=approval.approval_id,
        complete_budget_contract_id=budget.contract_id,
    ):
        raise ValueError("Attempt campaign ID differs from authorization")
    snapshot = load_json(budget_snapshot_path)
    if snapshot != budget.to_dict():
        raise ValueError("Complete budget snapshot missing or mismatched")
    authoritative_index = next_attempt_index(group_root)
    if authoritative_index is None or authoritative_index != attempt_index:
        raise ValueError("Attempt index is not authorized by the ledger")
    if attempt_index > MAXIMUM_TECHNICAL_RETRIES:
        raise ValueError("Attempt 3 is forbidden before MineDojo launch")
