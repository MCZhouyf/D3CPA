"""Fail-closed contracts for reconciling the Round 5.11 development campaign."""

from __future__ import annotations

import hashlib
import json
import signal
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .formal_acquisition_execution import TECHNICAL_FAILURE_CATEGORIES


SCHEMA_VERSION = 1
ROUND511_INELIGIBLE_CLOSEOUT_ID = (
    "4c168032881eda6def4235001bcf43e576e8c1f80601f3e5127acb09237e2e8f"
)
ROUND512_CLOSEOUT_SHA = "469c98ad085e2b8d68acbd92208d7a635492ebe6"
MISSING_BUDGET_FIELDS = (
    "max_execution_attempts",
    "max_explore_steps",
    "episode_timeout_seconds",
)
BUDGET_SOURCE_HIERARCHY = (
    "attempt_start_bound_config",
    "campaign_manifest",
    "exact_cli_manifest",
    "source_constant_with_no_override_proof",
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


def _load_json(path: str | Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


@dataclass(frozen=True)
class ClassificationRule:
    category: str
    required_signals: tuple[str, ...]
    accepted_values: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.category not in TECHNICAL_FAILURE_CATEGORIES:
            raise ValueError(f"Unapproved technical category: {self.category}")
        if not self.required_signals:
            raise ValueError("A classification rule needs structured signals")
        if any("detail" in name or "message" in name or "text" in name for name in self.required_signals):
            raise ValueError("Free-text classification signals are forbidden")

    def matches(self, signals: Mapping[str, Any]) -> bool:
        for name in self.required_signals:
            if name not in signals or signals[name] in (None, ""):
                return False
            allowed = self.accepted_values.get(name)
            if allowed is not None and signals[name] not in allowed:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "required_signals": list(self.required_signals),
            "accepted_values": {
                key: list(values)
                for key, values in sorted(self.accepted_values.items())
            },
        }


def _default_rules() -> tuple[ClassificationRule, ...]:
    # Ordering resolves overlap from the most specific failure to process crash.
    return (
        ClassificationRule(
            "environment_start_failure",
            ("environment_construction_status", "exception_class", "exception_module"),
            {"environment_construction_status": ("failed",)},
        ),
        ClassificationRule(
            "seed_application_failure",
            ("seed_application_status", "requested_seed", "effective_seed_status"),
            {
                "seed_application_status": ("failed",),
                "effective_seed_status": ("missing", "mismatch", "unapplied"),
            },
        ),
        ClassificationRule(
            "provider_transport_failure",
            ("provider_stage", "provider_transport_status", "exception_class"),
            {
                "provider_stage": ("request", "response"),
                "provider_transport_status": ("failed", "timeout", "rate_limited"),
            },
        ),
        ClassificationRule(
            "provider_empty_response",
            ("provider_stage", "provider_response_status"),
            {
                "provider_stage": ("response",),
                "provider_response_status": ("empty", "invalid"),
            },
        ),
        ClassificationRule(
            "infrastructure_timeout",
            ("timeout_stage", "watchdog_status"),
            {"watchdog_status": ("timed_out", "terminated")},
        ),
        ClassificationRule(
            "receipt_write_failure",
            ("receipt_write_status", "exception_class", "exception_module"),
            {"receipt_write_status": ("failed",)},
        ),
        ClassificationRule(
            "trace_write_failure",
            ("trace_write_status", "exception_class", "exception_module"),
            {"trace_write_status": ("failed",)},
        ),
        ClassificationRule(
            "disk_or_filesystem_failure",
            ("filesystem_write_status", "filesystem_errno", "exception_class"),
            {"filesystem_write_status": ("failed",)},
        ),
        ClassificationRule(
            "process_crash",
            ("process_exit_status", "process_exit_code"),
            {"process_exit_status": ("crashed", "signaled")},
        ),
    )


@dataclass(frozen=True)
class Round511ReconciliationPolicy:
    policy_name: str = "dc3pa-round511-reconciliation-v1"
    closeout_id: str = ROUND511_INELIGIBLE_CLOSEOUT_ID
    round512_closeout_sha: str = ROUND512_CLOSEOUT_SHA
    classification_rules: tuple[ClassificationRule, ...] = field(
        default_factory=_default_rules
    )
    missing_budget_fields: tuple[str, ...] = MISSING_BUDGET_FIELDS
    budget_source_hierarchy: tuple[str, ...] = BUDGET_SOURCE_HIERARCHY
    maximum_technical_retries: int = 2
    originals_are_immutable: bool = True
    ambiguous_is_unclassifiable: bool = True
    free_text_classifier_forbidden: bool = True
    llm_classifier_forbidden: bool = True
    task_outcome_classifier_forbidden: bool = True
    source_constant_requires_no_override_proof: bool = True
    replacement_requires_prospective_approval: bool = True
    failed_attempt_rows_excluded: bool = True
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported reconciliation policy schema")
        if self.closeout_id != ROUND511_INELIGIBLE_CLOSEOUT_ID:
            raise ValueError("The policy must bind the ineligible closeout")
        if self.round512_closeout_sha != ROUND512_CLOSEOUT_SHA:
            raise ValueError("The policy must bind the Round 5.12 closeout commit")
        if {rule.category for rule in self.classification_rules} != set(
            TECHNICAL_FAILURE_CATEGORIES
        ):
            raise ValueError("The frozen technical taxonomy changed")
        if self.missing_budget_fields != MISSING_BUDGET_FIELDS:
            raise ValueError("The discovered budget field set changed")
        if self.budget_source_hierarchy != BUDGET_SOURCE_HIERARCHY:
            raise ValueError("The budget provenance hierarchy changed")
        if self.maximum_technical_retries != 2:
            raise ValueError("The original retry maximum cannot be relaxed")
        safeguards = (
            self.originals_are_immutable,
            self.ambiguous_is_unclassifiable,
            self.free_text_classifier_forbidden,
            self.llm_classifier_forbidden,
            self.task_outcome_classifier_forbidden,
            self.source_constant_requires_no_override_proof,
            self.replacement_requires_prospective_approval,
            self.failed_attempt_rows_excluded,
        )
        if not all(safeguards):
            raise ValueError("Reconciliation safeguards are incomplete")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("Reconciliation policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["classification_rules"] = [
            rule.to_dict() for rule in self.classification_rules
        ]
        return payload

    def compute_policy_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "Round511ReconciliationPolicy":
        return replace(self, policy_id=self.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.policy_id else self.with_id()
        payload = item.payload_without_id()
        payload["policy_id"] = item.policy_id
        return payload


def classify_structured_failure(
    signals: Mapping[str, Any],
    policy: Round511ReconciliationPolicy | None = None,
) -> tuple[str | None, tuple[str, ...]]:
    """Classify only when exactly one frozen structured rule is proven."""
    active = policy or Round511ReconciliationPolicy()
    matches = [rule for rule in active.classification_rules if rule.matches(signals)]
    if len(matches) != 1:
        return None, ()
    rule = matches[0]
    return rule.category, rule.required_signals


def _trace_event_types(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        return ()
    result: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, Mapping):
            result.append(str(payload.get("event_type", "")))
    return tuple(result)


def _structured_attempt_signals(
    summary: Mapping[str, Any], trace_event_types: tuple[str, ...]
) -> dict[str, Any]:
    """Normalize only source-bound fields; never inspect free-text payloads."""
    return_code = summary.get("process_return_code")
    signals: dict[str, Any] = {"process_exit_code": return_code}
    if return_code == 124:
        # The frozen campaign runner returns 124 only from its episode watchdog.
        signals.update(
            {
                "timeout_stage": "stage6_episode",
                "watchdog_status": "timed_out",
            }
        )
    elif isinstance(return_code, int) and return_code < 0:
        signals.update(
            {
                "process_exit_status": "signaled",
                "process_signal": signal.Signals(-return_code).name,
            }
        )
    if "environment_seed_applied" in trace_event_types:
        signals["seed_application_status"] = "applied"
    return signals


def reconcile_technical_failures(
    campaign_root: str | Path,
    *,
    policy: Round511ReconciliationPolicy | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build evidence-only rows for every preceding failed attempt."""
    active = policy or Round511ReconciliationPolicy()
    runs_root = Path(campaign_root) / "runs"
    rows: list[dict[str, Any]] = []
    category_counts: Counter[str] = Counter()
    failed_decision_rows = 0

    for marker_path in sorted(runs_root.glob("*/accepted.json")):
        marker = _load_json(marker_path)
        final_attempt = int(marker.get("attempt", -1))
        for attempt_index in range(final_attempt):
            attempt_root = marker_path.parent / f"attempt-{attempt_index}"
            summary_path = attempt_root / "attempt_summary.json"
            binding_path = attempt_root / "run_binding.json"
            trace_path = attempt_root / "trace.jsonl"
            records_path = attempt_root / "development_decisions.jsonl"
            summary = _load_json(summary_path)
            binding = _load_json(binding_path)
            event_types = _trace_event_types(trace_path)
            signals = _structured_attempt_signals(summary, event_types)
            category, used = classify_structured_failure(signals, active)
            decision_count = 0
            if records_path.is_file():
                decision_count = sum(
                    bool(line.strip())
                    for line in records_path.read_text(encoding="utf-8").splitlines()
                )
            failed_decision_rows += decision_count
            assigned = category or "unclassifiable"
            category_counts[assigned] += 1
            evidence_hashes = {
                "attempt_summary_sha256": sha256_file(summary_path),
                "run_binding_sha256": sha256_file(binding_path),
                "trace_sha256": sha256_file(trace_path) if trace_path.is_file() else None,
            }
            rows.append(
                {
                    "attempt_id": str(summary.get("run_id", "")),
                    "task": str(binding.get("task", "")),
                    "seed": str(binding.get("seed", "")),
                    "role": str(binding.get("role", "")),
                    "group_id": str(binding.get("group_id", "")),
                    "attempt_index": attempt_index,
                    "original_evidence_hashes": evidence_hashes,
                    "structured_signals_used": {name: signals[name] for name in used},
                    "classification_policy_id": active.compute_policy_id(),
                    "assigned_category": assigned,
                    "confidence": "proven" if category else "unclassifiable",
                    "decision_row_count": decision_count,
                    "decision_rows_included_in_final_dataset": 0,
                }
            )

    summary = {
        "technical_attempts": len(rows),
        "classified_attempts": len(rows) - category_counts["unclassifiable"],
        "unclassifiable_attempts": category_counts["unclassifiable"],
        "counts_per_category": dict(sorted(category_counts.items())),
        "failed_attempt_decision_rows_produced": failed_decision_rows,
        "failed_attempt_decision_rows_included": 0,
        "technical_failure_reconciliation_eligible": (
            len(rows) == 40 and category_counts["unclassifiable"] == 0
        ),
        "classification_policy_id": active.compute_policy_id(),
    }
    return rows, summary


def source_budget_proof(repo_root: str | Path, source_commit: str) -> dict[str, Any]:
    """Inspect the exact bound runner source without using current defaults."""
    label = "MP5_agent/scripts_dc3pa/run_round511_development_campaign.py"
    source = subprocess.run(
        ["git", "show", f"{source_commit}:{label}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    source_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    fixed_execution = '"--max-execution-attempts",\n        "4",' in source or (
        "DEVELOPMENT_MAX_EXECUTION_ATTEMPTS = 4" in source
        and 'str(DEVELOPMENT_MAX_EXECUTION_ATTEMPTS)' in source
    )
    fixed_explore = "DEVELOPMENT_MAX_EXPLORE_STEPS = 60" in source and (
        'env["DC3PA_MAX_EXPLORE_STEPS"] = str(DEVELOPMENT_MAX_EXPLORE_STEPS)'
        in source
    )
    timeout_default = 'parser.add_argument("--timeout-seconds", type=int, default=1800)' in source
    return {
        "source_artifact_label": f"git:{source_commit}:{label}",
        "source_artifact_sha256": source_sha,
        "fields": {
            "max_execution_attempts": {
                "status": "proven" if fixed_execution else "unprovable",
                "value": 4 if fixed_execution else None,
                "source_key": "_stage6_command/--max-execution-attempts",
                "no_runtime_override_proof": fixed_execution,
            },
            "max_explore_steps": {
                "status": "proven" if fixed_explore else "unprovable",
                "value": 60 if fixed_explore else None,
                "source_key": "_stage6_environment/DC3PA_MAX_EXPLORE_STEPS",
                "no_runtime_override_proof": fixed_explore,
            },
            "episode_timeout_seconds": {
                "status": "unprovable",
                "value": None,
                "source_key": "build_parser/--timeout-seconds",
                "default_observed": 1800 if timeout_default else None,
                "no_runtime_override_proof": False,
                "reason": "CLI override permitted and no attempt-time command manifest exists",
            },
        },
    }


def reconcile_execution_budgets(
    campaign_root: str | Path,
    *,
    repo_root: str | Path,
    policy: Round511ReconciliationPolicy | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create one provenance row for each missing attempt budget field."""
    active = policy or Round511ReconciliationPolicy()
    attempts = sorted(Path(campaign_root).glob("runs/*/attempt-*"))
    proof_cache: dict[str, Mapping[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    complete_attempts = 0
    partial_profiles: set[tuple[tuple[str, Any], ...]] = set()

    for attempt_root in attempts:
        binding = _load_json(attempt_root / "run_binding.json")
        summary = _load_json(attempt_root / "attempt_summary.json")
        source_commit = str(binding.get("source_commit", ""))
        if source_commit not in proof_cache:
            proof_cache[source_commit] = source_budget_proof(repo_root, source_commit)
        proof = proof_cache[source_commit]
        statuses: list[str] = []
        partial: list[tuple[str, Any]] = []
        for field_name in active.missing_budget_fields:
            field_proof = dict(proof["fields"][field_name])
            status = str(field_proof.pop("status"))
            value = field_proof.pop("value")
            statuses.append(status)
            if status == "proven":
                partial.append((field_name, value))
            rows.append(
                {
                    "attempt_id": str(summary.get("run_id", "")),
                    "field_name": field_name,
                    "reconstructed_value": value,
                    "source_artifact_label": proof["source_artifact_label"],
                    "source_artifact_sha256": proof["source_artifact_sha256"],
                    "source_key": field_proof.pop("source_key"),
                    "proof_that_no_runtime_override_existed": field_proof.pop(
                        "no_runtime_override_proof"
                    ),
                    "reconstruction_status": status,
                    **field_proof,
                }
            )
        if all(status == "proven" for status in statuses):
            complete_attempts += 1
        partial_profiles.add(tuple(partial))

    proven = sum(row["reconstruction_status"] == "proven" for row in rows)
    unprovable = len(rows) - proven
    summary = {
        "attempts_audited": len(attempts),
        "missing_fields_discovered": len(rows),
        "fields_proven": proven,
        "fields_unprovable": unprovable,
        "attempts_with_complete_proof": complete_attempts,
        "attempts_with_incomplete_proof": len(attempts) - complete_attempts,
        "distinct_complete_budget_profiles": 0 if not complete_attempts else 1,
        "distinct_proven_partial_profiles": len(partial_profiles),
        "budget_reconciliation_eligible": (
            len(attempts) == 100 and len(rows) == 300 and unprovable == 0
        ),
        "reconciliation_policy_id": active.compute_policy_id(),
    }
    return rows, summary


def choose_salvage_path(
    technical_summary: Mapping[str, Any],
    budget_summary: Mapping[str, Any],
    *,
    retry_limit_violations: int,
    contamination_count: int,
    lineage_mismatch_count: int,
    remediation_approval: Round511ReconciliationApproval | None,
) -> dict[str, Any]:
    """Return the mandatory scientific path and currently executable path."""
    blockers: list[str] = []
    if int(technical_summary.get("unclassifiable_attempts", 0)):
        blockers.append("one_or_more_technical_failures_unclassifiable")
    if int(budget_summary.get("fields_unprovable", 0)):
        blockers.append("one_or_more_budget_fields_unprovable")
    if contamination_count:
        blockers.append("failed_attempt_decision_contamination")
    if lineage_mismatch_count:
        blockers.append("attempt_lineage_mismatch")
    if retry_limit_violations != 3:
        blockers.append("protocol_invalid_units_not_limited_to_known_three")
    scientifically_required = "path_b" if blockers else "path_a"
    authorized = (
        remediation_approval is not None
        and remediation_approval.approval_kind == "remediation"
        and remediation_approval.remediation_path == scientifically_required
    )
    return {
        "scientifically_required_path": scientifically_required,
        "selected_path": scientifically_required if authorized else "path_c",
        "salvage_status": "authorized" if authorized else "blocked",
        "reasons": blockers or ["selective_replacement_preconditions_satisfied"],
        "remediation_approval_present": remediation_approval is not None,
        "remediation_approval_id": (
            remediation_approval.with_id().approval_id if remediation_approval else None
        ),
        "mine_dojo_execution_permitted": authorized,
    }


@dataclass(frozen=True)
class Round511ReconciliationApproval:
    approval_name: str
    approved_by: str
    approval_kind: str
    reconciliation_policy_id: str
    closeout_id: str
    round512_closeout_sha: str
    remediation_path: str
    approved_at: str
    original_retry_limit_preserved: bool
    originals_remain_immutable: bool
    holdout_access_forbidden: bool
    outcome_selection_forbidden: bool
    schema_version: int = SCHEMA_VERSION
    approval_id: str = ""

    def __post_init__(self) -> None:
        if self.approved_by != "ZYF":
            raise ValueError("External ZYF approval is required")
        if self.approval_kind not in {"policy_freeze", "remediation"}:
            raise ValueError("Unknown reconciliation approval kind")
        if self.remediation_path not in {"none", "path_a", "path_b"}:
            raise ValueError("Unknown remediation path")
        if self.approval_kind == "policy_freeze" and self.remediation_path != "none":
            raise ValueError("Policy approval cannot authorize execution")
        if self.approval_kind == "remediation" and self.remediation_path == "none":
            raise ValueError("Remediation approval must select Path A or B")
        if self.closeout_id != ROUND511_INELIGIBLE_CLOSEOUT_ID:
            raise ValueError("Approval closeout binding mismatch")
        if self.round512_closeout_sha != ROUND512_CLOSEOUT_SHA:
            raise ValueError("Approval source binding mismatch")
        if self.reconciliation_policy_id != Round511ReconciliationPolicy().compute_policy_id():
            raise ValueError("Approval policy binding mismatch")
        parsed = datetime.fromisoformat(self.approved_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Approval timestamp must include a timezone")
        if not all(
            (
                self.original_retry_limit_preserved,
                self.originals_remain_immutable,
                self.holdout_access_forbidden,
                self.outcome_selection_forbidden,
            )
        ):
            raise ValueError("Approval weakens the reconciliation safeguards")
        expected = self.compute_approval_id()
        if self.approval_id and self.approval_id != expected:
            raise ValueError("Reconciliation approval hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("approval_id", None)
        return payload

    def compute_approval_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "Round511ReconciliationApproval":
        return replace(self, approval_id=self.compute_approval_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.approval_id else self.with_id()
        payload = item.payload_without_id()
        payload["approval_id"] = item.approval_id
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Round511ReconciliationApproval":
        return cls(**dict(payload))
