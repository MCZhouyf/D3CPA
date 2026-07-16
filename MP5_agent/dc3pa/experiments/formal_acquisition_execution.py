"""Immutable execution contracts for the 100-episode formal acquisition.

Scientific task failures are final outcomes and are never retried. Retries are
permitted only for a frozen list of infrastructure/technical failures, retain
the failed attempt, and remain bound to the same task, seed, code, policy,
Blueprint, authorization, and schedule entry.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


SCHEMA_VERSION = 1
EXPECTED_EPISODES = 100
EXPECTED_METHOD_ID = "single_chain_reactive_acquisition"

FINAL_STATUSES = frozenset(
    {"completed_success", "completed_scientific_failure"}
)
ALL_STATUSES = FINAL_STATUSES | {"technical_failure"}

TECHNICAL_FAILURE_CATEGORIES = frozenset(
    {
        "environment_start_failure",
        "seed_application_failure",
        "provider_transport_failure",
        "provider_empty_response",
        "process_crash",
        "infrastructure_timeout",
        "receipt_write_failure",
        "trace_write_failure",
        "disk_or_filesystem_failure",
    }
)
SCIENTIFIC_FAILURE_CATEGORIES = frozenset(
    {
        "planner_failure",
        "invalid_or_incomplete_plan",
        "controller_task_failure",
        "navigation_failure_within_budget",
        "resource_not_found_within_budget",
        "task_timeout_with_valid_environment",
        "craft_or_tool_failure",
        "task_success_condition_not_reached",
    }
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


def deterministic_attempt_id(
    campaign_id: str, episode_index: int, attempt_index: int
) -> str:
    """Return the stable run/episode ID for one frozen schedule attempt."""
    if not str(campaign_id).strip():
        raise ValueError("campaign_id is required")
    if not 0 <= int(episode_index) < EXPECTED_EPISODES:
        raise ValueError("episode index is out of range")
    if int(attempt_index) < 0:
        raise ValueError("attempt index cannot be negative")
    return f"r510-e{int(episode_index):03d}-a{int(attempt_index)}-{_sha({'campaign_id': campaign_id, 'episode_index': int(episode_index), 'attempt_index': int(attempt_index)})[:16]}"


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must contain a timezone")
    return parsed


@dataclass(frozen=True)
class TechnicalRetryPolicy:
    policy_name: str = "dc3pa-formal-acquisition-technical-retry-v1"
    maximum_technical_retries_per_entry: int = 2
    allowed_categories: tuple[str, ...] = tuple(
        sorted(TECHNICAL_FAILURE_CATEGORIES)
    )
    scientific_categories: tuple[str, ...] = tuple(
        sorted(SCIENTIFIC_FAILURE_CATEGORIES)
    )
    preserve_all_attempts: bool = True
    same_task_seed_required: bool = True
    same_source_commit_required: bool = True
    same_blueprint_required: bool = True
    same_schedule_required: bool = True
    same_bootstrap_policy_required: bool = True
    same_prompt_hashes_required: bool = True
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported retry-policy schema")
        if self.maximum_technical_retries_per_entry < 0:
            raise ValueError("Maximum retries cannot be negative")
        if set(self.allowed_categories) != TECHNICAL_FAILURE_CATEGORIES:
            raise ValueError("Technical failure category set changed")
        if set(self.scientific_categories) != SCIENTIFIC_FAILURE_CATEGORIES:
            raise ValueError("Scientific failure category set changed")
        if not all(
            (
                self.preserve_all_attempts,
                self.same_task_seed_required,
                self.same_source_commit_required,
                self.same_blueprint_required,
                self.same_schedule_required,
                self.same_bootstrap_policy_required,
                self.same_prompt_hashes_required,
            )
        ):
            raise ValueError("Retry safeguards are incomplete")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("Retry policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["allowed_categories"] = sorted(self.allowed_categories)
        payload["scientific_categories"] = sorted(
            self.scientific_categories
        )
        return payload

    def compute_policy_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "TechnicalRetryPolicy":
        return replace(self, policy_id=self.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.policy_id else self.with_id()
        payload = item.payload_without_id()
        payload["policy_id"] = item.policy_id
        return payload


@dataclass(frozen=True)
class FormalAcquisitionCampaign:
    campaign_name: str
    source_commit: str
    blueprint_id: str
    formal_authorization_id: str
    execution_tooling_binding_id: str
    schedule_id: str
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    bootstrap_data_binding_id: str
    model_profile_id: str
    prompt_hash_bundle_id: str
    controller_identity_sha256: str
    evaluator_identity_sha256: str
    retry_policy_id: str
    expected_episode_count: int = EXPECTED_EPISODES
    health_batch_size: int = 10
    schedule_order_must_be_preserved: bool = True
    outcome_based_stopping_forbidden: bool = True
    outcome_based_configuration_changes_forbidden: bool = True
    source_commit_changes_forbidden: bool = True
    schema_version: int = SCHEMA_VERSION
    campaign_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported acquisition campaign schema")
        required = (
            self.campaign_name,
            self.source_commit,
            self.blueprint_id,
            self.formal_authorization_id,
            self.execution_tooling_binding_id,
            self.schedule_id,
            self.bootstrap_policy_id,
            self.bootstrap_amendment_id,
            self.bootstrap_data_binding_id,
            self.model_profile_id,
            self.prompt_hash_bundle_id,
            self.controller_identity_sha256,
            self.evaluator_identity_sha256,
            self.retry_policy_id,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Formal acquisition campaign identity is incomplete")
        if self.expected_episode_count != EXPECTED_EPISODES:
            raise ValueError("Formal acquisition campaign must have 100 episodes")
        if self.health_batch_size <= 0:
            raise ValueError("Health batch size must be positive")
        if self.expected_episode_count % self.health_batch_size:
            raise ValueError("Health batches must divide the schedule evenly")
        if not all(
            (
                self.schedule_order_must_be_preserved,
                self.outcome_based_stopping_forbidden,
                self.outcome_based_configuration_changes_forbidden,
                self.source_commit_changes_forbidden,
            )
        ):
            raise ValueError("Campaign safeguards are incomplete")
        expected = self.compute_campaign_id()
        if self.campaign_id and self.campaign_id != expected:
            raise ValueError("Campaign hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("campaign_id", None)
        return payload

    def compute_campaign_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalAcquisitionCampaign":
        return replace(self, campaign_id=self.compute_campaign_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.campaign_id else self.with_id()
        payload = item.payload_without_id()
        payload["campaign_id"] = item.campaign_id
        return payload


@dataclass(frozen=True)
class FormalAcquisitionAttempt:
    attempt_id: str
    stage6_receipt_id: str
    campaign_id: str
    schedule_id: str
    formal_authorization_id: str
    execution_tooling_binding_id: str
    episode_index: int
    group_id: str
    task: str
    seed: str
    difficulty: str
    method_id: str
    attempt_index: int
    retry_of_attempt_id: str
    source_commit: str
    blueprint_id: str
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    bootstrap_data_binding_id: str
    prompt_hash_bundle_id: str
    model_profile_id: str
    requested_model: str
    returned_model_identities: tuple[str, ...]
    started_at: str
    finished_at: str
    status: str
    failure_category: str
    failure_detail: str
    pipeline_pass: bool
    task_completed: bool
    planner_calls: int
    reflection_calls: int
    evaluation_chain_calls: int
    controller_execution_count: int
    bootstrap_event_ids: tuple[str, ...]
    intervention_trigger_count: int
    injected_log_count: int
    naturally_collected_log_count: int
    natural_completion: bool
    bootstrap_assisted_completion: bool
    acquisition_record_path: str
    acquisition_record_sha256: str
    trace_sha256: str
    formal_memory_write_count: int
    acquisition_write_count: int
    secret_scan_passed: bool
    inline_rgb_detected: bool
    schema_version: int = SCHEMA_VERSION
    receipt_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported attempt schema")
        if self.status not in ALL_STATUSES:
            raise ValueError(f"Unknown attempt status {self.status!r}")
        if self.method_id != EXPECTED_METHOD_ID:
            raise ValueError("Formal acquisition method ID is incorrect")
        if not 0 <= self.episode_index < EXPECTED_EPISODES:
            raise ValueError("Episode index is out of range")
        if self.attempt_index < 0:
            raise ValueError("Attempt index cannot be negative")
        _parse_timestamp(self.started_at)
        start = _parse_timestamp(self.started_at)
        end = _parse_timestamp(self.finished_at)
        if end < start:
            raise ValueError("Attempt finish precedes start")
        required = (
            self.attempt_id,
            self.campaign_id,
            self.schedule_id,
            self.formal_authorization_id,
            self.execution_tooling_binding_id,
            self.group_id,
            self.task,
            self.seed,
            self.difficulty,
            self.source_commit,
            self.blueprint_id,
            self.bootstrap_policy_id,
            self.bootstrap_amendment_id,
            self.bootstrap_data_binding_id,
            self.prompt_hash_bundle_id,
            self.model_profile_id,
            self.requested_model,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Attempt identity is incomplete")
        integer_values = (
            self.planner_calls,
            self.reflection_calls,
            self.evaluation_chain_calls,
            self.controller_execution_count,
            self.intervention_trigger_count,
            self.injected_log_count,
            self.naturally_collected_log_count,
            self.formal_memory_write_count,
            self.acquisition_write_count,
        )
        if any(isinstance(value, bool) or value < 0 for value in integer_values):
            raise ValueError("Attempt counts cannot be negative")
        expected_attempt_id = deterministic_attempt_id(
            self.campaign_id, self.episode_index, self.attempt_index
        )
        if self.attempt_id != expected_attempt_id:
            raise ValueError("Attempt ID is not deterministic")
        if len(self.bootstrap_event_ids) != self.intervention_trigger_count:
            raise ValueError("Bootstrap event count mismatch")
        if self.natural_completion != (
            self.task_completed and self.intervention_trigger_count == 0
        ):
            raise ValueError("Natural completion classification is inconsistent")
        if self.bootstrap_assisted_completion != (
            self.task_completed and self.intervention_trigger_count > 0
        ):
            raise ValueError(
                "Bootstrap-assisted completion classification is inconsistent"
            )
        if self.natural_completion and self.bootstrap_assisted_completion:
            raise ValueError("Completion categories overlap")
        if self.evaluation_chain_calls != 0:
            raise ValueError("Evaluation Chain must remain disabled")
        if not self.secret_scan_passed or self.inline_rgb_detected:
            raise ValueError("Attempt security/serialization gate failed")

        if self.status == "completed_success":
            if not self.stage6_receipt_id or not self.trace_sha256:
                raise ValueError("Successful attempt needs receipt and trace identities")
            if not self.returned_model_identities:
                raise ValueError("Successful attempt needs returned model identities")
            if not self.pipeline_pass or not self.task_completed:
                raise ValueError("Successful attempt must pass pipeline and task")
            if not self.acquisition_record_path or not self.acquisition_record_sha256:
                raise ValueError("Successful attempt needs an acquisition record")
            if self.acquisition_write_count != 1:
                raise ValueError("Successful attempt must commit one acquisition record")
            if self.failure_category or self.failure_detail:
                raise ValueError("Successful attempt cannot contain failure fields")
        elif self.status == "completed_scientific_failure":
            if not self.stage6_receipt_id or not self.trace_sha256:
                raise ValueError("Scientific failure needs receipt and trace identities")
            if not self.returned_model_identities:
                raise ValueError("Scientific failure needs returned model identities")
            if not self.pipeline_pass or self.task_completed:
                raise ValueError("Scientific failure must be a completed pipeline failure")
            if self.failure_category not in SCIENTIFIC_FAILURE_CATEGORIES:
                raise ValueError("Scientific failure category is not approved")
            if self.acquisition_record_path or self.acquisition_record_sha256:
                raise ValueError("Scientific failure cannot commit acquisition memory")
            if self.acquisition_write_count != 0:
                raise ValueError("Scientific failure wrote acquisition memory")
        else:
            if self.failure_category not in TECHNICAL_FAILURE_CATEGORIES:
                raise ValueError("Technical failure category is not approved")
            if self.task_completed:
                raise ValueError("Technical failure cannot be task completion")
            if self.acquisition_record_path or self.acquisition_record_sha256:
                raise ValueError("Technical failure cannot commit acquisition memory")
            if self.acquisition_write_count != 0:
                raise ValueError("Technical failure wrote acquisition memory")

        if self.attempt_index == 0 and self.retry_of_attempt_id:
            raise ValueError("Initial attempt cannot reference a retry parent")
        if self.attempt_index > 0 and not self.retry_of_attempt_id:
            raise ValueError("Retry attempt must reference the previous attempt")

        expected = self.compute_receipt_id()
        if self.receipt_id and self.receipt_id != expected:
            raise ValueError("Attempt receipt hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("receipt_id", None)
        payload["returned_model_identities"] = list(
            self.returned_model_identities
        )
        payload["bootstrap_event_ids"] = list(self.bootstrap_event_ids)
        return payload

    def compute_receipt_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalAcquisitionAttempt":
        return replace(self, receipt_id=self.compute_receipt_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.receipt_id else self.with_id()
        payload = item.payload_without_id()
        payload["receipt_id"] = item.receipt_id
        return payload


@dataclass(frozen=True)
class EntryAttemptLedger:
    campaign_id: str
    schedule_id: str
    episode_index: int
    group_id: str
    task: str
    seed: str
    retry_policy_id: str
    attempts: tuple[FormalAcquisitionAttempt, ...] = ()
    schema_version: int = SCHEMA_VERSION
    ledger_id: str = ""

    def __post_init__(self) -> None:
        if not all(
            (
                self.campaign_id,
                self.schedule_id,
                self.group_id,
                self.task,
                self.seed,
                self.retry_policy_id,
            )
        ):
            raise ValueError("Attempt ledger identity is incomplete")
        if not 0 <= self.episode_index < EXPECTED_EPISODES:
            raise ValueError("Ledger episode index is out of range")
        for index, attempt in enumerate(self.attempts):
            if attempt.attempt_index != index:
                raise ValueError("Attempt indices are not contiguous")
            if attempt.episode_index != self.episode_index:
                raise ValueError("Attempt/ledger episode index mismatch")
            if (
                attempt.group_id,
                attempt.task,
                attempt.seed,
            ) != (self.group_id, self.task, self.seed):
                raise ValueError("Attempt/ledger task-seed mismatch")
            if attempt.campaign_id != self.campaign_id:
                raise ValueError("Attempt/ledger campaign mismatch")
            if attempt.schedule_id != self.schedule_id:
                raise ValueError("Attempt/ledger schedule mismatch")
            if index:
                if attempt.retry_of_attempt_id != self.attempts[index - 1].attempt_id:
                    raise ValueError("Retry lineage is broken")
                if self.attempts[index - 1].status != "technical_failure":
                    raise ValueError("Only technical failures may be retried")
        final_count = sum(attempt.status in FINAL_STATUSES for attempt in self.attempts)
        if final_count > 1:
            raise ValueError("Entry has more than one final outcome")
        if final_count and self.attempts[-1].status not in FINAL_STATUSES:
            raise ValueError("Attempts continue after a final outcome")
        expected = self.compute_ledger_id()
        if self.ledger_id and self.ledger_id != expected:
            raise ValueError("Attempt ledger hash mismatch")

    @property
    def resolved(self) -> bool:
        return bool(self.attempts and self.attempts[-1].status in FINAL_STATUSES)

    @property
    def final_attempt(self) -> Optional[FormalAcquisitionAttempt]:
        return self.attempts[-1] if self.resolved else None

    @property
    def technical_retry_count(self) -> int:
        return max(0, len(self.attempts) - 1)

    def append(
        self,
        attempt: FormalAcquisitionAttempt,
        *,
        retry_policy: TechnicalRetryPolicy,
    ) -> "EntryAttemptLedger":
        if self.resolved:
            raise ValueError("Cannot append after a final outcome")
        if retry_policy.policy_id not in (
            "",
            self.retry_policy_id,
        ) and retry_policy.compute_policy_id() != self.retry_policy_id:
            raise ValueError("Retry policy ID mismatch")
        if attempt.attempt_index != len(self.attempts):
            raise ValueError("Attempt index is not next in sequence")
        if self.attempts:
            previous = self.attempts[-1]
            if previous.status != "technical_failure":
                raise ValueError("Previous attempt is not technically retryable")
            if self.technical_retry_count >= (
                retry_policy.maximum_technical_retries_per_entry
            ):
                raise ValueError("Maximum technical retry count exceeded")
            immutable_fields = (
                "campaign_id",
                "schedule_id",
                "formal_authorization_id",
                "execution_tooling_binding_id",
                "episode_index",
                "group_id",
                "task",
                "seed",
                "difficulty",
                "method_id",
                "source_commit",
                "blueprint_id",
                "bootstrap_policy_id",
                "bootstrap_amendment_id",
                "bootstrap_data_binding_id",
                "prompt_hash_bundle_id",
                "model_profile_id",
                "requested_model",
            )
            mismatches = [
                field
                for field in immutable_fields
                if getattr(previous, field) != getattr(attempt, field)
            ]
            if mismatches:
                raise ValueError(
                    f"Retry changed frozen fields: {sorted(mismatches)}"
                )
        return replace(
            self,
            attempts=self.attempts + (attempt,),
            ledger_id="",
        ).with_id()

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("ledger_id", None)
        payload["attempts"] = [attempt.to_dict() for attempt in self.attempts]
        return payload

    def compute_ledger_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "EntryAttemptLedger":
        return replace(self, ledger_id=self.compute_ledger_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.ledger_id else self.with_id()
        payload = item.payload_without_id()
        payload["ledger_id"] = item.ledger_id
        payload["resolved"] = item.resolved
        payload["technical_retry_count"] = item.technical_retry_count
        return payload


def load_attempt(path: str | Path) -> FormalAcquisitionAttempt:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["returned_model_identities"] = tuple(
        payload.get("returned_model_identities", ())
    )
    payload["bootstrap_event_ids"] = tuple(
        payload.get("bootstrap_event_ids", ())
    )
    return FormalAcquisitionAttempt(**payload)


def load_ledger(path: str | Path) -> EntryAttemptLedger:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload.pop("resolved", None)
    payload.pop("technical_retry_count", None)
    payload["attempts"] = tuple(
        FormalAcquisitionAttempt(
            **{
                **attempt,
                "returned_model_identities": tuple(
                    attempt.get("returned_model_identities", ())
                ),
                "bootstrap_event_ids": tuple(
                    attempt.get("bootstrap_event_ids", ())
                ),
            }
        )
        for attempt in payload.get("attempts", ())
    )
    return EntryAttemptLedger(**payload)
