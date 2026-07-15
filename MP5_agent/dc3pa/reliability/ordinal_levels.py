"""Shared ordinal confidence vocabulary for DC3PA Round 3.

The vocabulary is deliberately small and closed.  Providers may vary case and use
spaces/hyphens, but synonyms and numeric substitutes are rejected in ordinal mode.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

ORDINAL_LEVELS = (
    "very_unlikely",
    "unlikely",
    "uncertain",
    "likely",
    "very_likely",
)

BASE_ORDINAL_MAPPING: Dict[str, float] = {
    "very_unlikely": 0.1,
    "unlikely": 0.3,
    "uncertain": 0.5,
    "likely": 0.7,
    "very_likely": 0.9,
}

MODEL_CONFIDENCE_IMPLS = frozenset(
    {
        "legacy_numeric",
        "ordinal_v2",
        "ordinal_shadow",
        "ordinal_calibrated",
    }
)


def normalize_ordinal_level(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("confidence_level must be a string")
    normalized = "_".join(value.strip().lower().replace("-", " ").split())
    if normalized not in ORDINAL_LEVELS:
        raise ValueError(
            f"confidence_level must be one of {list(ORDINAL_LEVELS)}, got {value!r}"
        )
    return normalized


def validate_model_confidence_impl(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in MODEL_CONFIDENCE_IMPLS:
        raise ValueError(
            "model_confidence_impl must be one of "
            f"{sorted(MODEL_CONFIDENCE_IMPLS)}, got {value!r}"
        )
    return normalized


def validate_mapping(mapping: Mapping[str, Any], *, label: str) -> Dict[str, float]:
    if set(mapping) != set(ORDINAL_LEVELS):
        raise ValueError(
            f"{label} must contain exactly {list(ORDINAL_LEVELS)}, "
            f"got {sorted(mapping)}"
        )
    result: Dict[str, float] = {}
    previous = -1.0
    for level in ORDINAL_LEVELS:
        value = mapping[level]
        if isinstance(value, bool):
            raise ValueError(f"{label}[{level!r}] must be numeric, not bool")
        number = float(value)
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"{label}[{level!r}] must be in [0, 1]")
        if number < previous:
            raise ValueError(f"{label} must be monotonically non-decreasing")
        result[level] = number
        previous = number
    return result
