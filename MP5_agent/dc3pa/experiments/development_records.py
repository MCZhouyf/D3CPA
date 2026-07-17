"""Decision-level records and audit for V5-bound development collection."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
ACTIVE_ROLES = frozenset({"dev_train", "dev_tune"})
CONFIDENCE_LEVELS = (
    "very_low",
    "low",
    "medium",
    "high",
    "very_high",
)
ENV_STATES = frozenset({"matched", "mismatch", "unknown"})


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
class DevelopmentDecisionRecord:
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
        required = (
            self.record_id,
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
            self.snapshot_root_sha256_before,
            self.snapshot_root_sha256_after,
            self.bootstrap_policy_id,
            self.prompt_hash_bundle_id,
            self.requested_model_name,
            self.local_subgoal,
            self.proposed_action,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Development decision identity is incomplete")
        if self.role not in ACTIVE_ROLES:
            raise ValueError("Round 5.11 records may only be train or tune")
        if self.task == "mine sand":
            raise ValueError("Development record contains superseded task")
        if self.decision_index < 0:
            raise ValueError("Decision index cannot be negative")
        if self.snapshot_root_sha256_before != self.snapshot_root_sha256_after:
            raise ValueError("Paper Memory V5 changed during the decision")
        if self.requested_model_name != "gpt-5.1":
            raise ValueError("Requested model name must remain gpt-5.1")
        if not self.returned_model_identities:
            raise ValueError("Returned model identity must be recorded")
        if not 0.0 <= self.knowledge_coverage <= 1.0:
            raise ValueError("Knowledge coverage is outside [0,1]")
        if self.confidence_level not in CONFIDENCE_LEVELS:
            raise ValueError("Unknown confidence level")
        if len(self.environment_topk_exemplar_ids) > 3:
            raise ValueError("Environment evidence may use at most top-3")
        if len(self.environment_topk_exemplar_ids) != len(
            self.environment_topk_similarities
        ):
            raise ValueError("Environment exemplar/similarity count mismatch")
        if any(
            not 0.0 <= float(value) <= 1.0
            for value in self.environment_topk_similarities
        ):
            raise ValueError("Environment similarity is outside [0,1]")
        if not 0.0 <= self.environment_compatibility <= 1.0:
            raise ValueError("Environment compatibility is outside [0,1]")
        if not 0.0 <= self.environment_coverage <= 1.0:
            raise ValueError("Environment coverage is outside [0,1]")
        if self.environment_raw_state not in ENV_STATES:
            raise ValueError("Unknown raw Environment state")
        integer_values = (
            self.planner_calls,
            self.reflection_calls,
            self.evaluation_chain_calls,
            self.controller_calls,
            self.bootstrap_event_count,
            self.injected_log_count,
            self.input_tokens,
            self.output_tokens,
            self.reasoning_tokens,
            self.formal_memory_write_count,
            self.acquisition_write_count,
        )
        if any(isinstance(value, bool) or value < 0 for value in integer_values):
            raise ValueError("Development counts cannot be negative")
        if self.latency_ms < 0:
            raise ValueError("Latency cannot be negative")
        if self.evaluation_chain_calls != 0:
            raise ValueError("Evaluation Chain must remain disabled")
        if self.formal_memory_write_count or self.acquisition_write_count:
            raise ValueError("Development collection wrote memory/acquisition")
        if self.holdout_accessed:
            raise ValueError("Round 5.11 accessed holdout")
        if not self.excluded_from_final_evaluation:
            raise ValueError("Development record is not marked excluded")
        expected = self.compute_record_hash()
        if self.record_hash and self.record_hash != expected:
            raise ValueError("Development record hash mismatch")

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

    def with_hash(self) -> "DevelopmentDecisionRecord":
        return replace(self, record_hash=self.compute_record_hash())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.record_hash else self.with_hash()
        payload = item.payload_without_hash()
        payload["record_hash"] = item.record_hash
        return payload


@dataclass(frozen=True)
class DevelopmentCollectionAudit:
    collection_id: str
    development_input_release_id: str
    development_protocol_id: str
    paper_memory_v5_release_id: str
    source_commit: str
    record_count: int
    run_count: int
    role_counts: Mapping[str, int]
    confidence_level_counts: Mapping[str, int]
    environment_state_counts: Mapping[str, int]
    task_count: int
    task_seed_count: int
    snapshot_root_sha256: str
    returned_model_identity_counts: Mapping[str, int]
    memory_write_count: int
    acquisition_write_count: int
    holdout_record_count: int
    superseded_task_record_count: int
    duplicate_record_count: int
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    def __post_init__(self) -> None:
        if self.eligible and self.errors:
            raise ValueError("Eligible collection audit cannot contain errors")
        expected = self.compute_audit_id()
        if self.audit_id and self.audit_id != expected:
            raise ValueError("Development collection audit hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("audit_id", None)
        for key in (
            "role_counts",
            "confidence_level_counts",
            "environment_state_counts",
            "returned_model_identity_counts",
        ):
            payload[key] = dict(sorted(payload[key].items()))
        payload["errors"] = list(self.errors)
        payload["warnings"] = list(self.warnings)
        return payload

    def compute_audit_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "DevelopmentCollectionAudit":
        return replace(self, audit_id=self.compute_audit_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.audit_id else self.with_id()
        payload = item.payload_without_id()
        payload["audit_id"] = item.audit_id
        return payload


def audit_development_collection(
    records: Sequence[DevelopmentDecisionRecord],
    *,
    collection_id: str,
    development_input_release_id: str,
    development_protocol_id: str,
    paper_memory_v5_release_id: str,
    source_commit: str,
) -> DevelopmentCollectionAudit:
    errors: list[str] = []
    warnings: list[str] = []
    role_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    environment_counts: Counter[str] = Counter()
    identity_counts: Counter[str] = Counter()
    seen_records: set[str] = set()
    duplicate_count = 0
    roots: set[str] = set()
    runs: set[str] = set()
    tasks: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    memory_writes = acquisition_writes = holdout = superseded = 0

    for item in records:
        if item.record_id in seen_records:
            duplicate_count += 1
        seen_records.add(item.record_id)
        if item.collection_id != collection_id:
            errors.append(f"{item.record_id}: collection ID mismatch")
        if item.development_input_release_id != development_input_release_id:
            errors.append(f"{item.record_id}: development input mismatch")
        if item.development_protocol_id != development_protocol_id:
            errors.append(f"{item.record_id}: protocol mismatch")
        if item.paper_memory_v5_release_id != paper_memory_v5_release_id:
            errors.append(f"{item.record_id}: paper memory mismatch")
        if item.source_commit != source_commit:
            errors.append(f"{item.record_id}: source commit mismatch")
        roots.add(item.snapshot_root_sha256_before)
        runs.add(item.run_id)
        tasks.add(item.task)
        pairs.add((item.task, item.seed))
        role_counts[item.role] += 1
        confidence_counts[item.confidence_level] += 1
        environment_counts[item.environment_raw_state] += 1
        identity_counts.update(item.returned_model_identities)
        memory_writes += item.formal_memory_write_count
        acquisition_writes += item.acquisition_write_count
        holdout += int(item.holdout_accessed or item.role == "dev_holdout")
        superseded += int(item.task == "mine sand")

    if duplicate_count:
        errors.append(f"duplicate development record IDs: {duplicate_count}")
    if len(roots) != 1:
        errors.append(f"development records use multiple snapshot roots: {sorted(roots)}")
    if memory_writes:
        errors.append("development collection wrote formal memory")
    if acquisition_writes:
        errors.append("development collection wrote acquisition data")
    if holdout:
        errors.append("Round 5.11 contains holdout records")
    if superseded:
        errors.append("Round 5.11 contains mine sand")
    if not records:
        errors.append("development collection is empty")
    for role in ACTIVE_ROLES:
        if role_counts[role] <= 0:
            errors.append(f"development role {role} has no records")
    for level in CONFIDENCE_LEVELS:
        if confidence_counts[level] <= 0:
            warnings.append(f"confidence level {level} has no observations")

    return DevelopmentCollectionAudit(
        collection_id=collection_id,
        development_input_release_id=development_input_release_id,
        development_protocol_id=development_protocol_id,
        paper_memory_v5_release_id=paper_memory_v5_release_id,
        source_commit=source_commit,
        record_count=len(records),
        run_count=len(runs),
        role_counts={role: role_counts[role] for role in sorted(ACTIVE_ROLES)},
        confidence_level_counts={
            level: confidence_counts[level] for level in CONFIDENCE_LEVELS
        },
        environment_state_counts={
            state: environment_counts[state] for state in sorted(ENV_STATES)
        },
        task_count=len(tasks),
        task_seed_count=len(pairs),
        snapshot_root_sha256=next(iter(roots), ""),
        returned_model_identity_counts=dict(identity_counts),
        memory_write_count=memory_writes,
        acquisition_write_count=acquisition_writes,
        holdout_record_count=holdout,
        superseded_task_record_count=superseded,
        duplicate_record_count=duplicate_count,
        eligible=not errors,
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(dict.fromkeys(warnings)),
    ).with_id()


def load_development_record(payload: Mapping[str, Any]) -> DevelopmentDecisionRecord:
    normalized = dict(payload)
    for key in (
        "returned_model_identities",
        "knowledge_missing_prerequisites",
        "environment_topk_exemplar_ids",
        "environment_topk_similarities",
    ):
        normalized[key] = tuple(normalized.get(key, ()))
    return DevelopmentDecisionRecord(**normalized)
