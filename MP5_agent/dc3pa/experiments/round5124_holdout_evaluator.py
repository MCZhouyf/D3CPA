"""Locked evaluator for Round 5.12.4; intentionally has no fitter import."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .round5124_holdout import FINAL_FEATURE_ORDER, sha256_file
from .round5124_holdout_features import HoldoutFusionFeatureRecord, load_holdout_features


EPSILON = 1e-12
LOWER_IS_BETTER = frozenset({"brier", "nll", "ece"})


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load(path: str | Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _probabilities(
    records: Sequence[HoldoutFusionFeatureRecord], candidate: Mapping[str, Any]
) -> np.ndarray:
    if tuple(candidate["feature_order"]) != FINAL_FEATURE_ORDER:
        raise ValueError("Locked candidate feature order changed")
    coefficients = candidate["coefficients"]
    return np.asarray(
        [
            0.0
            if not item.hard_feasible
            else _sigmoid(
                float(candidate["intercept"])
                + sum(
                    float(coefficients[name]) * float(item.features[name])
                    for name in FINAL_FEATURE_ORDER
                )
            )
            for item in records
        ],
        dtype=np.float64,
    )


def _validate_frozen_inputs(
    candidate: Mapping[str, Any], policy: Mapping[str, Any]
) -> None:
    if tuple(candidate.get("feature_order", ())) != FINAL_FEATURE_ORDER:
        raise ValueError("Locked candidate feature order changed")
    coefficients = candidate.get("coefficients", {})
    if set(coefficients) != set(FINAL_FEATURE_ORDER) or any(
        not math.isfinite(float(value)) or float(value) < 0
        for value in coefficients.values()
    ):
        raise ValueError("Locked candidate monotonic coefficients changed")
    expected = {
        "primary_bootstrap_unit": "task",
        "secondary_sensitivity_bootstrap_unit": "task_seed_run",
        "primary_controls_activation": True,
        "secondary_can_override_activation": False,
        "primary_metrics": ["brier", "nll"],
        "calibration_metrics": ["ece"],
        "noninferiority_margins": {"brier": 0.01, "ece": 0.02, "nll": 0.02},
        "minimum_effects": {"brier": 0.005, "ece": 0.0, "nll": 0.01},
        "minimum_primary_improvements": 1,
        "require_improvement_ci_upper_at_most_zero": True,
        "bootstrap_replicates": 2000,
        "bootstrap_seed": 5102026,
        "confidence_level": 0.95,
        "reliability_bins": 10,
        "post_holdout_tuning_forbidden": True,
    }
    for name, value in expected.items():
        if policy.get(name) != value:
            raise ValueError(f"Locked activation policy changed: {name}")


def _rank_auc(labels: np.ndarray, probabilities: np.ndarray) -> float | None:
    positives = int(labels.sum())
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    order = np.argsort(probabilities, kind="mergesort")
    ranks = np.empty(len(labels), dtype=np.float64)
    start = 0
    while start < len(labels):
        end = start + 1
        while end < len(labels) and probabilities[order[end]] == probabilities[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.0
        start = end
    return float(
        (ranks[labels == 1].sum() - positives * (positives + 1) / 2.0)
        / (positives * negatives)
    )


def _metrics(labels: np.ndarray, probabilities: np.ndarray, bins: int) -> dict[str, Any]:
    clipped = np.clip(probabilities, EPSILON, 1.0 - EPSILON)
    edges = np.linspace(0.0, 1.0, bins + 1)
    reliability = []
    ece = 0.0
    for index in range(bins):
        mask = (
            (probabilities >= edges[index]) & (probabilities <= edges[index + 1])
            if index == bins - 1
            else (probabilities >= edges[index]) & (probabilities < edges[index + 1])
        )
        count = int(mask.sum())
        mean_probability = float(probabilities[mask].mean()) if count else None
        empirical = float(labels[mask].mean()) if count else None
        if count:
            ece += count / len(labels) * abs(mean_probability - empirical)
        reliability.append(
            {
                "lower": float(edges[index]),
                "upper": float(edges[index + 1]),
                "count": count,
                "mean_probability": mean_probability,
                "empirical_success": empirical,
            }
        )
    positives = int(labels.sum())
    order = np.argsort(-probabilities, kind="mergesort")
    ordered = labels[order]
    auprc = (
        float(((np.cumsum(ordered) / np.arange(1, len(labels) + 1)) * ordered).sum() / positives)
        if positives
        else None
    )
    return {
        "count": len(labels),
        "positive_count": positives,
        "negative_count": len(labels) - positives,
        "brier": float(np.mean((probabilities - labels) ** 2)),
        "nll": float(-np.mean(labels * np.log(clipped) + (1 - labels) * np.log(1 - clipped))),
        "ece": float(ece),
        "auroc": _rank_auc(labels, probabilities),
        "auprc": auprc,
        "reliability_bins": reliability,
    }


def _oriented(metric: str, candidate: float, baseline: float) -> float:
    return candidate - baseline if metric in LOWER_IS_BETTER else baseline - candidate


def _bootstrap(
    records: Sequence[HoldoutFusionFeatureRecord],
    candidate: np.ndarray,
    baseline: np.ndarray,
    *,
    grouping: str,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    labels = np.asarray([item.label for item in records], dtype=np.float64)
    groups: dict[str, list[int]] = {}
    for index, item in enumerate(records):
        groups.setdefault(item.task if grouping == "task" else item.group_id, []).append(index)
    if len(groups) < 2:
        raise ValueError("Grouped holdout bootstrap requires at least two groups")
    rng = np.random.default_rng(int(policy["bootstrap_seed"]))
    names = sorted(groups)
    metrics = ("brier", "nll", "ece", "auroc", "auprc")
    values: dict[str, list[float]] = {name: [] for name in metrics}
    bins = int(policy["reliability_bins"])
    for _ in range(int(policy["bootstrap_replicates"])):
        sampled = rng.choice(names, size=len(names), replace=True)
        indices = [index for name in sampled for index in groups[str(name)]]
        subset_labels = labels[indices]
        if len(np.unique(subset_labels)) < 2:
            continue
        candidate_metrics = _metrics(subset_labels, candidate[indices], bins)
        baseline_metrics = _metrics(subset_labels, baseline[indices], bins)
        for metric in metrics:
            if candidate_metrics[metric] is not None and baseline_metrics[metric] is not None:
                values[metric].append(
                    _oriented(metric, candidate_metrics[metric], baseline_metrics[metric])
                )
    alpha = 1.0 - float(policy["confidence_level"])
    return {
        "grouping": grouping,
        "group_count": len(groups),
        "replicates_requested": int(policy["bootstrap_replicates"]),
        "metrics": {
            metric: {
                "valid_replicates": len(items),
                "mean_oriented_delta": float(np.mean(items)) if items else None,
                "ci_lower": float(np.quantile(items, alpha / 2)) if items else None,
                "ci_upper": float(np.quantile(items, 1 - alpha / 2)) if items else None,
                "negative_means_candidate_better": True,
            }
            for metric, items in values.items()
        },
    }


def evaluate_locked_holdout(
    *,
    feature_path: str | Path,
    candidate_path: str | Path,
    activation_policy_path: str | Path,
    runtime_release_path: str | Path,
    execution_manifest_path: str | Path,
    ledger_path: str | Path,
    campaign_summary_path: str | Path,
    source_commit: str,
) -> Mapping[str, Any]:
    candidate = _load(candidate_path)
    policy = _load(activation_policy_path)
    runtime = _load(runtime_release_path)
    manifest = _load(execution_manifest_path)
    ledger = _load(ledger_path)
    campaign = _load(campaign_summary_path)
    _validate_frozen_inputs(candidate, policy)
    if ledger.get("state") != "consumed":
        raise ValueError("Holdout campaign has not been consumed")
    if ledger.get("campaign_summary_sha256") != sha256_file(campaign_summary_path):
        raise ValueError("Holdout campaign summary changed after consumption")
    if manifest["runtime_release_id"] != runtime["release_id"]:
        raise ValueError("Holdout runtime/manifest mismatch")
    bindings = (
        (sha256_file(candidate_path), runtime["candidate_artifact_sha256"]),
        (sha256_file(activation_policy_path), runtime["activation_policy_sha256"]),
        (candidate["artifact_id"], runtime["candidate_artifact_id"]),
        (policy["policy_id"], runtime["activation_policy_id"]),
        (source_commit, runtime["source_commit"]),
    )
    if any(actual != expected for actual, expected in bindings):
        raise ValueError("Locked holdout candidate/policy/runtime binding changed")
    records = load_holdout_features(feature_path)
    labels = np.asarray([item.label for item in records], dtype=np.float64)
    if len(np.unique(labels)) != 2:
        raise ValueError("Locked holdout lacks positive/negative label support")
    candidate_probability = _probabilities(records, candidate)
    legacy_probability = np.asarray([item.legacy_probability for item in records])
    equal_probability = np.asarray([item.equal_weight_probability for item in records])
    bins = int(policy["reliability_bins"])
    primary_legacy = _bootstrap(
        records, candidate_probability, legacy_probability, grouping="task", policy=policy
    )
    primary_equal = _bootstrap(
        records, candidate_probability, equal_probability, grouping="task", policy=policy
    )
    secondary_legacy = _bootstrap(
        records, candidate_probability, legacy_probability, grouping="task_seed_run", policy=policy
    )
    secondary_equal = _bootstrap(
        records, candidate_probability, equal_probability, grouping="task_seed_run", policy=policy
    )
    candidate_metrics = _metrics(labels, candidate_probability, bins)
    legacy_metrics = _metrics(labels, legacy_probability, bins)
    equal_metrics = _metrics(labels, equal_probability, bins)
    reasons = []
    improvements = 0
    comparisons = {}
    primary_metrics = tuple(policy["primary_metrics"])
    required_metrics = primary_metrics + tuple(policy["calibration_metrics"])
    for metric in required_metrics:
        comparison = primary_legacy["metrics"][metric]
        upper = comparison["ci_upper"]
        if upper is None or comparison["valid_replicates"] < max(100, int(policy["bootstrap_replicates"] * 0.5)):
            reasons.append(f"{metric}: too few valid task-grouped replicates")
            continue
        if upper > float(policy["noninferiority_margins"][metric]):
            reasons.append(f"{metric}: noninferiority failed")
        point_delta = _oriented(
            metric, candidate_metrics[metric], legacy_metrics[metric]
        )
        meaningful = (
            metric in primary_metrics
            and point_delta <= -float(policy["minimum_effects"][metric])
            and (
                not policy["require_improvement_ci_upper_at_most_zero"]
                or upper <= 0.0
            )
        )
        comparisons[metric] = {
            "candidate": candidate_metrics[metric],
            "legacy": legacy_metrics[metric],
            "equal_weight": equal_metrics[metric],
            "oriented_delta": point_delta,
            "ci_lower": comparison["ci_lower"],
            "ci_upper": upper,
            "noninferiority_margin": float(policy["noninferiority_margins"][metric]),
            "noninferior": upper <= float(policy["noninferiority_margins"][metric]),
            "meaningful_primary_improvement": meaningful,
            "negative_means_candidate_better": True,
        }
        if meaningful:
            improvements += 1
    if improvements < int(policy["minimum_primary_improvements"]):
        reasons.append("insufficient meaningful primary improvements")
    report = {
        "schema_version": 1,
        "source_commit": source_commit,
        "candidate_artifact_id": candidate["artifact_id"],
        "activation_policy_id": policy["policy_id"],
        "final_runtime_release_id": runtime["release_id"],
        "execution_manifest_id": manifest["manifest_id"],
        "single_use_ledger_id": ledger["ledger_id"],
        "holdout_feature_sha256": sha256_file(feature_path),
        "holdout_assignment_count": int(campaign["assignment_count"]),
        "holdout_decision_count": len(records),
        "technical_retry_count": int(campaign["technical_retry_count"]),
        "candidate_metrics": candidate_metrics,
        "legacy_metrics": legacy_metrics,
        "equal_weight_metrics": equal_metrics,
        "activation_comparisons": comparisons,
        "primary_task_grouped": {
            "candidate_vs_legacy": primary_legacy,
            "candidate_vs_equal_weight": primary_equal,
        },
        "secondary_task_seed_run": {
            "candidate_vs_legacy": secondary_legacy,
            "candidate_vs_equal_weight": secondary_equal,
            "controls_activation": False,
        },
        "eligible": not reasons,
        "activation_reasons": reasons,
        "post_holdout_tuning_performed": False,
        "final_evaluation_opened": False,
    }
    report["report_id"] = _sha(report)
    return report
