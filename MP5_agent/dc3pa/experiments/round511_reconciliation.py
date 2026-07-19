"""Fail-closed contracts for reconciling the Round 5.11 development campaign."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
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
