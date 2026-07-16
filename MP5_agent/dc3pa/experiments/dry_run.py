"""Tiny dry-run campaign contracts and pipeline audit.

A dry run validates launch integration and data plumbing only. Its outputs are
permanently excluded from memory construction, calibration, and formal fitting.
Task completion is informational and is not required for a pipeline pass.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from dc3pa.experiments.blueprint import RealExperimentBlueprint
from dc3pa.experiments.launcher_validation import validate_real_experiment_launch
from dc3pa.experiments.phase_state import ExperimentPhaseState
from dc3pa.integration.events import TaskRunResult


DRY_RUN_SCHEMA_VERSION = 1
DRY_RUN_STATUSES = frozenset({"pipeline_pass", "pipeline_fail"})
DRY_RUN_MARKER = ".dc3pa_dry_run_root.json"
_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9]{12,}|OPENAI_API_KEY|api[_-]?key|password|secret|token)",
    re.IGNORECASE,
)
_INLINE_RGB_PATTERN = re.compile(
    r'"(?:rgb|image|pixels|frame|observation_image)"\s*:\s*\[',
    re.IGNORECASE,
)
_DISALLOWED_SUFFIXES = {
    ".db",
    ".jpeg",
    ".jpg",
    ".png",
    ".sqlite",
    ".sqlite3",
}


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mark_dry_run_output_root(
    root: str | Path,
    *,
    campaign_id: str,
    entry_id: str = "",
) -> Path:
    output = Path(root)
    output.mkdir(parents=True, exist_ok=True)
    marker = output / DRY_RUN_MARKER
    payload = {
        "dry_run_root": True,
        "campaign_id": campaign_id,
        "entry_id": entry_id,
        "excluded_from_formal_fitting": True,
        "schema_version": DRY_RUN_SCHEMA_VERSION,
    }
    if marker.exists():
        existing = json.loads(marker.read_text(encoding="utf-8"))
        if existing.get("campaign_id") != campaign_id:
            raise ValueError("Dry-run output root is already bound to another campaign")
    marker.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def dry_run_marker_for(path: str | Path) -> Optional[Path]:
    current = Path(path).resolve()
    candidates = [current] if current.is_dir() else [current.parent]
    candidates.extend(candidates[0].parents)
    for directory in candidates:
        marker = directory / DRY_RUN_MARKER
        if marker.exists():
            return marker
    return None


def ensure_not_dry_run_artifact_path(path: str | Path, *, label: str = "input") -> None:
    marker = dry_run_marker_for(path)
    if marker is not None:
        raise ValueError(
            f"{label} points inside a dry-run artifact root marked by {marker}"
        )


def _iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    return sorted(path for path in root.rglob("*") if path.is_file())


def scan_dry_run_output_root(root: str | Path) -> dict[str, Any]:
    output = Path(root)
    files = _iter_files(output)
    file_hashes: dict[str, str] = {}
    errors: list[str] = []
    inline_rgb_detected = False
    secret_scan_passed = True
    confidence_observation_count = 0
    execution_label_join_count = 0
    censored_excluded_count = 0
    ambiguous_excluded_count = 0
    technical_failure_count = 0

    for path in files:
        relative = path.relative_to(output).as_posix() if output.is_dir() else path.name
        file_hashes[relative] = sha256_file(path)
        if path.suffix.lower() in _DISALLOWED_SUFFIXES:
            errors.append(f"disallowed file in dry-run JSON artifact root: {relative}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _INLINE_RGB_PATTERN.search(text):
            inline_rgb_detected = True
        if _SECRET_PATTERN.search(text):
            secret_scan_passed = False
        for line in text.splitlines() if path.suffix == ".jsonl" else [text]:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, Mapping):
                confidence_observation_count += _count_key(payload, "confidence_observations")
                execution_label_join_count += _count_key(payload, "execution_label_joins")
                execution_label_join_count += _count_key(payload, "included")
                for item in _as_sequence(payload.get("excluded", ())):
                    reason = str(_mapping_get(item, "reason", "")).lower()
                    if "censored" in reason:
                        censored_excluded_count += 1
                    if "ambiguous" in reason:
                        ambiguous_excluded_count += 1
                if bool(payload.get("technical_failure", False)):
                    technical_failure_count += 1
    manifest = {
        "root_file_count": len(files),
        "files": file_hashes,
    }
    return {
        "output_manifest_sha256": hashlib.sha256(
            _canonical_json(manifest)
        ).hexdigest(),
        "inline_rgb_detected": inline_rgb_detected,
        "secret_scan_passed": secret_scan_passed,
        "confidence_observation_count": confidence_observation_count,
        "execution_label_join_count": execution_label_join_count,
        "censored_excluded_count": censored_excluded_count,
        "ambiguous_excluded_count": ambiguous_excluded_count,
        "technical_failure_count": technical_failure_count,
        "errors": tuple(errors),
    }


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _count_key(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key, ())
    if isinstance(value, Mapping):
        return len(value)
    return len(_as_sequence(value))


@dataclass(frozen=True)
class DryRunCampaignEntry:
    entry_id: str
    group_id: str
    task: str
    seed: str
    maximum_high_level_steps: int
    maximum_llm_calls: int
    maximum_replans: int
    timeout_seconds: float
    launch_trace: Mapping[str, Any]
    excluded_from_formal_fitting: bool = True

    def __post_init__(self) -> None:
        if not self.entry_id or not self.group_id or not self.task or not self.seed:
            raise ValueError("Dry-run entry identifiers are required")
        if not self.excluded_from_formal_fitting:
            raise ValueError("All dry-run entries must be excluded from fitting")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["launch_trace"] = dict(self.launch_trace)
        return payload


@dataclass(frozen=True)
class DryRunCampaign:
    campaign_name: str
    blueprint_id: str
    source_commit: str
    entries: tuple[DryRunCampaignEntry, ...]
    require_confidence_observations: bool
    require_execution_label_joins: bool
    use_formal_memory: bool = False
    schema_version: int = DRY_RUN_SCHEMA_VERSION
    campaign_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != DRY_RUN_SCHEMA_VERSION:
            raise ValueError("Unsupported dry-run campaign schema")
        if not self.campaign_name or not self.blueprint_id or not self.source_commit:
            raise ValueError("Dry-run campaign identifiers are required")
        if not self.entries:
            raise ValueError("Dry-run campaign must have at least one entry")
        if len(self.entries) > 6:
            raise ValueError("Tiny dry run may contain at most six task-seed entries")
        if self.use_formal_memory:
            raise ValueError("Tiny dry run cannot use formal long-term memory")
        ids = [item.entry_id for item in self.entries]
        pairs = [(item.task, item.seed) for item in self.entries]
        if len(ids) != len(set(ids)) or len(pairs) != len(set(pairs)):
            raise ValueError("Dry-run entries must be unique")
        expected = self.compute_campaign_id()
        if self.campaign_id and self.campaign_id != expected:
            raise ValueError("Dry-run campaign hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("campaign_id", None)
        payload["entries"] = [
            item.to_dict() for item in sorted(self.entries, key=lambda x: x.entry_id)
        ]
        return payload

    def compute_campaign_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "DryRunCampaign":
        return replace(self, campaign_id=self.compute_campaign_id())

    def to_dict(self) -> dict[str, Any]:
        campaign = self if self.campaign_id else self.with_id()
        payload = campaign.payload_without_id()
        payload["campaign_id"] = campaign.campaign_id
        return payload


@dataclass(frozen=True)
class DryRunReceipt:
    campaign_id: str
    entry_id: str
    status: str
    process_exit_code: int
    launch_validation_passed: bool
    controller_started: bool
    telemetry_event_count: int
    stable_step_identity_count: int
    confidence_observation_count: int
    execution_label_join_count: int
    censored_excluded_count: int
    ambiguous_excluded_count: int
    technical_failure_count: int
    inline_rgb_detected: bool
    secret_scan_passed: bool
    excluded_from_formal_fitting: bool
    formal_memory_used: bool
    output_manifest_sha256: str
    task_completed: Optional[bool] = None
    errors: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    requested_seed: str = ""
    effective_seed: str = ""
    environment_started: bool = False
    requested_model: str = ""
    returned_models: tuple[str, ...] = ()
    model_profile_id: str = ""
    reasoning_effort: str = ""
    expected_provider_call_count: int = 0
    actual_provider_call_count: int = 0
    provider_call_count_matches_expected: bool = False
    dry_run_root_guard_passed: bool = False
    trace_sha256: str = ""
    truth_receipt_id: str = ""
    task: str = ""
    difficulty: str = ""
    fallback_metrics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in DRY_RUN_STATUSES:
            raise ValueError(f"Unknown dry-run status {self.status!r}")
        integer_values = (
            self.telemetry_event_count,
            self.stable_step_identity_count,
            self.confidence_observation_count,
            self.execution_label_join_count,
            self.censored_excluded_count,
            self.ambiguous_excluded_count,
            self.technical_failure_count,
            self.expected_provider_call_count,
            self.actual_provider_call_count,
        )
        if any(value < 0 for value in integer_values):
            raise ValueError("Dry-run counts cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["errors"] = list(self.errors)
        payload["metadata"] = dict(self.metadata)
        payload["returned_models"] = list(self.returned_models)
        payload["fallback_metrics"] = dict(self.fallback_metrics)
        return payload


@dataclass(frozen=True)
class DryRunAuditReport:
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    summary: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "summary": dict(self.summary),
        }


def build_dry_run_campaign(
    *,
    blueprint: RealExperimentBlueprint,
    selected_group_ids: Sequence[str],
    source_commit: str,
    phase_state: Optional[ExperimentPhaseState] = None,
    require_confidence_observations: bool = True,
    require_execution_label_joins: bool = True,
) -> DryRunCampaign:
    selected = tuple(dict.fromkeys(str(value) for value in selected_group_ids))
    if not 1 <= len(selected) <= 6:
        raise ValueError("Select between one and six preregistered dev_train groups")
    assignment_map = {
        item.group_id: item
        for item in blueprint.development_assignments
        if item.role == "dev_train"
    }
    unknown = set(selected) - set(assignment_map)
    if unknown:
        raise ValueError(f"Dry run selected non-dev_train groups: {sorted(unknown)}")
    budget = next(
        item for item in blueprint.phase_budgets if item.phase == "dry_run"
    )
    entries: list[DryRunCampaignEntry] = []
    for group_id in selected:
        assignment = assignment_map[group_id]
        launch = validate_real_experiment_launch(
            blueprint=blueprint,
            phase="dry_run_completed",
            task=assignment.task,
            seed=assignment.seed,
            max_execution_attempts=min(
                budget.maximum_replans_per_episode + 1,
                1,
            ),
            phase_state=phase_state,
            run_manifest_ids={"dry_run_group": group_id},
        )
        entry_payload = {
            "blueprint_id": blueprint.blueprint_id,
            "group_id": group_id,
            "task": assignment.task,
            "seed": assignment.seed,
            "source_commit": source_commit,
        }
        entry_id = hashlib.sha256(_canonical_json(entry_payload)).hexdigest()
        entries.append(
            DryRunCampaignEntry(
                entry_id=entry_id,
                group_id=group_id,
                task=assignment.task,
                seed=assignment.seed,
                maximum_high_level_steps=budget.maximum_high_level_steps_per_episode,
                maximum_llm_calls=budget.maximum_llm_calls_per_episode,
                maximum_replans=budget.maximum_replans_per_episode,
                timeout_seconds=budget.timeout_seconds_per_episode,
                launch_trace=launch.to_trace_payload(),
            )
        )
    return DryRunCampaign(
        campaign_name=f"{blueprint.blueprint_name}-tiny-dry-run",
        blueprint_id=blueprint.blueprint_id,
        source_commit=source_commit,
        entries=tuple(entries),
        require_confidence_observations=require_confidence_observations,
        require_execution_label_joins=require_execution_label_joins,
        use_formal_memory=False,
    ).with_id()


def audit_dry_run(
    campaign: DryRunCampaign,
    receipts: Sequence[DryRunReceipt],
) -> DryRunAuditReport:
    errors: list[str] = []
    warnings: list[str] = []
    expected = {item.entry_id: item for item in campaign.entries}
    actual: dict[str, DryRunReceipt] = {}
    for receipt in receipts:
        if receipt.entry_id in actual:
            errors.append(f"Duplicate receipt for {receipt.entry_id}")
        actual[receipt.entry_id] = receipt
        if receipt.campaign_id != campaign.campaign_id:
            errors.append(f"{receipt.entry_id}: campaign ID mismatch")
    missing = set(expected) - set(actual)
    extra = set(actual) - set(expected)
    if missing:
        errors.append(f"Missing dry-run receipts: {sorted(missing)}")
    if extra:
        errors.append(f"Unexpected dry-run receipts: {sorted(extra)}")

    for entry_id, receipt in actual.items():
        if entry_id not in expected:
            continue
        if receipt.status != "pipeline_pass":
            errors.append(f"{entry_id}: pipeline status is {receipt.status}")
        if receipt.process_exit_code != 0:
            errors.append(f"{entry_id}: process exit code {receipt.process_exit_code}")
        if not receipt.launch_validation_passed:
            errors.append(f"{entry_id}: launch validation failed")
        if not receipt.controller_started:
            errors.append(f"{entry_id}: Controller did not start")
        if receipt.telemetry_event_count <= 0:
            errors.append(f"{entry_id}: no telemetry events")
        if receipt.stable_step_identity_count <= 0:
            errors.append(f"{entry_id}: no stable step identities")
        if campaign.require_confidence_observations and (
            receipt.confidence_observation_count <= 0
        ):
            errors.append(f"{entry_id}: no confidence observations")
        if campaign.require_execution_label_joins and (
            receipt.execution_label_join_count <= 0
        ):
            errors.append(f"{entry_id}: no execution-label joins")
        if receipt.inline_rgb_detected:
            errors.append(f"{entry_id}: inline RGB found in JSON/log outputs")
        if not receipt.secret_scan_passed:
            errors.append(f"{entry_id}: secret scan failed")
        if not receipt.excluded_from_formal_fitting:
            errors.append(f"{entry_id}: dry-run data was not excluded")
        if receipt.formal_memory_used:
            errors.append(f"{entry_id}: formal long-term memory was used")
        if not receipt.output_manifest_sha256:
            errors.append(f"{entry_id}: output manifest hash missing")
        if receipt.errors:
            errors.extend(f"{entry_id}: {value}" for value in receipt.errors)
        if receipt.technical_failure_count:
            errors.append(
                f"{entry_id}: {receipt.technical_failure_count} technical failures"
            )
        if receipt.task_completed is False:
            warnings.append(
                f"{entry_id}: task was not completed, but task success is "
                "not required for a pipeline dry run"
            )
        if not receipt.fallback_metrics:
            errors.append(f"{entry_id}: structured fallback metrics missing")

    return DryRunAuditReport(
        eligible=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        summary={
            "campaign_id": campaign.campaign_id,
            "expected_entry_count": len(expected),
            "receipt_count": len(receipts),
            "pipeline_pass_count": sum(
                receipt.status == "pipeline_pass" for receipt in receipts
            ),
            "task_completed_count": sum(
                receipt.task_completed is True for receipt in receipts
            ),
            "total_telemetry_events": sum(
                receipt.telemetry_event_count for receipt in receipts
            ),
            "total_label_joins": sum(
                receipt.execution_label_join_count for receipt in receipts
            ),
            "natural_completion_count": sum(
                bool(receipt.fallback_metrics.get("natural_completion", False))
                for receipt in receipts
            ),
            "fallback_assisted_completion_count": sum(
                bool(
                    receipt.fallback_metrics.get(
                        "fallback_assisted_completion", False
                    )
                )
                for receipt in receipts
            ),
            "fallback_trigger_count": sum(
                int(receipt.fallback_metrics.get("fallback_trigger_count", 0) or 0)
                for receipt in receipts
            ),
            "total_injected_logs": sum(
                int(receipt.fallback_metrics.get("total_injected_logs", 0) or 0)
                for receipt in receipts
            ),
            "total_natural_collection_attempts": sum(
                int(
                    receipt.fallback_metrics.get(
                        "total_natural_collection_attempts", 0
                    )
                    or 0
                )
                for receipt in receipts
            ),
            "planner_calls": sum(
                int(receipt.fallback_metrics.get("planner_calls", 0) or 0)
                for receipt in receipts
            ),
            "reflection_calls": sum(
                int(receipt.fallback_metrics.get("reflection_calls", 0) or 0)
                for receipt in receipts
            ),
            "evaluation_chain_calls": sum(
                int(receipt.fallback_metrics.get("evaluation_chain_calls", 0) or 0)
                for receipt in receipts
            ),
        },
    )


def receipt_from_stage6_result(
    *,
    campaign: DryRunCampaign,
    entry_id: str,
    result: Optional[TaskRunResult],
    output_root: str | Path,
    process_exit_code: int,
    launch_validation_passed: bool,
    formal_memory_used: bool,
    exception: Optional[BaseException] = None,
    truth_evidence: Optional[Mapping[str, Any]] = None,
    fallback_metrics: Optional[Mapping[str, Any]] = None,
) -> DryRunReceipt:
    entry_ids = {entry.entry_id for entry in campaign.entries}
    if entry_id not in entry_ids:
        raise ValueError(f"Unknown dry-run campaign entry {entry_id!r}")
    mark_dry_run_output_root(
        output_root,
        campaign_id=campaign.campaign_id,
        entry_id=entry_id,
    )
    scan = scan_dry_run_output_root(output_root)
    event_count = 0
    controller_started = False
    stable_step_identity_count = 0
    confidence_count = int(scan["confidence_observation_count"])
    if result is not None:
        event_count = len(result.events)
        controller_started = result.controller_execution_count > 0
        if result.final_plan is not None:
            stable_step_identity_count = len(result.final_plan.steps)
        for event in result.events:
            if event.event_type == "passive_confidence_collected":
                confidence_count += int(event.payload.get("observation_count", 0) or 0)
    errors = list(scan["errors"])
    if exception is not None:
        errors.append(f"{type(exception).__name__}: {exception}")
    truth = dict(truth_evidence or {})
    expected_calls = int(truth.get("expected_provider_call_count", 0) or 0)
    actual_calls = int(truth.get("actual_provider_call_count", 0) or 0)
    truth_payload = {
        "campaign_id": campaign.campaign_id,
        "entry_id": entry_id,
        "task": str(truth.get("task", "")),
        "difficulty": str(truth.get("difficulty", "")),
        "requested_seed": str(truth.get("requested_seed", "")),
        "effective_seed": str(truth.get("effective_seed", "")),
        "trace_sha256": str(truth.get("trace_sha256", "")),
    }
    truth_receipt_id = hashlib.sha256(_canonical_json(truth_payload)).hexdigest()
    return DryRunReceipt(
        campaign_id=campaign.campaign_id,
        entry_id=entry_id,
        status=(
            "pipeline_pass"
            if process_exit_code == 0
            and exception is None
            and not errors
            else "pipeline_fail"
        ),
        process_exit_code=process_exit_code,
        launch_validation_passed=launch_validation_passed,
        controller_started=controller_started,
        telemetry_event_count=event_count,
        stable_step_identity_count=stable_step_identity_count,
        confidence_observation_count=confidence_count,
        execution_label_join_count=int(scan["execution_label_join_count"]),
        censored_excluded_count=int(scan["censored_excluded_count"]),
        ambiguous_excluded_count=int(scan["ambiguous_excluded_count"]),
        technical_failure_count=int(scan["technical_failure_count"]),
        inline_rgb_detected=bool(scan["inline_rgb_detected"]),
        secret_scan_passed=bool(scan["secret_scan_passed"]),
        excluded_from_formal_fitting=True,
        formal_memory_used=formal_memory_used,
        output_manifest_sha256=str(scan["output_manifest_sha256"]),
        task_completed=result.success if result is not None else None,
        errors=tuple(errors),
        metadata={
            "dry_run_output_root_marker": DRY_RUN_MARKER,
            "provider_model_identity_validation": (
                "approved_alias_policy"
                if truth.get("provider_model_alias_policy_id", "")
                else "strict_identity_match"
            ),
            "provider_model_alias_policy_id": str(
                truth.get("provider_model_alias_policy_id", "")
            ),
        },
        requested_seed=str(truth.get("requested_seed", "")),
        effective_seed=str(truth.get("effective_seed", "")),
        environment_started=bool(truth.get("environment_started", False)),
        requested_model=str(truth.get("requested_model", "")),
        returned_models=tuple(truth.get("returned_models", ())),
        model_profile_id=str(truth.get("model_profile_id", "")),
        reasoning_effort=str(truth.get("reasoning_effort", "")),
        expected_provider_call_count=expected_calls,
        actual_provider_call_count=actual_calls,
        provider_call_count_matches_expected=(expected_calls == actual_calls),
        dry_run_root_guard_passed=bool(
            truth.get("dry_run_root_guard_passed", False)
        ),
        trace_sha256=str(truth.get("trace_sha256", "")),
        truth_receipt_id=truth_receipt_id,
        task=str(truth.get("task", "")),
        difficulty=str(truth.get("difficulty", "")),
        fallback_metrics=dict(fallback_metrics or {}),
    )


def save_receipt(path: str | Path, receipt: DryRunReceipt) -> None:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite dry-run receipt: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def save_campaign(path: str | Path, campaign: DryRunCampaign) -> str:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite campaign: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    campaign = campaign.with_id()
    output.write_text(
        json.dumps(campaign.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return campaign.campaign_id


def load_campaign(path: str | Path) -> DryRunCampaign:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["entries"] = tuple(
        DryRunCampaignEntry(**item) for item in payload["entries"]
    )
    return DryRunCampaign(**payload)


def load_receipt(path: str | Path) -> DryRunReceipt:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["errors"] = tuple(payload.get("errors", ()))
    return DryRunReceipt(**payload)
