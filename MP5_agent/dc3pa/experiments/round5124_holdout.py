"""Immutable runtime, records, and one-shot execution lock for Round 5.12.4."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .development_records import CONFIDENCE_LEVELS, ENV_STATES
from .development_shadow import Round511RunBinding, Round511ShadowCollector
from .task_assets import tree_sha256


SCHEMA_VERSION = 1
FINAL_FEATURE_ORDER = (
    "knowledge_coverage",
    "knowledge_known",
    "confidence_probability",
    "environment_probability",
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_exclusive(path: str | Path, payload: Mapping[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _atomic_replace(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


@dataclass(frozen=True)
class FinalHoldoutRuntimeRelease:
    source_commit: str
    controller_sha256: str
    structured_actions_sha256: str
    run_agent_sha256: str
    evaluator_sha256: str
    stage6_launcher_sha256: str
    holdout_runner_sha256: str
    prompt_hash_bundle_id: str
    active_taskset_release_id: str
    active_taskset_manifest_sha256: str
    runtime_task_tree_sha256: str
    formal_task_tree_sha256: str
    active_task_count: int
    paper_memory_v5_release_id: str
    paper_memory_snapshot_root_sha256: str
    formal_log_bootstrap_policy_id: str
    candidate_artifact_id: str
    candidate_artifact_sha256: str
    activation_policy_id: str
    activation_policy_sha256: str
    sealed_assignment_sha256: str
    execution_budget: Mapping[str, Any]
    scientific_success_logic_sha256: str
    memory_readonly: bool
    evaluation_chain_enabled: bool
    fusion_affects_action_selection: bool
    formal_memory_writes_permitted: bool
    acquisition_writes_permitted: bool
    controller_changes_after_freeze_permitted: bool
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        required = (
            self.source_commit,
            self.controller_sha256,
            self.structured_actions_sha256,
            self.run_agent_sha256,
            self.evaluator_sha256,
            self.stage6_launcher_sha256,
            self.holdout_runner_sha256,
            self.prompt_hash_bundle_id,
            self.active_taskset_release_id,
            self.active_taskset_manifest_sha256,
            self.runtime_task_tree_sha256,
            self.formal_task_tree_sha256,
            self.paper_memory_v5_release_id,
            self.paper_memory_snapshot_root_sha256,
            self.formal_log_bootstrap_policy_id,
            self.candidate_artifact_id,
            self.candidate_artifact_sha256,
            self.activation_policy_id,
            self.activation_policy_sha256,
            self.sealed_assignment_sha256,
            self.scientific_success_logic_sha256,
        )
        if any(not value for value in required):
            raise ValueError("Final holdout runtime binding is incomplete")
        if self.active_task_count != 50:
            raise ValueError("Final holdout runtime must bind the approved 50-task set")
        expected_budget = {
            "action_step_timeout_seconds": 30,
            "episode_timeout_seconds": 3600,
            "max_execution_attempts": 4,
            "max_explore_steps": 120,
            "max_planning_replans": 4,
            "maximum_technical_retries_per_assignment": 2,
            "provider_maximum_retries": 3,
            "provider_request_timeout_seconds": 180.0,
        }
        if dict(self.execution_budget) != expected_budget:
            raise ValueError("Final holdout execution budget changed")
        if not self.memory_readonly:
            raise ValueError("Holdout memory must be read-only")
        if any(
            (
                self.evaluation_chain_enabled,
                self.fusion_affects_action_selection,
                self.formal_memory_writes_permitted,
                self.acquisition_writes_permitted,
                self.controller_changes_after_freeze_permitted,
            )
        ):
            raise ValueError("Final holdout runtime opens a forbidden behavior")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("Final holdout runtime hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        payload["execution_budget"] = dict(sorted(self.execution_budget.items()))
        return payload

    def compute_release_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FinalHoldoutRuntimeRelease":
        return replace(self, release_id=self.compute_release_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.release_id else self.with_id()
        return {**item.payload_without_id(), "release_id": item.release_id}


@dataclass(frozen=True)
class LockedHoldoutExecutionManifest:
    source_commit: str
    runtime_release_id: str
    runtime_release_sha256: str
    candidate_artifact_id: str
    candidate_artifact_sha256: str
    activation_policy_id: str
    activation_policy_sha256: str
    sealed_assignment_sha256: str
    expected_assignment_count: int
    output_root: str
    github_actions_run_url: str
    source_worktree_clean: bool
    github_actions_green: bool
    holdout_outcome_files_absent: bool
    schema_version: int = SCHEMA_VERSION
    manifest_id: str = ""

    def __post_init__(self) -> None:
        if any(
            not value
            for value in (
                self.source_commit,
                self.runtime_release_id,
                self.runtime_release_sha256,
                self.candidate_artifact_id,
                self.candidate_artifact_sha256,
                self.activation_policy_id,
                self.activation_policy_sha256,
                self.sealed_assignment_sha256,
                self.output_root,
                self.github_actions_run_url,
            )
        ):
            raise ValueError("Locked holdout execution manifest is incomplete")
        if self.expected_assignment_count != 15:
            raise ValueError("Locked development holdout must contain 15 assignments")
        if not all(
            (
                self.source_worktree_clean,
                self.github_actions_green,
                self.holdout_outcome_files_absent,
            )
        ):
            raise ValueError("Holdout pre-unlock conditions are not satisfied")
        expected = self.compute_manifest_id()
        if self.manifest_id and self.manifest_id != expected:
            raise ValueError("Locked holdout execution manifest hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("manifest_id", None)
        return payload

    def compute_manifest_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "LockedHoldoutExecutionManifest":
        return replace(self, manifest_id=self.compute_manifest_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.manifest_id else self.with_id()
        return {**item.payload_without_id(), "manifest_id": item.manifest_id}


def create_single_use_ledger(
    path: str | Path,
    *,
    manifest: LockedHoldoutExecutionManifest,
) -> Mapping[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": manifest.manifest_id or manifest.compute_manifest_id(),
        "sealed_assignment_sha256": manifest.sealed_assignment_sha256,
        "state": "sealed_unopened",
        "sealed_at": utc_now(),
        "claimed_at": "",
        "consumed_at": "",
        "failure": "",
    }
    payload["ledger_id"] = _sha(payload)
    _write_exclusive(path, payload)
    return payload


def claim_single_use_ledger(
    path: str | Path,
    *,
    manifest: LockedHoldoutExecutionManifest,
    sealed_assignment_path: str | Path,
) -> Mapping[str, Any]:
    ledger_path = Path(path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("state") != "sealed_unopened":
        raise ValueError("Holdout ledger has already been opened")
    manifest_id = manifest.manifest_id or manifest.compute_manifest_id()
    if ledger.get("manifest_id") != manifest_id:
        raise ValueError("Holdout ledger/manifest mismatch")
    if sha256_file(sealed_assignment_path) != manifest.sealed_assignment_sha256:
        raise ValueError("Sealed holdout assignment hash mismatch")
    claimed = {
        **ledger,
        "state": "claimed",
        "claimed_at": utc_now(),
    }
    claimed["ledger_id"] = _sha({k: v for k, v in claimed.items() if k != "ledger_id"})
    _atomic_replace(ledger_path, claimed)
    return claimed


def preflight_active_task_assets(
    active_taskset_root: str | Path,
    *,
    runtime: FinalHoldoutRuntimeRelease,
) -> Mapping[str, Path]:
    """Validate every public task asset without opening holdout assignments."""
    root = Path(active_taskset_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Active taskset root does not exist: {root}")
    manifest_path = root / "active_artifacts.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Active taskset manifest does not exist: {manifest_path}"
        )
    if sha256_file(manifest_path) != runtime.active_taskset_manifest_sha256:
        raise ValueError("Active taskset manifest hash mismatch")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("Active taskset manifest has no artifact list")
    expected_by_kind = {
        "runtime_task_json": set(),
        "formal_task_spec": set(),
    }
    prefixes = {
        "runtime_task_json": "creative_task_jsons/",
        "formal_task_spec": "formal_task_specs/",
    }
    for item in artifacts:
        if not isinstance(item, Mapping):
            raise ValueError("Active taskset artifact descriptor is not an object")
        kind = str(item.get("artifact_kind", ""))
        if kind not in expected_by_kind:
            continue
        relative = str(item.get("path", ""))
        if (
            not relative.startswith(prefixes[kind])
            or Path(relative).suffix != ".json"
        ):
            raise ValueError(f"Invalid {kind} path in active taskset manifest: {relative}")
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Active taskset path escapes its root: {relative}") from exc
        if not path.is_file():
            raise FileNotFoundError(f"Active taskset asset does not exist: {path}")
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Active taskset asset is not valid JSON: {path}") from exc
        expected_by_kind[kind].add(relative)

    task_root = root / "creative_task_jsons"
    formal_root = root / "formal_task_specs"
    actual_runtime = {
        path.relative_to(root).as_posix() for path in task_root.glob("*.json")
    }
    actual_formal = {
        path.relative_to(root).as_posix() for path in formal_root.glob("*.json")
    }
    if actual_runtime != expected_by_kind["runtime_task_json"]:
        raise ValueError("Runtime task assets differ from the active taskset manifest")
    if actual_formal != expected_by_kind["formal_task_spec"]:
        raise ValueError("Formal task specs differ from the active taskset manifest")
    if (
        len(actual_runtime) != runtime.active_task_count
        or len(actual_formal) != runtime.active_task_count
    ):
        raise ValueError("Active taskset asset count differs from the frozen runtime")
    if {Path(path).name for path in actual_runtime} != {
        Path(path).name for path in actual_formal
    }:
        raise ValueError("Runtime task and formal task asset names do not match")
    if tree_sha256(task_root) != runtime.runtime_task_tree_sha256:
        raise ValueError("Runtime task asset tree hash mismatch")
    if tree_sha256(formal_root) != runtime.formal_task_tree_sha256:
        raise ValueError("Formal task spec tree hash mismatch")
    return {"task_root": task_root, "formal_task_spec_root": formal_root}


def claim_single_use_ledger_after_asset_preflight(
    path: str | Path,
    *,
    manifest: LockedHoldoutExecutionManifest,
    sealed_assignment_path: str | Path,
    active_taskset_root: str | Path,
    runtime: FinalHoldoutRuntimeRelease,
    dependency_preflight: Callable[[], None] | None = None,
) -> tuple[Mapping[str, Any], Mapping[str, Path]]:
    """Claim only after all non-secret launch assets have passed preflight."""
    roots = preflight_active_task_assets(active_taskset_root, runtime=runtime)
    if dependency_preflight is not None:
        dependency_preflight()
    claimed = claim_single_use_ledger(
        path,
        manifest=manifest,
        sealed_assignment_path=sealed_assignment_path,
    )
    return claimed, roots


def consume_single_use_ledger(
    path: str | Path,
    *,
    campaign_summary_sha256: str,
) -> Mapping[str, Any]:
    ledger_path = Path(path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("state") != "claimed":
        raise ValueError("Only a claimed holdout ledger can be consumed")
    consumed = {
        **ledger,
        "state": "consumed",
        "consumed_at": utc_now(),
        "campaign_summary_sha256": campaign_summary_sha256,
    }
    consumed["ledger_id"] = _sha({k: v for k, v in consumed.items() if k != "ledger_id"})
    _atomic_replace(ledger_path, consumed)
    return consumed


@dataclass(frozen=True)
class Round5124HoldoutRunBinding(Round511RunBinding):
    final_holdout_runtime_release_id: str = ""
    locked_holdout_execution_manifest_id: str = ""

    def __post_init__(self) -> None:
        if self.role != "dev_holdout":
            raise ValueError("Round 5.12.4 holdout role must be dev_holdout")
        if self.task == "mine sand":
            raise ValueError("Holdout cannot run the superseded mine sand task")
        required = (
            self.collection_id,
            self.development_input_release_id,
            self.development_protocol_id,
            self.group_id,
            self.task,
            self.seed,
            self.difficulty,
            self.run_id,
            self.source_commit,
            self.paper_memory_v5_release_id,
            self.snapshot_root_sha256,
            self.bootstrap_policy_id,
            self.prompt_hash_bundle_id,
            self.final_holdout_runtime_release_id,
            self.locked_holdout_execution_manifest_id,
        )
        if any(not value for value in required):
            raise ValueError("Round 5.12.4 holdout binding is incomplete")
        if self.requested_model_name != "gpt-5.1":
            raise ValueError("Frozen holdout requested model alias changed")


@dataclass(frozen=True)
class HoldoutDecisionRecord:
    record_id: str
    collection_id: str
    development_input_release_id: str
    development_protocol_id: str
    role: str
    group_id: str
    task: str
    seed: str
    difficulty: str
    run_id: str
    decision_index: int
    source_commit: str
    paper_memory_v5_release_id: str
    snapshot_root_sha256_before: str
    snapshot_root_sha256_after: str
    bootstrap_policy_id: str
    prompt_hash_bundle_id: str
    requested_model_name: str
    returned_model_identities: tuple[str, ...]
    local_subgoal: str
    proposed_action: str
    knowledge_hard_feasible: bool
    knowledge_coverage: float
    knowledge_unknown: bool
    knowledge_missing_prerequisites: tuple[str, ...]
    confidence_level: str
    environment_topk_exemplar_ids: tuple[str, ...]
    environment_topk_similarities: tuple[float, ...]
    environment_compatibility: float
    environment_coverage: float
    environment_raw_state: str
    decision_correct: bool
    task_completed: bool
    planner_calls: int
    reflection_calls: int
    evaluation_chain_calls: int
    controller_calls: int
    bootstrap_event_count: int
    injected_log_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    latency_ms: float
    formal_memory_write_count: int
    acquisition_write_count: int
    holdout_accessed: bool
    excluded_from_final_evaluation: bool
    schema_version: int = SCHEMA_VERSION
    record_hash: str = ""

    def __post_init__(self) -> None:
        if self.role != "dev_holdout" or not self.holdout_accessed:
            raise ValueError("Holdout record role/access marker changed")
        if self.excluded_from_final_evaluation:
            raise ValueError("Holdout record was excluded from holdout evaluation")
        if self.task == "mine sand" or self.decision_index < 0:
            raise ValueError("Holdout record task/index is invalid")
        if self.snapshot_root_sha256_before != self.snapshot_root_sha256_after:
            raise ValueError("Paper Memory V5 changed during holdout")
        if self.confidence_level not in CONFIDENCE_LEVELS:
            raise ValueError("Unknown Confidence level")
        if self.environment_raw_state not in ENV_STATES:
            raise ValueError("Unknown Environment state")
        probabilities = (
            self.knowledge_coverage,
            self.environment_compatibility,
            self.environment_coverage,
            *self.environment_topk_similarities,
        )
        if any(not math.isfinite(float(value)) or not 0 <= value <= 1 for value in probabilities):
            raise ValueError("Holdout evidence is outside [0,1]")
        if len(self.environment_topk_exemplar_ids) != len(self.environment_topk_similarities):
            raise ValueError("Holdout Environment evidence length mismatch")
        if self.evaluation_chain_calls or self.formal_memory_write_count or self.acquisition_write_count:
            raise ValueError("Holdout enabled Evaluation Chain or a protected write")
        if not self.returned_model_identities:
            raise ValueError("Holdout returned model identity was not recorded")
        expected = self.compute_record_hash()
        if self.record_hash and self.record_hash != expected:
            raise ValueError("Holdout record hash mismatch")

    def payload_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("record_hash", None)
        for key in (
            "returned_model_identities",
            "knowledge_missing_prerequisites",
            "environment_topk_exemplar_ids",
            "environment_topk_similarities",
        ):
            payload[key] = list(payload[key])
        return payload

    def compute_record_hash(self) -> str:
        return _sha(self.payload_without_hash())

    def with_hash(self) -> "HoldoutDecisionRecord":
        return replace(self, record_hash=self.compute_record_hash())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.record_hash else self.with_hash()
        return {**item.payload_without_hash(), "record_hash": item.record_hash}


class Round5124HoldoutShadowCollector(Round511ShadowCollector):
    """Use the unchanged passive collector with a protected holdout schema."""

    def _make_record(self, **values: Any) -> HoldoutDecisionRecord:
        values["holdout_accessed"] = True
        values["excluded_from_final_evaluation"] = False
        return HoldoutDecisionRecord(**values).with_hash()
