"""One-shot grouped holdout evaluation for monotonic fusion activation."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .activation_policy import ActivationPolicy
from .fusion_artifact import FusionArtifact
from .fusion_dataset import FusionExample, dataset_sha256
from .fusion_features import FUSION_FEATURE_NAMES


HOLDOUT_REPORT_SCHEMA_VERSION = 1
_LOWER_IS_BETTER = frozenset({"brier", "nll", "ece"})
_HIGHER_IS_BETTER = frozenset({"auroc", "average_precision"})
_EPS = 1e-12


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sigmoid(logits: np.ndarray | float) -> np.ndarray:
    values = np.asarray(logits, dtype=np.float64)
    positive = values >= 0
    output = np.empty_like(values)
    output[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_values = np.exp(values[~positive])
    output[~positive] = exp_values / (1.0 + exp_values)
    return output


def _brier_score(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _binary_nll(y: np.ndarray, p: np.ndarray) -> float:
    clipped = np.clip(p, _EPS, 1.0 - _EPS)
    return float(-np.mean(y * np.log(clipped) + (1.0 - y) * np.log(1.0 - clipped)))


def _ece_score(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(y)
    value = 0.0
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        mask = (p >= lower) & (p <= upper if index == bins - 1 else p < upper)
        count = int(mask.sum())
        if count:
            value += (count / total) * abs(float(p[mask].mean()) - float(y[mask].mean()))
    return float(value)


def _reliability_bins(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict[str, Any]]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows: list[dict[str, Any]] = []
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        mask = (p >= lower) & (p <= upper if index == bins - 1 else p < upper)
        rows.append(
            {
                "lower": float(lower),
                "upper": float(upper),
                "count": int(mask.sum()),
                "mean_probability": float(p[mask].mean()) if mask.any() else None,
                "empirical_success": float(y[mask].mean()) if mask.any() else None,
            }
        )
    return rows


def _roc_auc(y: np.ndarray, p: np.ndarray) -> Optional[float]:
    positives = int((y == 1).sum())
    negatives = int((y == 0).sum())
    if positives == 0 or negatives == 0:
        return None
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), dtype=np.float64)
    start = 0
    while start < len(p):
        end = start + 1
        while end < len(p) and p[order[end]] == p[order[start]]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        ranks[order[start:end]] = average_rank
        start = end
    rank_sum = ranks[y == 1].sum()
    return float((rank_sum - positives * (positives + 1) / 2) / (positives * negatives))


def _average_precision(y: np.ndarray, p: np.ndarray) -> Optional[float]:
    positives = int((y == 1).sum())
    if positives == 0:
        return None
    order = np.argsort(-p, kind="mergesort")
    sorted_y = y[order]
    cumulative = np.cumsum(sorted_y)
    precision = cumulative / np.arange(1, len(y) + 1)
    return float((precision * sorted_y).sum() / positives)


def _metric_report(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict[str, Any]:
    return {
        "count": int(len(y)),
        "positive_rate": float(y.mean()),
        "brier": _brier_score(y, p),
        "nll": _binary_nll(y, p),
        "ece": _ece_score(y, p, bins=bins),
        "auroc": _roc_auc(y, p),
        "average_precision": _average_precision(y, p),
        "reliability_bins": _reliability_bins(y, p, bins=bins),
    }


def _candidate_probability(
    example: FusionExample,
    artifact: FusionArtifact,
) -> float:
    if example.hard_conflict:
        return 0.0
    logit = float(artifact.intercept) + sum(
        float(artifact.coefficients[name]) * float(example.features[name])
        for name in FUSION_FEATURE_NAMES
    )
    return float(_sigmoid(logit))


def _equal_weight_probability(example: FusionExample) -> float:
    if example.hard_conflict:
        return 0.0
    return float(
        sum(float(example.features[name]) for name in FUSION_FEATURE_NAMES)
        / len(FUSION_FEATURE_NAMES)
    )


def _metric_value(
    metric: str,
    y: np.ndarray,
    p: np.ndarray,
    *,
    ece_bins: int,
) -> Optional[float]:
    report = _metric_report(y, p, bins=ece_bins)
    value = report.get(metric)
    return None if value is None else float(value)


def _oriented_delta(metric: str, candidate: float, legacy: float) -> float:
    """Return delta where negative always favours the candidate."""

    if metric in _LOWER_IS_BETTER:
        return float(candidate - legacy)
    if metric in _HIGHER_IS_BETTER:
        return float(legacy - candidate)
    raise ValueError(f"Unknown metric orientation: {metric}")


def _percentile_interval(values: Sequence[float], confidence_level: float) -> tuple[float, float]:
    if not values:
        raise ValueError("Cannot compute interval from no values")
    alpha = 1.0 - confidence_level
    array = np.asarray(values, dtype=np.float64)
    return (
        float(np.quantile(array, alpha / 2.0)),
        float(np.quantile(array, 1.0 - alpha / 2.0)),
    )


def _group_key(example: FusionExample, grouping: str) -> str:
    return example.task if grouping == "task" else example.group_id


@dataclass(frozen=True)
class MetricComparison:
    metric: str
    candidate: float
    legacy: float
    equal_weight: Optional[float]
    oriented_delta: float
    ci_lower: float
    ci_upper: float
    noninferiority_margin: float
    noninferior: bool
    meaningful_improvement: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HoldoutActivationReport:
    artifact_id: str
    policy_id: str
    protocol_id: str
    holdout_dataset_sha256: str
    group_count: int
    example_count: int
    positive_count: int
    negative_count: int
    comparisons: Mapping[str, MetricComparison]
    candidate_metrics: Mapping[str, Any]
    legacy_metrics: Mapping[str, Any]
    equal_weight_metrics: Mapping[str, Any]
    stratified_metrics: Mapping[str, Any]
    eligible: bool
    eligibility_reasons: tuple[str, ...]
    source_commit: str
    schema_version: int = HOLDOUT_REPORT_SCHEMA_VERSION
    report_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != HOLDOUT_REPORT_SCHEMA_VERSION:
            raise ValueError("Unsupported holdout report schema")
        if not self.artifact_id or not self.policy_id or not self.protocol_id:
            raise ValueError("Artifact, policy, and protocol IDs are required")
        expected = self.compute_report_id()
        if self.report_id and self.report_id != expected:
            raise ValueError("Holdout report hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("report_id", None)
        payload["comparisons"] = {
            name: comparison.to_dict()
            for name, comparison in sorted(self.comparisons.items())
        }
        return payload

    def compute_report_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "HoldoutActivationReport":
        return replace(self, report_id=self.compute_report_id())

    def to_dict(self) -> dict[str, Any]:
        report = self if self.report_id else self.with_id()
        payload = report.payload_without_id()
        payload["report_id"] = report.report_id
        return payload


def _stratified(
    examples: Sequence[FusionExample],
    candidate: np.ndarray,
    legacy: np.ndarray,
    *,
    ece_bins: int,
) -> dict[str, Any]:
    fields = {
        "difficulty": lambda item: str(item.metadata.get("difficulty", "unknown")),
        "goal_status": lambda item: str(item.metadata.get("goal_status", "unknown")),
        "knowledge_available": lambda item: str(
            item.metadata.get("knowledge_available", "unknown")
        ),
        "environment_status": lambda item: str(
            item.metadata.get("environment_status", "unknown")
        ),
    }
    output: dict[str, Any] = {}
    for field_name, getter in fields.items():
        values: dict[str, list[int]] = {}
        for index, item in enumerate(examples):
            values.setdefault(getter(item), []).append(index)
        output[field_name] = {}
        for value, indices in sorted(values.items()):
            y = np.asarray([examples[i].label for i in indices], dtype=np.float64)
            candidate_subset = candidate[indices]
            legacy_subset = legacy[indices]
            output[field_name][value] = {
                "count": len(indices),
                "positive_rate": float(y.mean()),
                "candidate": _metric_report(y, candidate_subset, bins=ece_bins),
                "legacy": _metric_report(y, legacy_subset, bins=ece_bins),
            }
    return output


def evaluate_holdout(
    examples: Sequence[FusionExample],
    *,
    artifact: FusionArtifact,
    policy: ActivationPolicy,
    protocol_id: str,
    source_commit: str,
) -> HoldoutActivationReport:
    if not examples:
        raise ValueError("Holdout examples are required")
    if any(item.legacy_probability is None for item in examples):
        raise ValueError("Every holdout example needs a legacy probability")
    if any(item.split not in {"test", "validation"} for item in examples):
        # Existing Round 5 datasets use 'test' for locked holdout. Accept
        # validation only for backward-compatible synthetic fixtures.
        raise ValueError("Holdout dataset contains training examples")

    labels = np.asarray([item.label for item in examples], dtype=np.float64)
    if len(np.unique(labels)) < 2:
        raise ValueError("Holdout must include both successful and failed steps")
    candidate = np.asarray(
        [_candidate_probability(item, artifact) for item in examples],
        dtype=np.float64,
    )
    legacy = np.asarray(
        [float(item.legacy_probability) for item in examples],
        dtype=np.float64,
    )
    equal_weight = np.asarray(
        [_equal_weight_probability(item) for item in examples],
        dtype=np.float64,
    )

    metrics = tuple(dict.fromkeys(policy.primary_metrics + policy.calibration_metrics))
    candidate_report = _metric_report(labels, candidate, bins=policy.ece_bins)
    legacy_report = _metric_report(labels, legacy, bins=policy.ece_bins)
    equal_report = _metric_report(labels, equal_weight, bins=policy.ece_bins)

    groups: dict[str, list[int]] = {}
    for index, item in enumerate(examples):
        groups.setdefault(_group_key(item, policy.bootstrap_grouping), []).append(index)
    if len(groups) < 2:
        raise ValueError("Grouped bootstrap requires at least two groups")

    rng = np.random.default_rng(policy.bootstrap_seed)
    group_names = sorted(groups)
    bootstrap_deltas: dict[str, list[float]] = {metric: [] for metric in metrics}

    for _ in range(policy.bootstrap_replicates):
        sampled_groups = rng.choice(group_names, size=len(group_names), replace=True)
        indices: list[int] = []
        for group_name in sampled_groups:
            indices.extend(groups[str(group_name)])
        y = labels[indices]
        if len(np.unique(y)) < 2:
            continue
        p_candidate = candidate[indices]
        p_legacy = legacy[indices]
        for metric in metrics:
            candidate_value = _metric_value(
                metric, y, p_candidate, ece_bins=policy.ece_bins
            )
            legacy_value = _metric_value(
                metric, y, p_legacy, ece_bins=policy.ece_bins
            )
            if candidate_value is None or legacy_value is None:
                continue
            bootstrap_deltas[metric].append(
                _oriented_delta(metric, candidate_value, legacy_value)
            )

    comparisons: dict[str, MetricComparison] = {}
    reasons: list[str] = []
    improvement_count = 0
    for metric in metrics:
        candidate_value = candidate_report.get(metric)
        legacy_value = legacy_report.get(metric)
        equal_value = equal_report.get(metric)
        if candidate_value is None or legacy_value is None:
            reasons.append(f"{metric}: unavailable")
            continue
        deltas = bootstrap_deltas[metric]
        if len(deltas) < max(100, int(policy.bootstrap_replicates * 0.5)):
            reasons.append(f"{metric}: too few valid bootstrap replicates")
            continue
        ci_lower, ci_upper = _percentile_interval(
            deltas, policy.confidence_level
        )
        delta = _oriented_delta(metric, float(candidate_value), float(legacy_value))
        margin = float(policy.noninferiority_margins[metric])
        noninferior = ci_upper <= margin
        minimum_effect = float(policy.minimum_effects.get(metric, 0.0))
        meaningful = delta <= -minimum_effect
        if policy.require_improvement_ci_upper_at_most_zero:
            meaningful = meaningful and ci_upper <= 0.0
        comparisons[metric] = MetricComparison(
            metric=metric,
            candidate=float(candidate_value),
            legacy=float(legacy_value),
            equal_weight=None if equal_value is None else float(equal_value),
            oriented_delta=delta,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            noninferiority_margin=margin,
            noninferior=noninferior,
            meaningful_improvement=meaningful,
        )
        if not noninferior:
            reasons.append(
                f"{metric}: noninferiority failed "
                f"(CI upper {ci_upper:.6g} > margin {margin:.6g})"
            )
        if metric in policy.primary_metrics and meaningful:
            improvement_count += 1

    for metric in policy.primary_metrics + policy.calibration_metrics:
        comparison = comparisons.get(metric)
        if comparison is None:
            reasons.append(f"{metric}: comparison missing")
        elif not comparison.noninferior:
            pass

    if improvement_count < policy.minimum_primary_improvements:
        reasons.append(
            "Insufficient primary metric improvements: "
            f"{improvement_count} < {policy.minimum_primary_improvements}"
        )

    eligible = not reasons
    return HoldoutActivationReport(
        artifact_id=artifact.artifact_id or artifact.compute_artifact_id(),
        policy_id=policy.policy_id or policy.compute_policy_id(),
        protocol_id=protocol_id,
        holdout_dataset_sha256=dataset_sha256(examples),
        group_count=len(groups),
        example_count=len(examples),
        positive_count=int(labels.sum()),
        negative_count=int(len(labels) - labels.sum()),
        comparisons=comparisons,
        candidate_metrics=candidate_report,
        legacy_metrics=legacy_report,
        equal_weight_metrics=equal_report,
        stratified_metrics=_stratified(
            examples,
            candidate,
            legacy,
            ece_bins=policy.ece_bins,
        ),
        eligible=eligible,
        eligibility_reasons=tuple(reasons),
        source_commit=source_commit,
    ).with_id()


def save_holdout_report(
    path: str | Path,
    report: HoldoutActivationReport,
    *,
    refuse_overwrite: bool = True,
) -> str:
    output = Path(path)
    if output.exists() and refuse_overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing holdout report: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    report = report.with_id()
    output.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report.report_id


def load_holdout_report(path: str | Path) -> HoldoutActivationReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["comparisons"] = {
        name: MetricComparison(**value)
        for name, value in payload["comparisons"].items()
    }
    payload["eligibility_reasons"] = tuple(payload["eligibility_reasons"])
    return HoldoutActivationReport(**payload)
