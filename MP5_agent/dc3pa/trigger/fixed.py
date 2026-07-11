from __future__ import annotations

import math
from statistics import fmean
from typing import Optional, Sequence

from .contracts import TriggerObservation, TriggerWindow


class FixedIntervalTriggerSession:
    def __init__(self, total_steps: int, interval: int = 1, threshold: float = 0.8):
        if total_steps <= 0:
            raise ValueError("total_steps must be positive")
        if interval <= 0:
            raise ValueError("interval must be positive")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        self.total_steps = int(total_steps)
        self.interval = int(interval)
        self.threshold = float(threshold)
        self.cursor = 0
        self._pending: Optional[TriggerWindow] = None
        self._forced_next = False
        self.history: list[TriggerObservation] = []

    @property
    def finished(self) -> bool:
        return self.cursor >= self.total_steps and self._pending is None

    def next_window(self) -> Optional[TriggerWindow]:
        if self._pending is not None:
            raise RuntimeError("observe() must be called before requesting another window")
        if self.cursor >= self.total_steps:
            return None
        interval = 1 if self._forced_next else self.interval
        end = min(self.total_steps - 1, self.cursor + interval - 1)
        window = TriggerWindow(
            start_index=self.cursor,
            end_index=end,
            interval=interval,
            forced=self._forced_next,
            reason="post_revision_validation" if self._forced_next else "fixed_schedule",
        )
        self._forced_next = False
        self._pending = window
        return window

    def observe(
        self,
        probabilities: Sequence[Optional[float]],
        hard_conflict: bool = False,
    ) -> TriggerObservation:
        if self._pending is None:
            raise RuntimeError("next_window() must be called before observe()")
        if len(probabilities) != len(self._pending.step_indices):
            raise ValueError("probability count does not match pending window")
        if any(isinstance(value, bool) for value in probabilities if value is not None):
            raise ValueError("probabilities cannot be booleans")
        available = [float(value) for value in probabilities if value is not None]
        if any(
            not math.isfinite(value) or not 0.0 <= value <= 1.0
            for value in available
        ):
            raise ValueError("probabilities must be finite and in [0, 1]")
        had_unavailable = len(available) != len(probabilities)
        monitored = float(fmean(available)) if available else None
        low = hard_conflict or had_unavailable or monitored is None or monitored < self.threshold
        observation = TriggerObservation(
            window=self._pending,
            probabilities=tuple(probabilities),
            monitored_confidence=monitored,
            threshold=self.threshold,
            low_confidence=low,
            hard_conflict=hard_conflict,
            had_unavailable=had_unavailable,
            previous_interval=self.interval,
            next_interval=self.interval,
        )
        self.history.append(observation)
        self.cursor = self._pending.end_index + 1
        self._pending = None
        return observation

    def restart_after_revision(self, start_index: int, total_steps: int) -> None:
        if self._pending is not None:
            raise RuntimeError("Cannot restart while a trigger window is pending")
        if total_steps <= 0 or not 0 <= start_index < total_steps:
            raise ValueError("Invalid revised plan range")
        self.total_steps = int(total_steps)
        self.cursor = int(start_index)
        self._forced_next = True
