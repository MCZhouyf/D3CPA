"""Compile a small pre-outcome Environment candidate grid around active defaults.

Preferred behavior is to reuse an already preregistered grid. When no such grid
exists, the author-approved fallback is a one-factor-at-a-time grid around the
active Environment V2 defaults:

- minimum similarity: anchor ± 0.10;
- minimum coverage: anchor ± 0.10;
- mismatch compatibility: anchor ± 0.05;
- match compatibility: anchor ± 0.05;
- plus the unchanged anchor.

Values are clamped to [0,1], invalid mismatch>=match candidates are removed,
and duplicates are removed. This avoids an outcome-adaptive Cartesian search.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .environment_parameter_selection import EnvironmentCandidate


SIMILARITY_DELTA = 0.10
COVERAGE_DELTA = 0.10
COMPATIBILITY_DELTA = 0.05


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, round(float(value), 10)))


@dataclass(frozen=True)
class CompiledEnvironmentGrid:
    anchor_config_id: str
    source: str
    candidates: tuple[EnvironmentCandidate, ...]
    one_factor_at_a_time: bool
    outcome_data_used: bool
    grid_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_only": False,
            "anchor_config_id": self.anchor_config_id,
            "source": self.source,
            "one_factor_at_a_time": self.one_factor_at_a_time,
            "outcome_data_used": self.outcome_data_used,
            "candidates": [item.to_dict() for item in self.candidates],
            "grid_id": self.grid_id,
        }


def compile_grid_from_anchor(
    anchor: Mapping[str, Any],
    *,
    anchor_config_id: str,
) -> CompiledEnvironmentGrid:
    if not anchor_config_id:
        raise ValueError("Environment anchor config ID is required")
    base = {
        "top_k": int(anchor["top_k"]),
        "minimum_similarity": float(anchor["minimum_similarity"]),
        "minimum_coverage": float(anchor["minimum_coverage"]),
        "mismatch_compatibility_threshold": float(
            anchor["mismatch_compatibility_threshold"]
        ),
        "match_compatibility_threshold": float(
            anchor["match_compatibility_threshold"]
        ),
    }
    if base["top_k"] != 3:
        raise ValueError("Environment anchor must use top_k=3")
    variants: list[dict[str, Any]] = [dict(base)]
    changes = (
        ("minimum_similarity", SIMILARITY_DELTA),
        ("minimum_coverage", COVERAGE_DELTA),
        ("mismatch_compatibility_threshold", COMPATIBILITY_DELTA),
        ("match_compatibility_threshold", COMPATIBILITY_DELTA),
    )
    for field, delta in changes:
        for sign in (-1.0, 1.0):
            candidate = dict(base)
            candidate[field] = _clamp(candidate[field] + sign * delta)
            variants.append(candidate)

    normalized: dict[str, EnvironmentCandidate] = {}
    for payload in variants:
        if payload["mismatch_compatibility_threshold"] >= (
            payload["match_compatibility_threshold"]
        ):
            continue
        candidate = EnvironmentCandidate(**payload).with_id()
        normalized[candidate.candidate_id] = candidate
    candidates = tuple(
        normalized[key] for key in sorted(normalized)
    )
    if not candidates:
        raise ValueError("Compiled Environment grid is empty")
    grid_id = _sha([item.to_dict() for item in candidates])
    return CompiledEnvironmentGrid(
        anchor_config_id=anchor_config_id,
        source="active_environment_v2_defaults_one_factor_at_a_time",
        candidates=candidates,
        one_factor_at_a_time=True,
        outcome_data_used=False,
        grid_id=grid_id,
    )
