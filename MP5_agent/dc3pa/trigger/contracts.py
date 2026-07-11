from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Sequence


@dataclass(frozen=True)
class TriggerWindow:
    start_index: int
    end_index: int
    interval: int
    forced: bool = False
    reason: str = "scheduled"

    def __post_init__(self) -> None:
        values = (self.start_index, self.end_index, self.interval)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("TriggerWindow indices and interval must be integers")
        if self.start_index < 0 or self.end_index < self.start_index:
            raise ValueError("TriggerWindow range is invalid")
        if self.interval <= 0:
            raise ValueError("TriggerWindow.interval must be positive")
        if not isinstance(self.forced, bool):
            raise ValueError("TriggerWindow.forced must be bool")
        if not self.reason.strip():
            raise ValueError("TriggerWindow.reason cannot be empty")

    @property
    def step_indices(self) -> tuple[int, ...]:
        return tuple(range(self.start_index, self.end_index + 1))

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["step_indices"] = list(self.step_indices)
        return result


@dataclass(frozen=True)
class TriggerObservation:
    window: TriggerWindow
    probabilities: tuple[Optional[float], ...]
    monitored_confidence: Optional[float]
    threshold: float
    low_confidence: bool
    hard_conflict: bool
    had_unavailable: bool
    previous_interval: int
    next_interval: int

    def __post_init__(self) -> None:
        if len(self.probabilities) != len(self.window.step_indices):
            raise ValueError("TriggerObservation probabilities must match the window")
        for value in (*self.probabilities, self.monitored_confidence, self.threshold):
            if value is None:
                continue
            if isinstance(value, bool):
                raise ValueError("Trigger probabilities cannot be booleans")
            number = float(value)
            if not math.isfinite(number) or not 0.0 <= number <= 1.0:
                raise ValueError("Trigger probabilities must be finite and in [0, 1]")
        flags = (self.low_confidence, self.hard_conflict, self.had_unavailable)
        if any(not isinstance(value, bool) for value in flags):
            raise ValueError("TriggerObservation flags must be bool")
        intervals = (self.previous_interval, self.next_interval)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in intervals
        ):
            raise ValueError("TriggerObservation intervals must be positive integers")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window": self.window.to_dict(),
            "probabilities": list(self.probabilities),
            "monitored_confidence": self.monitored_confidence,
            "threshold": self.threshold,
            "low_confidence": self.low_confidence,
            "hard_conflict": self.hard_conflict,
            "had_unavailable": self.had_unavailable,
            "previous_interval": self.previous_interval,
            "next_interval": self.next_interval,
        }
