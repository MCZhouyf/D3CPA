"""Frozen CHRM-lite + CDT-lite V4.1 method and statistical contracts.

This module defines the prospective method. It does not fit CHRM-lite, estimate
CDT parameters, activate a trigger, or read holdout data.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
CONFIDENCE_LEVELS = (
    "very_unlikely",
    "unlikely",
    "uncertain",
    "likely",
    "very_likely",
)
ENVIRONMENT_STATES = ("mismatch", "unknown", "matched")
FEATURE_ORDER = ("knowledge_coverage", "knowledge_available", "model_logit", "environment_logit")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


class _HashedContract:
    _id_field: str

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop(self._id_field, None)
        return payload

    def compute_id(self) -> str:
        return _sha(self.payload_without_id())

    def to_dict(self) -> dict[str, Any]:
        identifier = getattr(self, self._id_field)
        item = self if identifier else replace(self, **{self._id_field: self.compute_id()})
        payload = item.payload_without_id()
        payload[self._id_field] = getattr(item, self._id_field)
        return payload


@dataclass(frozen=True)
class CHRMLiteFeatureSchemaV4_1(_HashedContract):
    feature_order: tuple[str, ...] = FEATURE_ORDER
    hard_rules_excluded_from_soft_coverage: bool = True
    hard_gate_bypasses_fusion: bool = True
    no_soft_rules_coverage: float = 0.0
    no_soft_rules_availability: float = 0.0
    confidence_levels: tuple[str, ...] = CONFIDENCE_LEVELS
    confidence_same_planner_generation_required: bool = True
    confidence_extra_online_call_forbidden: bool = True
    environment_states: tuple[str, ...] = ENVIRONMENT_STATES
    environment_top_k_per_side: int = 3
    environment_minimum_count_per_side: int = 3
    environment_tie_break: str = "similarity_desc_exemplar_id_asc"
    environment_empty_or_undercovered_state: str = "unknown"
    gamma_candidate_quantile_pairs: tuple[tuple[float, float], ...] = (
        (0.25, 0.75),
        (1.0 / 3.0, 2.0 / 3.0),
    )
    gamma_source: str = "dev_train_cross_fitted_contrast_quantiles"
    schema_version: int = SCHEMA_VERSION
    schema_id: str = ""

    _id_field = "schema_id"

    def __post_init__(self) -> None:
        if self.feature_order != FEATURE_ORDER:
            raise ValueError("V4.1 feature order changed")
        if self.confidence_levels != CONFIDENCE_LEVELS:
            raise ValueError("V4.1 confidence levels changed")
        if self.environment_states != ENVIRONMENT_STATES:
            raise ValueError("V4.1 Environment states changed")
        if (self.environment_top_k_per_side, self.environment_minimum_count_per_side) != (3, 3):
            raise ValueError("V4.1 bilateral top-3 coverage changed")
        if not all(
            (
                self.hard_rules_excluded_from_soft_coverage,
                self.hard_gate_bypasses_fusion,
                self.confidence_same_planner_generation_required,
                self.confidence_extra_online_call_forbidden,
            )
        ):
            raise ValueError("V4.1 feature safety invariant changed")
        if (self.no_soft_rules_coverage, self.no_soft_rules_availability) != (0.0, 0.0):
            raise ValueError("V4.1 empty soft-rule semantics changed")
        for lower, upper in self.gamma_candidate_quantile_pairs:
            if not 0.0 <= lower < upper <= 1.0:
                raise ValueError("Invalid Environment gamma quantile pair")
        if self.schema_id and self.schema_id != self.compute_id():
            raise ValueError("V4.1 feature schema hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        for key in ("feature_order", "confidence_levels", "environment_states"):
            payload[key] = list(payload[key])
        payload["gamma_candidate_quantile_pairs"] = [
            list(pair) for pair in self.gamma_candidate_quantile_pairs
        ]
        return payload

    def with_id(self) -> "CHRMLiteFeatureSchemaV4_1":
        return replace(self, schema_id=self.compute_id())


@dataclass(frozen=True)
class CHRMLiteLabelPolicyV4_1(_HashedContract):
    main_target: str = "deployment_step_success_within_frozen_budget"
    positive_definition: str = "expected_state_transition_or_local_subgoal_completed"
    allowed_sources: tuple[str, ...] = (
        "minedojo_structured_state",
        "inventory_change",
        "object_or_task_state",
        "controller_return",
        "frozen_evaluator_result",
        "deterministic_join_logic",
    )
    forbidden_sources: tuple[str, ...] = (
        "manual_relabeling",
        "post_hoc_llm_judging",
        "future_holdout_outcomes",
    )
    technical_failures_are_scientific_labels: bool = False
    secondary_target: str = "deterministic_downstream_usefulness_when_available"
    secondary_target_blocks_main_model: bool = False
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        if self.main_target != "deployment_step_success_within_frozen_budget":
            raise ValueError("V4.1 main target changed")
        if self.technical_failures_are_scientific_labels or self.secondary_target_blocks_main_model:
            raise ValueError("V4.1 label isolation changed")
        if not self.allowed_sources or not self.forbidden_sources:
            raise ValueError("V4.1 label provenance is incomplete")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("V4.1 label policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["allowed_sources"] = list(self.allowed_sources)
        payload["forbidden_sources"] = list(self.forbidden_sources)
        return payload

    def with_id(self) -> "CHRMLiteLabelPolicyV4_1":
        return replace(self, policy_id=self.compute_id())


@dataclass(frozen=True)
class CHRMLiteParameterProvenancePolicyV4_1(_HashedContract):
    laplace_alpha: float = 1.0
    model_calibration: str = "weighted_pav_monotonic"
    environment_calibration: str = "weighted_pav_ordered_mismatch_unknown_matched"
    l2_candidates: tuple[float, ...] = (0.0001, 0.001, 0.01)
    l2_selection_split: str = "dev_tune"
    intercept_fitted: bool = True
    intercept_regularized: bool = False
    intercept_initialization: str = "dev_train_base_rate_logit"
    coefficient_constraints: Mapping[str, str] = None  # type: ignore[assignment]
    cdt_primary_cost_unit: str = "planner_equivalent_calls"
    c_eval_source: str = "development_evaluation_call_cost_mean"
    rho_path_selection: str = "choose_A_before_estimation_else_B_before_estimation_else_unidentified"
    rho_path_a_definition: str = "P(revised_success|direct_failure)_matched_state_paired_replay"
    rho_path_b_definition: str = "P(post_success|evaluation_changed_action)_observed_yield_noncausal"
    c_fp_definition: str = "E(delta_cost*I(action_changed)|direct_correct_and_evaluated)"
    l_fail_compute_component: str = "downstream_planner_equivalent_calls"
    terminal_penalty_rule: str = "remaining_episode_seconds_divided_by_dev_train_median_seconds_per_planner_call"
    l_fail_horizon_bins: tuple[str, ...] = ("short", "medium", "long")
    sparse_horizon_rule: str = "shrink_to_dev_train_global_l_fail_mean"
    insufficient_rho_rule: str = "shadow_or_fixed_period"
    tau_max: float = 0.95
    delta: float = 0.05
    m_min: int = 1
    m_max: int = 4
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        if self.coefficient_constraints is None:
            object.__setattr__(
                self,
                "coefficient_constraints",
                {
                    "intercept": "unrestricted",
                    "knowledge_coverage": "nonnegative",
                    "knowledge_available": "unrestricted",
                    "model_logit": "nonnegative",
                    "environment_logit": "nonnegative",
                },
            )
        required = {
            "intercept": "unrestricted",
            "knowledge_coverage": "nonnegative",
            "knowledge_available": "unrestricted",
            "model_logit": "nonnegative",
            "environment_logit": "nonnegative",
        }
        if dict(self.coefficient_constraints) != required:
            raise ValueError("V4.1 coefficient constraints changed")
        if self.laplace_alpha != 1.0 or not self.intercept_fitted or self.intercept_regularized:
            raise ValueError("V4.1 calibration/intercept semantics changed")
        if self.cdt_primary_cost_unit != "planner_equivalent_calls":
            raise ValueError("V4.1 CDT cost unit changed")
        if not 0.0 < self.delta < self.tau_max < 1.0:
            raise ValueError("V4.1 threshold constants are invalid")
        if not 1 <= self.m_min <= self.m_max:
            raise ValueError("V4.1 interval bounds are invalid")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("V4.1 parameter provenance hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["l2_candidates"] = list(self.l2_candidates)
        payload["l_fail_horizon_bins"] = list(self.l_fail_horizon_bins)
        payload["coefficient_constraints"] = dict(sorted(self.coefficient_constraints.items()))
        return payload

    def with_id(self) -> "CHRMLiteParameterProvenancePolicyV4_1":
        return replace(self, policy_id=self.compute_id())


@dataclass(frozen=True)
class CHRMLiteStatisticalAnalysisPolicyV4_1(_HashedContract):
    dev_train_role: str = "fitting_and_task_grouped_cross_fitting"
    dev_tune_role: str = "candidate_selection_and_calibration_audit"
    locked_holdout_role: str = "one_time_confirmation"
    final_evaluation_role: str = "final_endpoint"
    cross_fit_group: str = "terminal_task"
    cross_fit_folds: int = 5
    deterministic_fold_rule: str = "sorted_terminal_tasks_round_robin"
    terminal_task_may_cross_splits: bool = False
    primary_fit_weighting: str = "unweighted_step_level"
    sensitivity_fit_weighting: str = "task_seed_balanced"
    primary_bootstrap_group: str = "terminal_task"
    secondary_bootstrap_group: str = "task_seed_run"
    decision_row_iid_bootstrap_permitted: bool = False
    bootstrap_replicates: int = 2000
    bootstrap_seed: int = 513041
    epsilon_clipping: float = 1e-12
    hard_gate_metrics: tuple[str, ...] = (
        "precision",
        "recall",
        "false_positive_rate",
        "false_negative_rate",
    )
    probabilistic_metrics: tuple[str, ...] = (
        "ece",
        "brier",
        "nll",
        "auroc",
        "auprc",
        "reliability_diagram",
    )
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        if self.cross_fit_group != "terminal_task" or self.primary_bootstrap_group != "terminal_task":
            raise ValueError("V4.1 primary grouping must be terminal task")
        if self.terminal_task_may_cross_splits or self.decision_row_iid_bootstrap_permitted:
            raise ValueError("V4.1 split/bootstrap leakage guard changed")
        if self.cross_fit_folds < 2 or self.bootstrap_replicates < 200:
            raise ValueError("V4.1 statistical resampling is underspecified")
        if not 0.0 < self.epsilon_clipping < 0.5:
            raise ValueError("V4.1 epsilon clipping is invalid")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("V4.1 statistical policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["hard_gate_metrics"] = list(self.hard_gate_metrics)
        payload["probabilistic_metrics"] = list(self.probabilistic_metrics)
        return payload

    def with_id(self) -> "CHRMLiteStatisticalAnalysisPolicyV4_1":
        return replace(self, policy_id=self.compute_id())


@dataclass(frozen=True)
class CHRMLiteCDTLiteMethodContractV4_1(_HashedContract):
    source_commit: str
    feature_schema_id: str
    label_policy_id: str
    parameter_provenance_policy_id: str
    statistical_analysis_policy_id: str
    version: str = "4.1"
    method_name: str = "CHRM-lite + CDT-lite"
    fusion_equation: str = "b+beta_K*k+beta_U*u+beta_L*(logit(pL)-logit(pi0))+beta_E*(logit(pE)-logit(pi0))"
    objective: str = "mean_binary_nll_plus_l2_on_beta_only"
    hard_gate_bypasses_fusion_and_smoothing: bool = True
    evaluation_recomputes_changed_action_features: bool = True
    model_confidence_always_updated_after_evaluation: bool = True
    active_trigger_experiments_permitted: bool = False
    model_fitting_permitted_in_round513a: bool = False
    holdout_access_permitted: bool = False
    final_evaluation_permitted: bool = False
    round6_permitted: bool = False
    schema_version: int = SCHEMA_VERSION
    contract_id: str = ""

    _id_field = "contract_id"

    def __post_init__(self) -> None:
        identities = (
            self.source_commit,
            self.feature_schema_id,
            self.label_policy_id,
            self.parameter_provenance_policy_id,
            self.statistical_analysis_policy_id,
        )
        if not all(identities) or self.version != "4.1":
            raise ValueError("V4.1 method identity is incomplete")
        if not all(
            (
                self.hard_gate_bypasses_fusion_and_smoothing,
                self.evaluation_recomputes_changed_action_features,
                self.model_confidence_always_updated_after_evaluation,
            )
        ):
            raise ValueError("V4.1 method correction is missing")
        if any(
            (
                self.active_trigger_experiments_permitted,
                self.model_fitting_permitted_in_round513a,
                self.holdout_access_permitted,
                self.final_evaluation_permitted,
                self.round6_permitted,
            )
        ):
            raise ValueError("V4.1 contract opened a forbidden phase")
        if self.contract_id and self.contract_id != self.compute_id():
            raise ValueError("V4.1 method contract hash mismatch")

    def with_id(self) -> "CHRMLiteCDTLiteMethodContractV4_1":
        return replace(self, contract_id=self.compute_id())


def knowledge_features(
    hard_rule_satisfaction: Sequence[bool],
    soft_rule_satisfaction: Sequence[bool],
) -> tuple[int, float, int]:
    h_value = int(all(bool(value) for value in hard_rule_satisfaction))
    if not soft_rule_satisfaction:
        return h_value, 0.0, 0
    return (
        h_value,
        sum(bool(value) for value in soft_rule_satisfaction) / len(soft_rule_satisfaction),
        1,
    )


def environment_state(
    compatible: Sequence[tuple[str, float]],
    incompatible: Sequence[tuple[str, float]],
    *,
    gamma_minus: float,
    gamma_plus: float,
    minimum_count_per_side: int = 3,
) -> tuple[str, float | None, tuple[str, ...], tuple[str, ...]]:
    if not gamma_minus < gamma_plus:
        raise ValueError("gamma_minus must be smaller than gamma_plus")
    order = lambda item: (-float(item[1]), str(item[0]))
    positive = tuple(sorted(compatible, key=order)[:3])
    negative = tuple(sorted(incompatible, key=order)[:3])
    if len(positive) < minimum_count_per_side or len(negative) < minimum_count_per_side:
        return "unknown", None, tuple(item[0] for item in positive), tuple(item[0] for item in negative)
    contrast = sum(item[1] for item in positive) / len(positive) - sum(
        item[1] for item in negative
    ) / len(negative)
    if contrast >= gamma_plus:
        state = "matched"
    elif contrast <= gamma_minus:
        state = "mismatch"
    else:
        state = "unknown"
    return state, float(contrast), tuple(item[0] for item in positive), tuple(item[0] for item in negative)


def weighted_pav(values: Sequence[float], weights: Sequence[float]) -> tuple[float, ...]:
    if len(values) != len(weights) or not values:
        raise ValueError("PAV values and weights must be nonempty and aligned")
    blocks: list[list[float]] = []
    for index, (value, weight) in enumerate(zip(values, weights)):
        if weight <= 0:
            raise ValueError("PAV weights must be positive")
        blocks.append([float(value) * float(weight), float(weight), float(index), float(index)])
        while len(blocks) >= 2 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            right = blocks.pop()
            left = blocks.pop()
            blocks.append([left[0] + right[0], left[1] + right[1], left[2], right[3]])
    output = [0.0] * len(values)
    for weighted_sum, weight, start, end in blocks:
        for index in range(int(start), int(end) + 1):
            output[index] = weighted_sum / weight
    return tuple(output)


def chrmlite_probability(
    *,
    h: int,
    k: float,
    u: int,
    p_model: float,
    p_environment: float,
    base_rate: float,
    intercept: float,
    beta_k: float,
    beta_u: float,
    beta_model: float,
    beta_environment: float,
    epsilon: float = 1e-12,
) -> float | None:
    if h not in {0, 1}:
        raise ValueError("h must be binary")
    if h == 0:
        return None
    if min(beta_k, beta_model, beta_environment) < 0:
        raise ValueError("V4.1 monotonic coefficients must be nonnegative")
    if not 0.0 <= k <= 1.0 or u not in {0, 1}:
        raise ValueError("Invalid knowledge features")

    def logit(value: float) -> float:
        clipped = min(1.0 - epsilon, max(epsilon, float(value)))
        return math.log(clipped / (1.0 - clipped))

    baseline = logit(base_rate)
    eta = (
        float(intercept)
        + beta_k * k
        + beta_u * u
        + beta_model * (logit(p_model) - baseline)
        + beta_environment * (logit(p_environment) - baseline)
    )
    return 1.0 / (1.0 + math.exp(-eta)) if eta >= 0 else math.exp(eta) / (1.0 + math.exp(eta))


def cdt_threshold(
    *,
    rho_lcb: float,
    failure_loss: float,
    evaluation_cost: float,
    false_positive_cost: float,
    tau_max: float,
) -> float:
    benefit = float(rho_lcb) * float(failure_loss)
    if benefit <= float(evaluation_cost):
        return 0.0
    denominator = benefit + float(false_positive_cost)
    if denominator <= 0:
        raise ValueError("CDT threshold denominator must be positive")
    return min((benefit - float(evaluation_cost)) / denominator, float(tau_max))


def cdt_should_trigger(*, h: int, p_pre: float | None, tau: float, delta: float, counter: int, interval: int) -> bool:
    if h == 0:
        return True
    if p_pre is None:
        raise ValueError("Feasible rows require p_pre")
    return bool(p_pre <= tau - delta or counter >= interval)


def false_positive_cost(samples: Sequence[tuple[bool, float]]) -> float:
    if not samples:
        raise ValueError("c_fp requires evaluated correct-step samples")
    return sum(float(delta_cost) if changed else 0.0 for changed, delta_cost in samples) / len(samples)


def post_revision_features(
    *,
    action_changed: bool,
    old_h: int,
    old_k: float,
    old_u: int,
    old_environment_probability: float,
    recomputed: tuple[int, float, int, float] | None,
    new_model_probability: float,
) -> tuple[int, float, int, float, float]:
    if action_changed:
        if recomputed is None:
            raise ValueError("Changed action requires recomputed K/E features")
        new_h, new_k, new_u, new_environment = recomputed
    else:
        new_h, new_k, new_u, new_environment = (
            old_h,
            old_k,
            old_u,
            old_environment_probability,
        )
    return new_h, new_k, new_u, float(new_model_probability), float(new_environment)


def update_evaluation_interval(
    *,
    current: int,
    action_changed: bool,
    revised_action_succeeded: bool,
    p_post: float,
    tau: float,
    delta: float,
    m_min: int,
    m_max: int,
) -> int:
    if action_changed and revised_action_succeeded:
        return max(m_min, current - 1)
    if not action_changed and p_post >= tau + delta:
        return min(m_max, current + 1)
    return current


def deterministic_task_folds(tasks: Sequence[str], fold_count: int) -> Mapping[str, int]:
    unique = sorted(set(str(task) for task in tasks))
    if fold_count < 2 or len(unique) < fold_count:
        raise ValueError("Not enough terminal tasks for cross-fitting")
    return {task: index % fold_count for index, task in enumerate(unique)}


def build_method_contracts(source_commit: str) -> tuple[
    CHRMLiteCDTLiteMethodContractV4_1,
    CHRMLiteFeatureSchemaV4_1,
    CHRMLiteLabelPolicyV4_1,
    CHRMLiteParameterProvenancePolicyV4_1,
    CHRMLiteStatisticalAnalysisPolicyV4_1,
]:
    feature = CHRMLiteFeatureSchemaV4_1().with_id()
    label = CHRMLiteLabelPolicyV4_1().with_id()
    provenance = CHRMLiteParameterProvenancePolicyV4_1().with_id()
    statistical = CHRMLiteStatisticalAnalysisPolicyV4_1().with_id()
    method = CHRMLiteCDTLiteMethodContractV4_1(
        source_commit=source_commit,
        feature_schema_id=feature.schema_id,
        label_policy_id=label.policy_id,
        parameter_provenance_policy_id=provenance.policy_id,
        statistical_analysis_policy_id=statistical.policy_id,
    ).with_id()
    return method, feature, label, provenance, statistical
