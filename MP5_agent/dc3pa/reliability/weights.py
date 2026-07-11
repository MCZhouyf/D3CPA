from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional

from .contracts import DIMENSIONS, DimensionScore, StrategyWeights


@dataclass(frozen=True)
class LinearMemoryWeightPolicy:
    learned_weight_cap: float = 0.4
    memory_weight_growth: float = 0.02

    def __post_init__(self) -> None:
        values = {
            "learned_weight_cap": self.learned_weight_cap,
            "memory_weight_growth": self.memory_weight_growth,
        }
        for label, value in values.items():
            if isinstance(value, bool):
                raise ValueError(f"{label} cannot be bool")
            if not math.isfinite(float(value)):
                raise ValueError(f"{label} must be finite")
        if not 0.0 <= self.learned_weight_cap <= 0.5:
            raise ValueError("learned_weight_cap must be in [0, 0.5]")
        if self.memory_weight_growth < 0.0:
            raise ValueError("memory_weight_growth cannot be negative")

    def weights(self, successful_memory_count: int) -> StrategyWeights:
        if (
            isinstance(successful_memory_count, bool)
            or not isinstance(successful_memory_count, int)
            or successful_memory_count < 0
        ):
            raise ValueError("successful_memory_count must be a non-negative integer")
        learned = min(
            self.learned_weight_cap,
            self.memory_weight_growth * float(successful_memory_count),
        )
        return StrategyWeights(
            knowledge=learned,
            model=1.0 - 2.0 * learned,
            environment=learned,
        )


def effective_weights(
    base: StrategyWeights,
    scores: Mapping[str, DimensionScore],
) -> Optional[StrategyWeights]:
    """Renormalize paper weights across signals available for this step.

    A zero-weight signal does not become active merely because another provider failed.
    This preserves model-only cold-start semantics. If every positive-weight signal is
    unavailable, the overall reliability is unavailable rather than silently guessed.
    """

    base_dict = base.as_dict()
    usable = {
        name: base_dict[name]
        for name in DIMENSIONS
        if scores[name].available and base_dict[name] > 0.0
    }
    total = sum(usable.values())
    if total <= 0.0:
        return None
    normalized = {name: usable.get(name, 0.0) / total for name in DIMENSIONS}
    return StrategyWeights(
        knowledge=normalized["knowledge"],
        model=normalized["model"],
        environment=normalized["environment"],
    )
