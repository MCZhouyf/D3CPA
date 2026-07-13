"""Pure policy helpers for making deterministic material repair explicit.

The helpers preserve the current planner behavior under ``legacy`` and allow the
planner integration to be changed without embedding string comparisons throughout
``cognitive_control.py``.
"""

from __future__ import annotations

from typing import Final


LEGACY: Final[str] = "legacy"
EVALUATION_ONLY: Final[str] = "evaluation_only"
EVALUATION_THEN_DETERMINISTIC_FALLBACK: Final[str] = (
    "evaluation_then_deterministic_fallback"
)
BLOCK_ON_UNRESOLVED: Final[str] = "block_on_unresolved"

CONSTRAINT_REPAIR_POLICIES = frozenset(
    {
        LEGACY,
        EVALUATION_ONLY,
        EVALUATION_THEN_DETERMINISTIC_FALLBACK,
        BLOCK_ON_UNRESOLVED,
    }
)
REPAIR_PHASES = frozenset({"request_replan", "post_patch"})


def validate_constraint_repair_policy(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in CONSTRAINT_REPAIR_POLICIES:
        raise ValueError(
            "constraint_repair_policy must be one of "
            f"{sorted(CONSTRAINT_REPAIR_POLICIES)}, got {value!r}"
        )
    return normalized


def should_attempt_deterministic_repair(
    policy: str,
    *,
    phase: str,
    hard_conflict: bool,
) -> bool:
    """Return whether deterministic material repair is allowed at this point.

    ``legacy`` exactly mirrors the pre-Round-2 planner:
      * after ``request_replan``: repair only when a hard conflict exists;
      * after a patch: always run the deterministic repair pass.

    The recommended paper policy only uses repair as a fallback for a known hard
    conflict, after the Evaluation Chain has had the first opportunity to revise.
    """

    policy = validate_constraint_repair_policy(policy)
    phase = str(phase).strip().lower()
    if phase not in REPAIR_PHASES:
        raise ValueError(f"phase must be one of {sorted(REPAIR_PHASES)}, got {phase!r}")

    if policy == LEGACY:
        return bool(hard_conflict) if phase == "request_replan" else True
    if policy == EVALUATION_THEN_DETERMINISTIC_FALLBACK:
        return bool(hard_conflict)
    return False


def should_block_unresolved_hard_conflict(policy: str) -> bool:
    return validate_constraint_repair_policy(policy) == BLOCK_ON_UNRESOLVED
