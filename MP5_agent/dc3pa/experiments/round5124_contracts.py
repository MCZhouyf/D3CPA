"""Immutable contracts for the Round 5.12.4 standard closeout."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping


SCHEMA_VERSION = 1
STANDARDIZATION_DECISION = (
    "The two Controller repairs and the maximum-step adjustments are "
    "execution-layer fixes that do not change the scientific method, task "
    "definitions, seeds, observations, Paper Memory V5, prompts, formal Log "
    "Bootstrap, success criterion, decision-label definition, or "
    "reliability-feature semantics. Therefore all 60 accepted units and all "
    "528/153 accepted decision records are valid and are analyzed as one "
    "standard development experiment."
)
FORBIDDEN_FUSION_FEATURES = frozenset(
    {
        "task",
        "difficulty",
        "controller",
        "controller_identity",
        "source_commit",
        "runtime_segment",
        "segment_id",
        "budget",
        "execution_budget",
        "memory_count",
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


def _required(*values: str) -> None:
    if any(not str(value).strip() for value in values):
        raise ValueError("Required identity is missing")


@dataclass(frozen=True)
class StandardizationDecision:
    approved_by: str
    decision_text: str
    source_prompt_sha256: str
    effective_date: str
    all_60_units_accepted: bool
    all_681_records_accepted: bool
    no_development_rerun: bool
    standard_scientific_condition: bool
    runtime_segment_modeling: bool
    runtime_segment_is_predictive_feature: bool
    runtime_segment_is_eligibility_gate: bool
    one_frozen_runtime_required_for_holdout: bool
    model_identity_differences_ignored: bool
    schema_version: int = SCHEMA_VERSION
    decision_id: str = ""

    def __post_init__(self) -> None:
        _required(
            self.approved_by,
            self.decision_text,
            self.source_prompt_sha256,
            self.effective_date,
        )
        if self.decision_text != STANDARDIZATION_DECISION:
            raise ValueError("Standardization decision text changed")
        if not all(
            (
                self.all_60_units_accepted,
                self.all_681_records_accepted,
                self.no_development_rerun,
                self.standard_scientific_condition,
                self.one_frozen_runtime_required_for_holdout,
                self.model_identity_differences_ignored,
            )
        ):
            raise ValueError("Standardization decision is incomplete")
        if any(
            (
                self.runtime_segment_modeling,
                self.runtime_segment_is_predictive_feature,
                self.runtime_segment_is_eligibility_gate,
            )
        ):
            raise ValueError("Runtime segment cannot affect standard analysis")
        expected = self.compute_decision_id()
        if self.decision_id and self.decision_id != expected:
            raise ValueError("Standardization decision hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("decision_id", None)
        return payload

    def compute_decision_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "StandardizationDecision":
        return replace(self, decision_id=self.compute_decision_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.decision_id else self.with_id()
        return {**item.payload_without_id(), "decision_id": item.decision_id}


@dataclass(frozen=True)
class StandardIntegrityCounts:
    resolved_units: int
    train_units: int
    tune_units: int
    task_successes: int
    scientific_failures: int
    pending_units: int
    train_decisions: int
    tune_decisions: int
    failed_attempt_decision_contamination: int
    duplicate_accepted_decision_ids: int
    formal_memory_writes: int
    acquisition_store_writes: int
    evaluation_chain_calls: int
    holdout_accesses_or_records: int
    final_accesses_or_records: int
    mine_sand_records: int
    paper_memory_v5_snapshot_roots: int

    def __post_init__(self) -> None:
        expected = {
            "resolved_units": 60,
            "train_units": 45,
            "tune_units": 15,
            "task_successes": 36,
            "scientific_failures": 24,
            "pending_units": 0,
            "train_decisions": 528,
            "tune_decisions": 153,
            "failed_attempt_decision_contamination": 0,
            "duplicate_accepted_decision_ids": 0,
            "formal_memory_writes": 0,
            "acquisition_store_writes": 0,
            "evaluation_chain_calls": 0,
            "holdout_accesses_or_records": 0,
            "final_accesses_or_records": 0,
            "mine_sand_records": 0,
            "paper_memory_v5_snapshot_roots": 1,
        }
        actual = asdict(self)
        if actual != expected:
            raise ValueError(f"Standard development integrity failed: {actual}")

    @property
    def total_decisions(self) -> int:
        return self.train_decisions + self.tune_decisions

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "total_decisions": self.total_decisions}


@dataclass(frozen=True)
class StandardReplacementLineage:
    assignment_id: str
    task: str
    seed: str
    role: str
    old_failed_attempt_ids: tuple[str, ...]
    old_failed_attempt_sha256: tuple[str, ...]
    replacement_attempt_id: str
    replacement_attempt_sha256: str
    authorization_id: str
    old_failed_attempt_rows: int
    old_failed_attempt_rows_included: int
    resumed_accepted_rows: int
    accepted_final_attempts: int
    final_status: str
    schema_version: int = SCHEMA_VERSION
    lineage_id: str = ""

    def __post_init__(self) -> None:
        _required(
            self.assignment_id,
            self.task,
            self.seed,
            self.role,
            self.replacement_attempt_id,
            self.replacement_attempt_sha256,
            self.authorization_id,
            self.final_status,
        )
        if self.assignment_id != "dev_train:medium:mine coal ore:3":
            raise ValueError("Unexpected resumed assignment")
        if self.task != "mine coal ore" or self.role != "dev_train":
            raise ValueError("Resumed assignment identity changed")
        if len(self.old_failed_attempt_ids) != 1:
            raise ValueError("Expected exactly one old failed attempt")
        if len(self.old_failed_attempt_sha256) != 1:
            raise ValueError("Old failed attempt hash is missing")
        if (
            self.old_failed_attempt_rows,
            self.old_failed_attempt_rows_included,
            self.resumed_accepted_rows,
            self.accepted_final_attempts,
        ) != (17, 0, 8, 1):
            raise ValueError("Resumed replacement accounting changed")
        if self.final_status != "completed_success":
            raise ValueError("Resumed replacement is not a success")
        expected = self.compute_lineage_id()
        if self.lineage_id and self.lineage_id != expected:
            raise ValueError("Replacement lineage hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("lineage_id", None)
        payload["old_failed_attempt_ids"] = list(self.old_failed_attempt_ids)
        payload["old_failed_attempt_sha256"] = list(
            self.old_failed_attempt_sha256
        )
        return payload

    def compute_lineage_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "StandardReplacementLineage":
        return replace(self, lineage_id=self.compute_lineage_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.lineage_id else self.with_id()
        return {**item.payload_without_id(), "lineage_id": item.lineage_id}


@dataclass(frozen=True)
class StandardDevelopmentDatasetAcceptance:
    acceptance_name: str
    source_commit: str
    standardization_decision_id: str
    assignment_manifest_id: str
    assignment_manifest_sha256: str
    effective_status_sha256: str
    train_dataset_id: str
    train_jsonl_sha256: str
    tune_dataset_id: str
    tune_jsonl_sha256: str
    paper_memory_v5_release_id: str
    paper_memory_v5_snapshot_root_sha256: str
    active_taskset_release_id: str
    analysis_policy_id: str
    formal_log_bootstrap_policy_id: str
    historical_runtime_segment_manifest_id: str
    historical_runtime_segment_manifest_sha256: str
    replacement_lineage: StandardReplacementLineage
    integrity: StandardIntegrityCounts
    standard_scientific_condition: bool
    mixed_runtime_modeling: bool
    runtime_segment_is_predictive_feature: bool
    runtime_segment_is_eligibility_gate: bool
    holdout_opened: bool
    fusion_fitted: bool
    final_evaluation_opened: bool
    eligible: bool
    errors: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION
    acceptance_id: str = ""

    def __post_init__(self) -> None:
        _required(
            self.acceptance_name,
            self.source_commit,
            self.standardization_decision_id,
            self.assignment_manifest_id,
            self.assignment_manifest_sha256,
            self.effective_status_sha256,
            self.train_dataset_id,
            self.train_jsonl_sha256,
            self.tune_dataset_id,
            self.tune_jsonl_sha256,
            self.paper_memory_v5_release_id,
            self.paper_memory_v5_snapshot_root_sha256,
            self.active_taskset_release_id,
            self.analysis_policy_id,
            self.formal_log_bootstrap_policy_id,
            self.historical_runtime_segment_manifest_id,
            self.historical_runtime_segment_manifest_sha256,
        )
        if not self.standard_scientific_condition or self.mixed_runtime_modeling:
            raise ValueError("Dataset is not accepted as one standard condition")
        if self.runtime_segment_is_predictive_feature:
            raise ValueError("Runtime segment cannot be a Fusion feature")
        if self.runtime_segment_is_eligibility_gate:
            raise ValueError("Runtime segment cannot gate standard eligibility")
        if self.holdout_opened or self.fusion_fitted or self.final_evaluation_opened:
            raise ValueError("Acceptance opened a protected phase")
        if not self.eligible or self.errors:
            raise ValueError("Cannot freeze an ineligible standard acceptance")
        if self.integrity.total_decisions != 681:
            raise ValueError("Standard acceptance must bind 681 decisions")
        expected = self.compute_acceptance_id()
        if self.acceptance_id and self.acceptance_id != expected:
            raise ValueError("Standard acceptance hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("acceptance_id", None)
        payload["replacement_lineage"] = self.replacement_lineage.to_dict()
        payload["integrity"] = self.integrity.to_dict()
        payload["errors"] = list(self.errors)
        return payload

    def compute_acceptance_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "StandardDevelopmentDatasetAcceptance":
        return replace(self, acceptance_id=self.compute_acceptance_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.acceptance_id else self.with_id()
        return {**item.payload_without_id(), "acceptance_id": item.acceptance_id}


@dataclass(frozen=True)
class StandardDevelopmentCloseout:
    closeout_name: str
    source_commit: str
    acceptance_id: str
    development_success_rate: float
    train_label_counts: Mapping[str, int]
    tune_label_counts: Mapping[str, int]
    train_group_count: int
    tune_group_count: int
    train_task_count: int
    tune_task_count: int
    holdout_opened: bool
    fusion_fitted: bool
    final_evaluation_opened: bool
    eligible: bool
    schema_version: int = SCHEMA_VERSION
    closeout_id: str = ""

    def __post_init__(self) -> None:
        _required(self.closeout_name, self.source_commit, self.acceptance_id)
        if not math.isclose(self.development_success_rate, 0.6):
            raise ValueError("Standard development success rate changed")
        if dict(self.train_label_counts) != {"false": 80, "true": 448}:
            raise ValueError("Train label accounting changed")
        if dict(self.tune_label_counts) != {"false": 25, "true": 128}:
            raise ValueError("Tune label accounting changed")
        if (
            self.train_group_count,
            self.tune_group_count,
            self.train_task_count,
            self.tune_task_count,
        ) != (45, 15, 15, 5):
            raise ValueError("Standard closeout group/task accounting changed")
        if self.holdout_opened or self.fusion_fitted or self.final_evaluation_opened:
            raise ValueError("Closeout opened a protected phase")
        if not self.eligible:
            raise ValueError("Cannot freeze an ineligible closeout")
        expected = self.compute_closeout_id()
        if self.closeout_id and self.closeout_id != expected:
            raise ValueError("Standard closeout hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("closeout_id", None)
        payload["train_label_counts"] = dict(sorted(self.train_label_counts.items()))
        payload["tune_label_counts"] = dict(sorted(self.tune_label_counts.items()))
        return payload

    def compute_closeout_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "StandardDevelopmentCloseout":
        return replace(self, closeout_id=self.compute_closeout_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.closeout_id else self.with_id()
        return {**item.payload_without_id(), "closeout_id": item.closeout_id}


@dataclass(frozen=True)
class L2ProvenanceAudit:
    case: int
    source_commit: str
    source_paths: tuple[str, ...]
    source_json_pointers: tuple[str, ...]
    candidate_values: tuple[float, ...]
    loss_definition: str
    regularization_definition: str
    intercept_regularized: bool
    feature_scaling: str
    sample_weighting: str
    development_outcomes_existed_when_frozen: bool
    numeric_value_invented: bool
    eligible_for_fit: bool
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    def __post_init__(self) -> None:
        if self.case not in {1, 2, 3}:
            raise ValueError("L2 provenance case must be 1, 2, or 3")
        if self.development_outcomes_existed_when_frozen:
            raise ValueError("L2 provenance is not pre-outcome")
        if self.numeric_value_invented:
            raise ValueError("L2 value was invented post hoc")
        if self.case == 2:
            _required(self.source_commit, *self.source_paths)
            if self.candidate_values != (1e-3,):
                raise ValueError("Historical fixed L2 must be the one-element grid 1e-3")
            if not self.eligible_for_fit:
                raise ValueError("Valid historical fixed L2 should permit fitting")
        elif self.case == 3:
            if self.candidate_values or self.eligible_for_fit:
                raise ValueError("Case 3 must stop before fitting")
        elif not self.candidate_values:
            raise ValueError("Case 1 requires a historical candidate grid")
        if self.loss_definition != "mean_binary_negative_log_likelihood":
            raise ValueError("Historical trainer loss changed")
        if self.regularization_definition != "0.5*l2*sum(beta_j^2)":
            raise ValueError("Historical L2 definition changed")
        if self.intercept_regularized:
            raise ValueError("Historical trainer did not regularize the intercept")
        if self.feature_scaling != "none_features_used_on_native_0_1_scale":
            raise ValueError("Historical feature scaling changed")
        if self.sample_weighting != "equal_per_decision_record":
            raise ValueError("Historical sample weighting changed")
        expected = self.compute_audit_id()
        if self.audit_id and self.audit_id != expected:
            raise ValueError("L2 provenance audit hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("audit_id", None)
        payload["source_paths"] = list(self.source_paths)
        payload["source_json_pointers"] = list(self.source_json_pointers)
        payload["candidate_values"] = list(self.candidate_values)
        return payload

    def compute_audit_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "L2ProvenanceAudit":
        return replace(self, audit_id=self.compute_audit_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.audit_id else self.with_id()
        return {**item.payload_without_id(), "audit_id": item.audit_id}


@dataclass(frozen=True)
class Round5124BootstrapPolicy:
    historical_activation_policy_id: str
    historical_activation_policy_sha256: str
    primary_bootstrap_unit: str
    secondary_sensitivity_bootstrap_unit: str
    decision_row_iid_bootstrap_forbidden: bool
    primary_controls_activation: bool
    secondary_can_override_activation: bool
    bootstrap_replicates: int
    bootstrap_seed: int
    confidence_level: float
    reliability_bins: int
    noninferiority_margins: Mapping[str, float]
    minimum_effects: Mapping[str, float]
    minimum_primary_improvements: int
    require_improvement_ci_upper_at_most_zero: bool
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        _required(
            self.historical_activation_policy_id,
            self.historical_activation_policy_sha256,
        )
        if self.primary_bootstrap_unit != "task":
            raise ValueError("Primary bootstrap must group by task")
        if self.secondary_sensitivity_bootstrap_unit != "task_seed_run":
            raise ValueError("Secondary bootstrap must group by task-seed/run")
        if not self.decision_row_iid_bootstrap_forbidden:
            raise ValueError("Decision-row IID bootstrap must be forbidden")
        if not self.primary_controls_activation or self.secondary_can_override_activation:
            raise ValueError("Sensitivity bootstrap cannot control activation")
        if (self.bootstrap_replicates, self.bootstrap_seed) != (2000, 5102026):
            raise ValueError("Historical bootstrap settings changed")
        if not math.isclose(self.confidence_level, 0.95):
            raise ValueError("Historical confidence level changed")
        if self.reliability_bins != 10:
            raise ValueError("Historical reliability bins changed")
        if dict(self.noninferiority_margins) != {
            "brier": 0.01,
            "ece": 0.02,
            "nll": 0.02,
        }:
            raise ValueError("Historical noninferiority margins changed")
        if dict(self.minimum_effects) != {
            "brier": 0.005,
            "ece": 0.0,
            "nll": 0.01,
        }:
            raise ValueError("Historical minimum effects changed")
        if self.minimum_primary_improvements != 1:
            raise ValueError("Historical activation rule changed")
        if not self.require_improvement_ci_upper_at_most_zero:
            raise ValueError("Historical improvement CI rule changed")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("Round 5.12.4 bootstrap policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["noninferiority_margins"] = dict(
            sorted(self.noninferiority_margins.items())
        )
        payload["minimum_effects"] = dict(sorted(self.minimum_effects.items()))
        return payload

    def compute_policy_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "Round5124BootstrapPolicy":
        return replace(self, policy_id=self.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.policy_id else self.with_id()
        return {**item.payload_without_id(), "policy_id": item.policy_id}


def assert_standard_fusion_feature_names(names: tuple[str, ...]) -> None:
    normalized = {str(name).strip().lower() for name in names}
    forbidden = normalized.intersection(FORBIDDEN_FUSION_FEATURES)
    if forbidden:
        raise ValueError(f"Forbidden Fusion predictive features: {sorted(forbidden)}")
