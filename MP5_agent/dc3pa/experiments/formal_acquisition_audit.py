"""Audit a complete 100-entry formal acquisition campaign.

The audit distinguishes:
- task success;
- completed scientific task failure;
- unresolved infrastructure failure.

Only successful final attempts may appear in the append-only AcquisitionStore.
Scientific failures remain in the immutable attempt ledgers but never become
successful trajectory records.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .acquisition_binding import (
    acquisition_root_manifest,
    sha256_file,
    validate_acquisition_payload,
)
from .formal_acquisition_execution import (
    EntryAttemptLedger,
    EXPECTED_EPISODES,
    FormalAcquisitionCampaign,
    TechnicalRetryPolicy,
    load_ledger,
)


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
class FormalAcquisitionAuditReport:
    campaign_id: str
    schedule_id: str
    formal_authorization_id: str
    execution_tooling_binding_id: str
    source_commit: str
    blueprint_id: str
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    bootstrap_data_binding_id: str
    scheduled_episode_count: int
    resolved_episode_count: int
    successful_episode_count: int
    scientific_failure_count: int
    unresolved_technical_failure_count: int
    total_attempt_count: int
    technical_retry_count: int
    acquisition_record_count: int
    natural_completion_count: int
    bootstrap_assisted_completion_count: int
    intervention_trigger_count: int
    injected_log_count: int
    naturally_collected_log_count: int
    planner_calls: int
    reflection_calls: int
    evaluation_chain_calls: int
    controller_execution_count: int
    returned_model_identity_counts: Mapping[str, int]
    success_by_difficulty: Mapping[str, int]
    scientific_failure_by_difficulty: Mapping[str, int]
    success_by_task: Mapping[str, int]
    acquisition_root_sha256: str
    acquisition_file_count: int
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported formal acquisition audit schema")
        if self.scheduled_episode_count != EXPECTED_EPISODES:
            raise ValueError("Audit must cover the 100-entry schedule")
        expected = self.compute_audit_id()
        if self.audit_id and self.audit_id != expected:
            raise ValueError("Formal acquisition audit hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("audit_id", None)
        for key in (
            "returned_model_identity_counts",
            "success_by_difficulty",
            "scientific_failure_by_difficulty",
            "success_by_task",
        ):
            payload[key] = dict(sorted(payload[key].items()))
        payload["errors"] = list(self.errors)
        payload["warnings"] = list(self.warnings)
        return payload

    def compute_audit_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "FormalAcquisitionAuditReport":
        return replace(self, audit_id=self.compute_audit_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.audit_id else self.with_id()
        payload = item.payload_without_id()
        payload["audit_id"] = item.audit_id
        return payload


def _schedule_entries(schedule: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    entries = schedule.get("entries")
    if not isinstance(entries, Sequence):
        raise ValueError("Formal acquisition schedule has no entries")
    if len(entries) != EXPECTED_EPISODES:
        raise ValueError(
            f"Expected {EXPECTED_EPISODES} schedule entries, found {len(entries)}"
        )
    expected_indices = list(range(EXPECTED_EPISODES))
    actual_indices = [int(item.get("episode_index", -1)) for item in entries]
    if actual_indices != expected_indices:
        raise ValueError("Schedule episode indices are not contiguous")
    pairs = {(str(item.get("task")), str(item.get("seed"))) for item in entries}
    if len(pairs) != EXPECTED_EPISODES:
        raise ValueError("Schedule task-seed pairs are not unique")
    return tuple(entries)


def audit_formal_acquisition(
    *,
    campaign: FormalAcquisitionCampaign,
    schedule: Mapping[str, Any],
    authorization: Mapping[str, Any],
    blueprint: Mapping[str, Any],
    retry_policy: TechnicalRetryPolicy,
    ledgers: Sequence[EntryAttemptLedger],
    acquisition_root: str | Path,
) -> FormalAcquisitionAuditReport:
    errors: list[str] = []
    warnings: list[str] = []

    campaign = campaign if campaign.campaign_id else campaign.with_id()
    retry_policy = (
        retry_policy if retry_policy.policy_id else retry_policy.with_id()
    )
    entries = _schedule_entries(schedule)
    final_seed_pairs = {
        (str(item.get("task", "")), str(seed))
        for item in blueprint.get("final_test_exclusion", {}).get("tasks", ())
        for seed in item.get("test_seeds", ())
    }
    contaminated = sorted(
        (str(item["task"]), str(item["seed"]))
        for item in entries
        if (str(item["task"]), str(item["seed"])) in final_seed_pairs
    )
    if contaminated:
        errors.append(f"final-test task/seed contamination: {contaminated}")
    if str(schedule.get("schedule_id", "")) != campaign.schedule_id:
        errors.append("campaign/schedule ID mismatch")
    if int(schedule.get("episode_count", len(entries))) != EXPECTED_EPISODES:
        errors.append("schedule episode_count is not 100")
    if str(authorization.get("authorization_id", "")) != (
        campaign.formal_authorization_id
    ):
        errors.append("campaign/authorization ID mismatch")
    if not bool(authorization.get("formal_acquisition_permitted", False)):
        errors.append("formal acquisition authorization is not permitted")
    if str(authorization.get("acquisition_schedule_id", "")) != (
        campaign.schedule_id
    ):
        errors.append("authorization/schedule ID mismatch")
    if str(authorization.get("bootstrap_policy_id", "")) != (
        campaign.bootstrap_policy_id
    ):
        errors.append("authorization/bootstrap policy mismatch")
    if str(authorization.get("bootstrap_amendment_id", "")) != (
        campaign.bootstrap_amendment_id
    ):
        errors.append("authorization/bootstrap amendment mismatch")
    if retry_policy.policy_id != campaign.retry_policy_id:
        errors.append("campaign/retry policy mismatch")

    by_index: dict[int, EntryAttemptLedger] = {}
    for ledger in ledgers:
        if ledger.episode_index in by_index:
            errors.append(f"duplicate ledger for episode {ledger.episode_index}")
        by_index[ledger.episode_index] = ledger

    success_count = scientific_count = unresolved_count = 0
    total_attempts = technical_retries = 0
    natural_count = assisted_count = triggers = injected = natural_logs = 0
    planner_calls = reflection_calls = evaluation_calls = controller_calls = 0
    identity_counts: Counter[str] = Counter()
    success_by_difficulty: Counter[str] = Counter()
    failure_by_difficulty: Counter[str] = Counter()
    success_by_task: Counter[str] = Counter()
    expected_record_by_run: dict[str, Any] = {}

    for entry in entries:
        index = int(entry["episode_index"])
        ledger = by_index.get(index)
        if ledger is None:
            errors.append(f"missing ledger for episode {index}")
            continue
        if ledger.campaign_id != campaign.campaign_id:
            errors.append(f"episode {index}: campaign ID mismatch")
        if ledger.schedule_id != campaign.schedule_id:
            errors.append(f"episode {index}: schedule ID mismatch")
        if (
            ledger.group_id,
            ledger.task,
            str(ledger.seed),
        ) != (
            str(entry.get("group_id")),
            str(entry.get("task")),
            str(entry.get("seed")),
        ):
            errors.append(f"episode {index}: ledger/schedule assignment mismatch")
        total_attempts += len(ledger.attempts)
        technical_retries += ledger.technical_retry_count
        if ledger.technical_retry_count > (
            retry_policy.maximum_technical_retries_per_entry
        ):
            errors.append(f"episode {index}: retry maximum exceeded")
        frozen_expected = {
            "campaign_id": campaign.campaign_id,
            "schedule_id": campaign.schedule_id,
            "formal_authorization_id": campaign.formal_authorization_id,
            "execution_tooling_binding_id": campaign.execution_tooling_binding_id,
            "source_commit": campaign.source_commit,
            "blueprint_id": campaign.blueprint_id,
            "bootstrap_policy_id": campaign.bootstrap_policy_id,
            "bootstrap_amendment_id": campaign.bootstrap_amendment_id,
            "bootstrap_data_binding_id": campaign.bootstrap_data_binding_id,
            "prompt_hash_bundle_id": campaign.prompt_hash_bundle_id,
            "model_profile_id": campaign.model_profile_id,
        }
        for attempt in ledger.attempts:
            for field, expected in frozen_expected.items():
                if getattr(attempt, field) != expected:
                    errors.append(f"episode {index}: attempt {attempt.attempt_index} {field} mismatch")
            for identity in attempt.returned_model_identities:
                identity_counts[str(identity)] += 1
            triggers += attempt.intervention_trigger_count
            injected += attempt.injected_log_count
            natural_logs += attempt.naturally_collected_log_count
            planner_calls += attempt.planner_calls
            reflection_calls += attempt.reflection_calls
            evaluation_calls += attempt.evaluation_chain_calls
            controller_calls += attempt.controller_execution_count
        if not ledger.resolved:
            unresolved_count += 1
            errors.append(f"episode {index}: unresolved technical failure")
            continue

        attempt = ledger.final_attempt
        assert attempt is not None
        natural_count += int(attempt.natural_completion)
        assisted_count += int(attempt.bootstrap_assisted_completion)

        if attempt.status == "completed_success":
            success_count += 1
            success_by_difficulty[attempt.difficulty] += 1
            success_by_task[attempt.task] += 1
            expected_record_by_run[attempt.attempt_id] = attempt
        else:
            scientific_count += 1
            failure_by_difficulty[attempt.difficulty] += 1

    if len(by_index) != EXPECTED_EPISODES:
        extra = sorted(set(by_index) - set(range(EXPECTED_EPISODES)))
        if extra:
            errors.append(f"unexpected ledger episode indices: {extra}")

    root_path = Path(acquisition_root).resolve()
    root_manifest = acquisition_root_manifest(root_path)
    episode_dir = root_path / "episodes"
    record_paths = sorted(episode_dir.glob("*.json")) if episode_dir.is_dir() else []
    seen_record_runs: set[str] = set()
    for path in record_paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            provenance = validate_acquisition_payload(
                payload,
                expected_campaign_id=campaign.campaign_id,
                expected_schedule_id=campaign.schedule_id,
                expected_authorization_id=campaign.formal_authorization_id,
                expected_tooling_binding_id=campaign.execution_tooling_binding_id,
                expected_policy_id=campaign.bootstrap_policy_id,
                expected_amendment_id=campaign.bootstrap_amendment_id,
                expected_binding_id=campaign.bootstrap_data_binding_id,
                expected_source_commit=campaign.source_commit,
                expected_blueprint_id=campaign.blueprint_id,
            )
        except Exception as exc:
            errors.append(f"{path.name}: acquisition record invalid: {exc}")
            continue
        if provenance.attempt_id in seen_record_runs:
            errors.append(
                f"{path.name}: duplicate successful attempt {provenance.attempt_id}"
            )
        seen_record_runs.add(provenance.attempt_id)
        expected_attempt = expected_record_by_run.get(provenance.attempt_id)
        if expected_attempt is None:
            errors.append(
                f"{path.name}: acquisition record has no successful final attempt"
            )
            continue
        if provenance.stage6_receipt_id != expected_attempt.stage6_receipt_id:
            errors.append(f"{path.name}: Stage6 receipt ID mismatch")
        if sha256_file(path) != expected_attempt.acquisition_record_sha256:
            errors.append(f"{path.name}: acquisition record SHA-256 mismatch")
        if provenance.provenance_id not in path.read_text(encoding="utf-8"):
            errors.append(f"{path.name}: provenance ID was not persisted")

        record = payload["record"]
        for candidate in record.get("scene_candidates", []):
            image_relative = str(candidate.get("image_path", ""))
            image_path = (root_path / image_relative).resolve()
            try:
                image_path.relative_to(root_path)
            except ValueError:
                errors.append(
                    f"{path.name}: scene image escapes acquisition root"
                )
                continue
            if not image_path.is_file():
                errors.append(
                    f"{path.name}: scene image is missing: {image_relative}"
                )
            else:
                expected_image_sha = str(
                    candidate.get("metadata", {}).get("image_sha256", "")
                )
                if not expected_image_sha or sha256_file(image_path) != expected_image_sha:
                    errors.append(f"{path.name}: scene image SHA-256 mismatch")

    expected_success_runs = set(expected_record_by_run)
    missing_records = sorted(expected_success_runs - seen_record_runs)
    extra_records = sorted(seen_record_runs - expected_success_runs)
    if missing_records:
        errors.append(
            f"successful final attempts missing acquisition records: {missing_records}"
        )
    if extra_records:
        errors.append(
            f"unexpected acquisition records: {extra_records}"
        )
    if len(record_paths) != success_count:
        errors.append(
            f"acquisition record count {len(record_paths)} != success count "
            f"{success_count}"
        )
    if evaluation_calls:
        errors.append("Evaluation Chain calls were observed")
    if not identity_counts:
        errors.append("no returned model identity was recorded")
    if success_count + scientific_count != EXPECTED_EPISODES:
        errors.append("resolved success/failure counts do not sum to 100")
    if natural_count + assisted_count != success_count:
        errors.append("success completion classes do not sum to successes")
    if unresolved_count:
        warnings.append(
            "Unresolved technical failures block the memory snapshot."
        )

    return FormalAcquisitionAuditReport(
        campaign_id=campaign.campaign_id,
        schedule_id=campaign.schedule_id,
        formal_authorization_id=campaign.formal_authorization_id,
        execution_tooling_binding_id=campaign.execution_tooling_binding_id,
        source_commit=campaign.source_commit,
        blueprint_id=campaign.blueprint_id,
        bootstrap_policy_id=campaign.bootstrap_policy_id,
        bootstrap_amendment_id=campaign.bootstrap_amendment_id,
        bootstrap_data_binding_id=campaign.bootstrap_data_binding_id,
        scheduled_episode_count=EXPECTED_EPISODES,
        resolved_episode_count=success_count + scientific_count,
        successful_episode_count=success_count,
        scientific_failure_count=scientific_count,
        unresolved_technical_failure_count=unresolved_count,
        total_attempt_count=total_attempts,
        technical_retry_count=technical_retries,
        acquisition_record_count=len(record_paths),
        natural_completion_count=natural_count,
        bootstrap_assisted_completion_count=assisted_count,
        intervention_trigger_count=triggers,
        injected_log_count=injected,
        naturally_collected_log_count=natural_logs,
        planner_calls=planner_calls,
        reflection_calls=reflection_calls,
        evaluation_chain_calls=evaluation_calls,
        controller_execution_count=controller_calls,
        returned_model_identity_counts=dict(identity_counts),
        success_by_difficulty=dict(success_by_difficulty),
        scientific_failure_by_difficulty=dict(failure_by_difficulty),
        success_by_task=dict(success_by_task),
        acquisition_root_sha256=str(root_manifest["root_sha256"]),
        acquisition_file_count=int(root_manifest["file_count"]),
        eligible=not errors,
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(dict.fromkeys(warnings)),
    ).with_id()


def load_ledgers(paths: Sequence[str | Path]) -> tuple[EntryAttemptLedger, ...]:
    return tuple(load_ledger(path) for path in paths)
