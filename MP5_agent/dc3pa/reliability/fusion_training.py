"""Deterministic nonnegative Logistic trainer and calibration metrics."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .fusion_dataset import FusionExample
from .fusion_features import FUSION_FEATURE_NAMES


_EPS = 1e-12


def sigmoid(logits: np.ndarray | float) -> np.ndarray:
    values = np.asarray(logits, dtype=np.float64)
    positive = values >= 0
    output = np.empty_like(values)
    output[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_values = np.exp(values[~positive])
    output[~positive] = exp_values / (1.0 + exp_values)
    return output


def _matrix(examples: Sequence[FusionExample]) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(
        [[float(item.features[name]) for name in FUSION_FEATURE_NAMES] for item in examples],
        dtype=np.float64,
    )
    y = np.asarray([item.label for item in examples], dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != len(FUSION_FEATURE_NAMES):
        raise ValueError("Invalid feature matrix")
    if len(np.unique(y)) < 2:
        raise ValueError("Training split must contain both successful and failed steps")
    return x, y


def brier_score(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def binary_nll(y: np.ndarray, p: np.ndarray) -> float:
    clipped = np.clip(p, _EPS, 1.0 - _EPS)
    return float(-np.mean(y * np.log(clipped) + (1.0 - y) * np.log(1.0 - clipped)))


def ece_score(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    if bins <= 0:
        raise ValueError("bins must be positive")
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(y)
    value = 0.0
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        if index == bins - 1:
            mask = (p >= lower) & (p <= upper)
        else:
            mask = (p >= lower) & (p < upper)
        count = int(mask.sum())
        if not count:
            continue
        value += (count / total) * abs(float(p[mask].mean()) - float(y[mask].mean()))
    return float(value)


def reliability_bins(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict[str, Any]]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows: list[dict[str, Any]] = []
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        if index == bins - 1:
            mask = (p >= lower) & (p <= upper)
        else:
            mask = (p >= lower) & (p < upper)
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


def roc_auc(y: np.ndarray, p: np.ndarray) -> Optional[float]:
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


def average_precision(y: np.ndarray, p: np.ndarray) -> Optional[float]:
    positives = int((y == 1).sum())
    if positives == 0:
        return None
    order = np.argsort(-p, kind="mergesort")
    sorted_y = y[order]
    cumulative = np.cumsum(sorted_y)
    precision = cumulative / np.arange(1, len(y) + 1)
    return float((precision * sorted_y).sum() / positives)


def metric_report(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict[str, Any]:
    return {
        "count": int(len(y)),
        "positive_rate": float(y.mean()),
        "brier": brier_score(y, p),
        "nll": binary_nll(y, p),
        "ece": ece_score(y, p, bins=bins),
        "auroc": roc_auc(y, p),
        "average_precision": average_precision(y, p),
        "reliability_bins": reliability_bins(y, p, bins=bins),
    }


@dataclass(frozen=True)
class TrainerConfig:
    learning_rate: float = 0.05
    l2: float = 1e-3
    max_epochs: int = 5000
    patience: int = 200
    min_delta: float = 1e-8
    ece_bins: int = 10

    def __post_init__(self) -> None:
        if not self.learning_rate > 0:
            raise ValueError("learning_rate must be positive")
        if self.l2 < 0:
            raise ValueError("l2 must be nonnegative")
        if self.max_epochs <= 0 or self.patience <= 0:
            raise ValueError("max_epochs and patience must be positive")


@dataclass(frozen=True)
class FitResult:
    intercept: float
    coefficients: Mapping[str, float]
    epochs: int
    training_metrics: Mapping[str, Any]
    validation_metrics: Mapping[str, Any]
    legacy_validation_metrics: Optional[Mapping[str, Any]]
    equal_weight_validation_metrics: Mapping[str, Any]
    activation_assessment: Mapping[str, Any]
    trainer_config: Mapping[str, Any]


def _predict(x: np.ndarray, intercept: float, coefficients: np.ndarray) -> np.ndarray:
    return sigmoid(intercept + x @ coefficients)


def assess_activation(
    new_metrics: Mapping[str, Any],
    legacy_metrics: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    if not legacy_metrics:
        return {
            "eligible": False,
            "reason": "legacy validation probabilities were not available",
        }
    brier_ok = float(new_metrics["brier"]) <= float(legacy_metrics["brier"]) + 1e-12
    nll_ok = float(new_metrics["nll"]) <= float(legacy_metrics["nll"]) + 1e-12
    ece_ok = float(new_metrics["ece"]) <= float(legacy_metrics["ece"]) + 1e-12
    return {
        "eligible": bool(brier_ok and nll_ok and ece_ok),
        "brier_not_worse": brier_ok,
        "nll_not_worse": nll_ok,
        "ece_not_worse": ece_ok,
        "note": "This is a development-set gate, not evidence from final test seeds.",
    }


def fit_monotonic_logistic(
    training: Sequence[FusionExample],
    validation: Sequence[FusionExample],
    *,
    config: Optional[TrainerConfig] = None,
) -> FitResult:
    config = config or TrainerConfig()
    if not training or not validation:
        raise ValueError("Both training and validation splits are required")

    x_train, y_train = _matrix(training)
    x_val, y_val = _matrix(validation)

    # Deterministic initialization. Nonnegative coefficients are projected after
    # every update; the intercept remains unconstrained.
    coefficients = np.zeros(len(FUSION_FEATURE_NAMES), dtype=np.float64)
    prevalence = float(np.clip(y_train.mean(), 1e-6, 1.0 - 1e-6))
    intercept = math.log(prevalence / (1.0 - prevalence))

    best = (float("inf"), intercept, coefficients.copy(), 0)
    stale = 0
    for epoch in range(1, config.max_epochs + 1):
        probabilities = _predict(x_train, intercept, coefficients)
        residual = probabilities - y_train
        grad_b = float(residual.mean())
        grad_w = (x_train.T @ residual) / len(y_train) + config.l2 * coefficients

        intercept -= config.learning_rate * grad_b
        coefficients -= config.learning_rate * grad_w
        coefficients = np.maximum(coefficients, 0.0)

        validation_probability = _predict(x_val, intercept, coefficients)
        validation_loss = binary_nll(y_val, validation_probability)
        if validation_loss < best[0] - config.min_delta:
            best = (validation_loss, intercept, coefficients.copy(), epoch)
            stale = 0
        else:
            stale += 1
            if stale >= config.patience:
                break

    _, intercept, coefficients, best_epoch = best
    train_probability = _predict(x_train, intercept, coefficients)
    validation_probability = _predict(x_val, intercept, coefficients)

    legacy_values = [item.legacy_probability for item in validation]
    legacy_metrics = None
    if all(value is not None for value in legacy_values):
        legacy_metrics = metric_report(
            y_val,
            np.asarray(legacy_values, dtype=np.float64),
            bins=config.ece_bins,
        )
    equal_weight_probability = np.asarray(
        [
            sum(float(item.features[name]) for name in FUSION_FEATURE_NAMES)
            / len(FUSION_FEATURE_NAMES)
            for item in validation
        ],
        dtype=np.float64,
    )

    validation_metrics = metric_report(
        y_val, validation_probability, bins=config.ece_bins
    )
    return FitResult(
        intercept=float(intercept),
        coefficients={
            name: float(value)
            for name, value in zip(FUSION_FEATURE_NAMES, coefficients)
        },
        epochs=int(best_epoch),
        training_metrics=metric_report(
            y_train, train_probability, bins=config.ece_bins
        ),
        validation_metrics=validation_metrics,
        legacy_validation_metrics=legacy_metrics,
        equal_weight_validation_metrics=metric_report(
            y_val, equal_weight_probability, bins=config.ece_bins
        ),
        activation_assessment=assess_activation(
            validation_metrics, legacy_metrics
        ),
        trainer_config=asdict(config),
    )
