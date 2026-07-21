"""Frozen policies and deterministic monotonic Fusion fit for Round 5.12.4."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .round5124_fusion_data import (
    FINAL_FEATURE_ORDER,
    DirectedFusionFeatureRecord,
    load_directed_jsonl,
    sha256_file,
)


SCHEMA_VERSION = 1
EPSILON = 1e-12
LOWER_IS_BETTER = frozenset({"brier", "nll", "ece"})
HIGHER_IS_BETTER = frozenset({"auroc", "auprc"})


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _load_json(path: str | Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _sigmoid(values: np.ndarray | float) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    positive = array >= 0
    output = np.empty_like(array)
    output[positive] = 1.0 / (1.0 + np.exp(-array[positive]))
    exp_values = np.exp(array[~positive])
    output[~positive] = exp_values / (1.0 + exp_values)
    return output


def _nll(labels: np.ndarray, probabilities: np.ndarray) -> float:
    clipped = np.clip(probabilities, EPSILON, 1.0 - EPSILON)
    return float(
        -np.mean(
            labels * np.log(clipped)
            + (1.0 - labels) * np.log(1.0 - clipped)
        )
    )


def _ece(labels: np.ndarray, probabilities: np.ndarray, bins: int) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    result = 0.0
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        mask = (
            (probabilities >= lower) & (probabilities <= upper)
            if index == bins - 1
            else (probabilities >= lower) & (probabilities < upper)
        )
        count = int(mask.sum())
        if count:
            result += count / len(labels) * abs(
                float(probabilities[mask].mean()) - float(labels[mask].mean())
            )
    return float(result)


def _roc_auc(labels: np.ndarray, probabilities: np.ndarray) -> float | None:
    positives = int((labels == 1).sum())
    negatives = int((labels == 0).sum())
    if positives == 0 or negatives == 0:
        return None
    order = np.argsort(probabilities, kind="mergesort")
    ranks = np.empty(len(probabilities), dtype=np.float64)
    start = 0
    while start < len(probabilities):
        end = start + 1
        while (
            end < len(probabilities)
            and probabilities[order[end]] == probabilities[order[start]]
        ):
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.0
        start = end
    rank_sum = float(ranks[labels == 1].sum())
    return (rank_sum - positives * (positives + 1) / 2.0) / (
        positives * negatives
    )


def _average_precision(
    labels: np.ndarray, probabilities: np.ndarray
) -> float | None:
    positives = int((labels == 1).sum())
    if positives == 0:
        return None
    order = np.argsort(-probabilities, kind="mergesort")
    ordered = labels[order]
    true_positives = np.cumsum(ordered)
    precision = true_positives / np.arange(1, len(ordered) + 1)
    return float((precision * ordered).sum() / positives)


def _reliability_bins(
    labels: np.ndarray,
    probabilities: np.ndarray,
    bins: int,
) -> list[dict[str, Any]]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    output: list[dict[str, Any]] = []
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        mask = (
            (probabilities >= lower) & (probabilities <= upper)
            if index == bins - 1
            else (probabilities >= lower) & (probabilities < upper)
        )
        output.append(
            {
                "lower": float(lower),
                "upper": float(upper),
                "count": int(mask.sum()),
                "mean_probability": (
                    float(probabilities[mask].mean()) if mask.any() else None
                ),
                "empirical_success": (
                    float(labels[mask].mean()) if mask.any() else None
                ),
            }
        )
    return output


def metric_report(
    labels: np.ndarray,
    probabilities: np.ndarray,
    *,
    bins: int = 10,
) -> dict[str, Any]:
    return {
        "count": int(len(labels)),
        "positive_count": int(labels.sum()),
        "negative_count": int(len(labels) - labels.sum()),
        "brier": float(np.mean((probabilities - labels) ** 2)),
        "nll": _nll(labels, probabilities),
        "ece": _ece(labels, probabilities, bins),
        "auroc": _roc_auc(labels, probabilities),
        "auprc": _average_precision(labels, probabilities),
        "reliability_bins": _reliability_bins(labels, probabilities, bins),
    }


@dataclass(frozen=True)
class Round5124FitPolicy:
    source_commit: str
    pre_fusion_qualification_id: str
    feature_direction_policy_id: str
    l2_provenance_audit_id: str
    l2_candidate_values: tuple[float, ...]
    learning_rate: float
    maximum_epochs: int
    patience: int
    minimum_delta: float
    initialization: str
    coefficient_projection: str
    intercept_regularized: bool
    feature_scaling: str
    sample_weighting: str
    train_objective: str
    tune_selection_objective: str
    hard_infeasible_probability: float
    task_runtime_features_forbidden: bool
    holdout_path_permitted: bool
    final_evaluation_path_permitted: bool
    post_tune_redesign_permitted: bool
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        required = (
            self.source_commit,
            self.pre_fusion_qualification_id,
            self.feature_direction_policy_id,
            self.l2_provenance_audit_id,
        )
        if any(not value for value in required):
            raise ValueError("Fit policy binding is incomplete")
        if self.l2_candidate_values != (1e-3,):
            raise ValueError("Round 5.12.4 L2 policy must be the fixed 1e-3 value")
        if (
            self.learning_rate,
            self.maximum_epochs,
            self.patience,
            self.minimum_delta,
        ) != (0.05, 5000, 200, 1e-8):
            raise ValueError("Historical deterministic optimizer settings changed")
        if self.initialization != "zero_coefficients_prevalence_intercept":
            raise ValueError("Optimizer initialization changed")
        if self.coefficient_projection != "nonnegative_after_each_update":
            raise ValueError("Coefficient projection changed")
        if self.intercept_regularized:
            raise ValueError("Intercept cannot be regularized")
        if self.feature_scaling != "none_native_0_1":
            raise ValueError("Feature scaling changed")
        if self.sample_weighting != "equal_per_decision_record":
            raise ValueError("Sample weighting changed")
        if self.train_objective != "mean_nll_plus_half_l2_sum_beta_squared":
            raise ValueError("Train objective changed")
        if self.tune_selection_objective != "minimum_tune_nll_checkpoint":
            raise ValueError("Tune selection objective changed")
        if self.hard_infeasible_probability != 0.0:
            raise ValueError("Hard feasibility gate changed")
        if not self.task_runtime_features_forbidden:
            raise ValueError("Forbidden predictive features were allowed")
        if any(
            (
                self.holdout_path_permitted,
                self.final_evaluation_path_permitted,
                self.post_tune_redesign_permitted,
            )
        ):
            raise ValueError("Fit policy opened a protected operation")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("Fit policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["l2_candidate_values"] = list(self.l2_candidate_values)
        return payload

    def compute_policy_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "Round5124FitPolicy":
        return replace(self, policy_id=self.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.policy_id else self.with_id()
        return {**item.payload_without_id(), "policy_id": item.policy_id}


@dataclass(frozen=True)
class Round5124ActivationPolicy:
    source_commit: str
    bootstrap_policy_id: str
    historical_activation_policy_id: str
    primary_bootstrap_unit: str
    secondary_sensitivity_bootstrap_unit: str
    primary_controls_activation: bool
    secondary_can_override_activation: bool
    primary_metrics: tuple[str, ...]
    calibration_metrics: tuple[str, ...]
    noninferiority_margins: Mapping[str, float]
    minimum_effects: Mapping[str, float]
    minimum_primary_improvements: int
    require_improvement_ci_upper_at_most_zero: bool
    bootstrap_replicates: int
    bootstrap_seed: int
    confidence_level: float
    reliability_bins: int
    post_holdout_tuning_forbidden: bool
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        if not all(
            (
                self.source_commit,
                self.bootstrap_policy_id,
                self.historical_activation_policy_id,
            )
        ):
            raise ValueError("Activation policy binding is incomplete")
        if self.primary_bootstrap_unit != "task":
            raise ValueError("Primary activation bootstrap must be task-grouped")
        if self.secondary_sensitivity_bootstrap_unit != "task_seed_run":
            raise ValueError("Sensitivity bootstrap must be task-seed/run grouped")
        if not self.primary_controls_activation or self.secondary_can_override_activation:
            raise ValueError("Sensitivity result cannot control activation")
        if self.primary_metrics != ("brier", "nll"):
            raise ValueError("Primary activation metrics changed")
        if self.calibration_metrics != ("ece",):
            raise ValueError("Calibration activation metrics changed")
        if dict(self.noninferiority_margins) != {
            "brier": 0.01,
            "ece": 0.02,
            "nll": 0.02,
        }:
            raise ValueError("Noninferiority margins changed")
        if dict(self.minimum_effects) != {
            "brier": 0.005,
            "ece": 0.0,
            "nll": 0.01,
        }:
            raise ValueError("Minimum effects changed")
        if (
            self.minimum_primary_improvements,
            self.bootstrap_replicates,
            self.bootstrap_seed,
            self.reliability_bins,
        ) != (1, 2000, 5102026, 10):
            raise ValueError("Activation bootstrap settings changed")
        if not math.isclose(self.confidence_level, 0.95):
            raise ValueError("Activation confidence level changed")
        if not self.require_improvement_ci_upper_at_most_zero:
            raise ValueError("Activation CI rule changed")
        if not self.post_holdout_tuning_forbidden:
            raise ValueError("Post-holdout tuning must be forbidden")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("Activation policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["primary_metrics"] = list(self.primary_metrics)
        payload["calibration_metrics"] = list(self.calibration_metrics)
        payload["noninferiority_margins"] = dict(
            sorted(self.noninferiority_margins.items())
        )
        payload["minimum_effects"] = dict(sorted(self.minimum_effects.items()))
        return payload

    def compute_policy_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "Round5124ActivationPolicy":
        return replace(self, policy_id=self.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.policy_id else self.with_id()
        return {**item.payload_without_id(), "policy_id": item.policy_id}


@dataclass(frozen=True)
class MonotonicFusionCandidateArtifact:
    source_commit: str
    fit_policy_id: str
    activation_policy_id: str
    pre_fusion_qualification_id: str
    feature_direction_policy_id: str
    train_dataset_sha256: str
    tune_dataset_sha256: str
    feature_order: tuple[str, ...]
    hard_infeasible_probability: float
    intercept: float
    coefficients: Mapping[str, float]
    selected_l2: float
    selected_checkpoint: int
    train_metrics: Mapping[str, Any]
    tune_metrics: Mapping[str, Any]
    holdout_not_opened: bool
    final_evaluation_not_opened: bool
    schema_version: int = SCHEMA_VERSION
    artifact_id: str = ""

    def __post_init__(self) -> None:
        if self.feature_order != FINAL_FEATURE_ORDER:
            raise ValueError("Candidate feature order changed")
        if set(self.coefficients) != set(FINAL_FEATURE_ORDER):
            raise ValueError("Candidate coefficients are incomplete")
        if any(float(value) < 0 or not math.isfinite(float(value)) for value in self.coefficients.values()):
            raise ValueError("Candidate coefficients must be finite and nonnegative")
        if not math.isfinite(float(self.intercept)):
            raise ValueError("Candidate intercept is not finite")
        if self.selected_l2 != 1e-3 or self.selected_checkpoint <= 0:
            raise ValueError("Candidate selection changed")
        if self.hard_infeasible_probability != 0.0:
            raise ValueError("Candidate hard gate changed")
        if not self.holdout_not_opened or not self.final_evaluation_not_opened:
            raise ValueError("Candidate opened protected data")
        expected = self.compute_artifact_id()
        if self.artifact_id and self.artifact_id != expected:
            raise ValueError("Candidate artifact hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("artifact_id", None)
        payload["feature_order"] = list(self.feature_order)
        payload["coefficients"] = dict(sorted(self.coefficients.items()))
        payload["train_metrics"] = dict(self.train_metrics)
        payload["tune_metrics"] = dict(self.tune_metrics)
        return payload

    def compute_artifact_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "MonotonicFusionCandidateArtifact":
        return replace(self, artifact_id=self.compute_artifact_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.artifact_id else self.with_id()
        return {**item.payload_without_id(), "artifact_id": item.artifact_id}


def freeze_fit_policies(
    *,
    source_commit: str,
    qualification_path: str | Path,
    feature_direction_path: str | Path,
    l2_provenance_path: str | Path,
    bootstrap_policy_path: str | Path,
) -> tuple[Round5124FitPolicy, Round5124ActivationPolicy]:
    qualification = _load_json(qualification_path)
    direction = _load_json(feature_direction_path)
    l2 = _load_json(l2_provenance_path)
    bootstrap = _load_json(bootstrap_policy_path)
    if not qualification.get("eligible"):
        raise ValueError("Pre-Fusion qualification is ineligible")
    if l2.get("case") != 2 or l2.get("candidate_values") != [0.001]:
        raise ValueError("L2 provenance does not permit the fixed fit")
    fit = Round5124FitPolicy(
        source_commit=source_commit,
        pre_fusion_qualification_id=str(qualification["report_id"]),
        feature_direction_policy_id=str(direction["policy_id"]),
        l2_provenance_audit_id=str(l2["audit_id"]),
        l2_candidate_values=(1e-3,),
        learning_rate=0.05,
        maximum_epochs=5000,
        patience=200,
        minimum_delta=1e-8,
        initialization="zero_coefficients_prevalence_intercept",
        coefficient_projection="nonnegative_after_each_update",
        intercept_regularized=False,
        feature_scaling="none_native_0_1",
        sample_weighting="equal_per_decision_record",
        train_objective="mean_nll_plus_half_l2_sum_beta_squared",
        tune_selection_objective="minimum_tune_nll_checkpoint",
        hard_infeasible_probability=0.0,
        task_runtime_features_forbidden=True,
        holdout_path_permitted=False,
        final_evaluation_path_permitted=False,
        post_tune_redesign_permitted=False,
    ).with_id()
    activation = Round5124ActivationPolicy(
        source_commit=source_commit,
        bootstrap_policy_id=str(bootstrap["policy_id"]),
        historical_activation_policy_id=str(
            bootstrap["historical_activation_policy_id"]
        ),
        primary_bootstrap_unit="task",
        secondary_sensitivity_bootstrap_unit="task_seed_run",
        primary_controls_activation=True,
        secondary_can_override_activation=False,
        primary_metrics=("brier", "nll"),
        calibration_metrics=("ece",),
        noninferiority_margins=dict(bootstrap["noninferiority_margins"]),
        minimum_effects=dict(bootstrap["minimum_effects"]),
        minimum_primary_improvements=int(bootstrap["minimum_primary_improvements"]),
        require_improvement_ci_upper_at_most_zero=bool(
            bootstrap["require_improvement_ci_upper_at_most_zero"]
        ),
        bootstrap_replicates=int(bootstrap["bootstrap_replicates"]),
        bootstrap_seed=int(bootstrap["bootstrap_seed"]),
        confidence_level=float(bootstrap["confidence_level"]),
        reliability_bins=int(bootstrap["reliability_bins"]),
        post_holdout_tuning_forbidden=True,
    ).with_id()
    return fit, activation


def _matrix(
    records: Sequence[DirectedFusionFeatureRecord],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    features = np.asarray(
        [[float(item.features[name]) for name in FINAL_FEATURE_ORDER] for item in records],
        dtype=np.float64,
    )
    labels = np.asarray([item.label for item in records], dtype=np.float64)
    feasible = np.asarray([item.hard_feasible for item in records], dtype=bool)
    return features, labels, feasible


def _predict(
    features: np.ndarray,
    feasible: np.ndarray,
    intercept: float,
    coefficients: np.ndarray,
) -> np.ndarray:
    probabilities = _sigmoid(intercept + features @ coefficients)
    return np.where(feasible, probabilities, 0.0)


def fit_candidate(
    *,
    source_commit: str,
    train_records: Sequence[DirectedFusionFeatureRecord],
    tune_records: Sequence[DirectedFusionFeatureRecord],
    fit_policy: Round5124FitPolicy,
    activation_policy: Round5124ActivationPolicy,
    train_dataset_sha256: str,
    tune_dataset_sha256: str,
) -> MonotonicFusionCandidateArtifact:
    x_train, y_train, feasible_train = _matrix(train_records)
    x_tune, y_tune, feasible_tune = _matrix(tune_records)
    x_fit = x_train[feasible_train]
    y_fit = y_train[feasible_train]
    if set(np.unique(y_fit)) != {0.0, 1.0}:
        raise ValueError("Feasible training rows must contain both labels")
    coefficients = np.zeros(len(FINAL_FEATURE_ORDER), dtype=np.float64)
    prevalence = float(np.clip(y_fit.mean(), 1e-6, 1.0 - 1e-6))
    intercept = math.log(prevalence / (1.0 - prevalence))
    best = (float("inf"), intercept, coefficients.copy(), 0)
    stale = 0
    for epoch in range(1, fit_policy.maximum_epochs + 1):
        probability = _sigmoid(intercept + x_fit @ coefficients)
        residual = probability - y_fit
        grad_intercept = float(residual.mean())
        grad_coefficients = (
            (x_fit.T @ residual) / len(y_fit)
            + fit_policy.l2_candidate_values[0] * coefficients
        )
        intercept -= fit_policy.learning_rate * grad_intercept
        coefficients -= fit_policy.learning_rate * grad_coefficients
        coefficients = np.maximum(coefficients, 0.0)
        tune_probability = _predict(
            x_tune, feasible_tune, intercept, coefficients
        )
        tune_loss = _nll(y_tune, tune_probability)
        if tune_loss < best[0] - fit_policy.minimum_delta:
            best = (tune_loss, intercept, coefficients.copy(), epoch)
            stale = 0
        else:
            stale += 1
            if stale >= fit_policy.patience:
                break
    _, intercept, coefficients, checkpoint = best
    if checkpoint <= 0:
        raise ValueError("No fit checkpoint was selected")
    train_probability = _predict(
        x_train, feasible_train, intercept, coefficients
    )
    tune_probability = _predict(x_tune, feasible_tune, intercept, coefficients)
    return MonotonicFusionCandidateArtifact(
        source_commit=source_commit,
        fit_policy_id=fit_policy.policy_id,
        activation_policy_id=activation_policy.policy_id,
        pre_fusion_qualification_id=fit_policy.pre_fusion_qualification_id,
        feature_direction_policy_id=fit_policy.feature_direction_policy_id,
        train_dataset_sha256=train_dataset_sha256,
        tune_dataset_sha256=tune_dataset_sha256,
        feature_order=FINAL_FEATURE_ORDER,
        hard_infeasible_probability=0.0,
        intercept=float(intercept),
        coefficients={
            name: float(value)
            for name, value in zip(FINAL_FEATURE_ORDER, coefficients)
        },
        selected_l2=fit_policy.l2_candidate_values[0],
        selected_checkpoint=checkpoint,
        train_metrics=metric_report(
            y_train, train_probability, bins=activation_policy.reliability_bins
        ),
        tune_metrics=metric_report(
            y_tune, tune_probability, bins=activation_policy.reliability_bins
        ),
        holdout_not_opened=True,
        final_evaluation_not_opened=True,
    ).with_id()


def candidate_probabilities(
    records: Sequence[DirectedFusionFeatureRecord],
    artifact: MonotonicFusionCandidateArtifact,
) -> np.ndarray:
    features, _, feasible = _matrix(records)
    coefficients = np.asarray(
        [artifact.coefficients[name] for name in FINAL_FEATURE_ORDER],
        dtype=np.float64,
    )
    return _predict(features, feasible, artifact.intercept, coefficients)


def _metric_value(
    name: str,
    labels: np.ndarray,
    probability: np.ndarray,
    bins: int,
) -> float | None:
    return metric_report(labels, probability, bins=bins).get(name)


def _oriented_delta(name: str, candidate: float, baseline: float) -> float:
    return candidate - baseline if name in LOWER_IS_BETTER else baseline - candidate


def _bootstrap_comparison(
    *,
    records: Sequence[DirectedFusionFeatureRecord],
    candidate: np.ndarray,
    baseline: np.ndarray,
    grouping: str,
    policy: Round5124ActivationPolicy,
) -> dict[str, Any]:
    labels = np.asarray([item.label for item in records], dtype=np.float64)
    groups: dict[str, list[int]] = {}
    for index, item in enumerate(records):
        key = item.task if grouping == "task" else item.group_id
        groups.setdefault(key, []).append(index)
    if len(groups) < 2:
        raise ValueError("Grouped bootstrap requires at least two groups")
    rng = np.random.default_rng(policy.bootstrap_seed)
    names = sorted(groups)
    metrics = ("brier", "nll", "ece", "auroc", "auprc")
    deltas: dict[str, list[float]] = {name: [] for name in metrics}
    for _ in range(policy.bootstrap_replicates):
        sampled = rng.choice(names, size=len(names), replace=True)
        indices = [index for key in sampled for index in groups[str(key)]]
        subset_labels = labels[indices]
        if len(np.unique(subset_labels)) < 2:
            continue
        for metric in metrics:
            candidate_value = _metric_value(
                metric,
                subset_labels,
                candidate[indices],
                policy.reliability_bins,
            )
            baseline_value = _metric_value(
                metric,
                subset_labels,
                baseline[indices],
                policy.reliability_bins,
            )
            if candidate_value is not None and baseline_value is not None:
                deltas[metric].append(
                    _oriented_delta(metric, candidate_value, baseline_value)
                )
    alpha = 1.0 - policy.confidence_level
    output = {}
    for metric, values in deltas.items():
        if not values:
            output[metric] = {"valid_replicates": 0, "ci": None}
            continue
        array = np.asarray(values, dtype=np.float64)
        output[metric] = {
            "valid_replicates": len(values),
            "mean_oriented_delta": float(array.mean()),
            "ci_lower": float(np.quantile(array, alpha / 2.0)),
            "ci_upper": float(np.quantile(array, 1.0 - alpha / 2.0)),
            "negative_means_candidate_better": True,
        }
    return {
        "grouping": grouping,
        "group_count": len(groups),
        "replicates_requested": policy.bootstrap_replicates,
        "metrics": output,
    }


def build_tune_selection_report(
    *,
    source_commit: str,
    records: Sequence[DirectedFusionFeatureRecord],
    artifact: MonotonicFusionCandidateArtifact,
    activation_policy: Round5124ActivationPolicy,
) -> dict[str, Any]:
    labels = np.asarray([item.label for item in records], dtype=np.float64)
    candidate = candidate_probabilities(records, artifact)
    legacy = np.asarray([item.legacy_probability for item in records], dtype=np.float64)
    equal = np.asarray(
        [item.equal_weight_probability for item in records], dtype=np.float64
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "source_commit": source_commit,
        "candidate_artifact_id": artifact.artifact_id,
        "activation_policy_id": activation_policy.policy_id,
        "candidate_metrics": metric_report(
            labels, candidate, bins=activation_policy.reliability_bins
        ),
        "legacy_metrics": metric_report(
            labels, legacy, bins=activation_policy.reliability_bins
        ),
        "equal_weight_metrics": metric_report(
            labels, equal, bins=activation_policy.reliability_bins
        ),
        "primary_task_grouped": {
            "candidate_vs_legacy": _bootstrap_comparison(
                records=records,
                candidate=candidate,
                baseline=legacy,
                grouping="task",
                policy=activation_policy,
            ),
            "candidate_vs_equal_weight": _bootstrap_comparison(
                records=records,
                candidate=candidate,
                baseline=equal,
                grouping="task",
                policy=activation_policy,
            ),
        },
        "secondary_task_seed_run": {
            "candidate_vs_legacy": _bootstrap_comparison(
                records=records,
                candidate=candidate,
                baseline=legacy,
                grouping="group_id",
                policy=activation_policy,
            ),
            "candidate_vs_equal_weight": _bootstrap_comparison(
                records=records,
                candidate=candidate,
                baseline=equal,
                grouping="group_id",
                policy=activation_policy,
            ),
        },
        "selection": {
            "l2_selected_from_grid": False,
            "fixed_l2": artifact.selected_l2,
            "checkpoint_selected_on_tune_nll": artifact.selected_checkpoint,
            "activation_decision_deferred_to_single_use_holdout": True,
        },
        "holdout_not_opened": True,
        "final_evaluation_not_opened": True,
    }
    report["report_id"] = _sha(report)
    return report


def build_fit_ledger(
    *,
    source_commit: str,
    train_path: str | Path,
    tune_path: str | Path,
    fit_policy: Round5124FitPolicy,
    activation_policy: Round5124ActivationPolicy,
    artifact: MonotonicFusionCandidateArtifact,
    tune_report: Mapping[str, Any],
) -> dict[str, Any]:
    ledger = {
        "schema_version": SCHEMA_VERSION,
        "source_commit": source_commit,
        "train_dataset_sha256": sha256_file(train_path),
        "tune_dataset_sha256": sha256_file(tune_path),
        "fit_policy_id": fit_policy.policy_id,
        "activation_policy_id": activation_policy.policy_id,
        "candidate_artifact_id": artifact.artifact_id,
        "tune_selection_report_id": tune_report["report_id"],
        "l2_candidate_values": list(fit_policy.l2_candidate_values),
        "selected_l2": artifact.selected_l2,
        "selected_checkpoint": artifact.selected_checkpoint,
        "holdout_paths_present_in_fit_command": False,
        "holdout_opened": False,
        "final_evaluation_opened": False,
        "manual_coefficient_editing": False,
    }
    ledger["ledger_id"] = _sha(ledger)
    return ledger


def write_json_immutable(path: str | Path, value: Mapping[str, Any]) -> None:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
