from __future__ import annotations

import math
from collections import deque
from statistics import fmean
from typing import Iterable, Optional, Sequence

from ..reliability.config import AdaptiveTriggerConfig
from .contracts import TriggerObservation, TriggerWindow


class AdaptiveTriggerSession:
    """Stateful variable-cadence gate over consecutive planning-step windows."""

    def __init__(self, total_steps: int, config: AdaptiveTriggerConfig):
        config.validate()
        if total_steps <= 0:
            raise ValueError("total_steps must be positive")
        self.config = config
        self.total_steps = int(total_steps)
        self.cursor = 0
        self.current_interval = config.initial_interval
        self._recent = deque(maxlen=config.window_size)
        self._pending: Optional[TriggerWindow] = None
        self._forced_next = False
        self._forced_reason = ""
        self.history: list[TriggerObservation] = []

    @property
    def finished(self) -> bool:
        return self.cursor >= self.total_steps and self._pending is None

    def next_window(self) -> Optional[TriggerWindow]:
        if self._pending is not None:
            raise RuntimeError("observe() must be called before requesting another window")
        if self.cursor >= self.total_steps:
            return None
        interval = 1 if self._forced_next else self.current_interval
        end = min(self.total_steps - 1, self.cursor + interval - 1)
        window = TriggerWindow(
            start_index=self.cursor,
            end_index=end,
            interval=interval,
            forced=self._forced_next,
            reason=self._forced_reason if self._forced_next else "adaptive_schedule",
        )
        self._pending = window
        self._forced_next = False
        self._forced_reason = ""
        return window

    def observe(
        self,
        probabilities: Sequence[Optional[float]],
        hard_conflict: bool = False,
    ) -> TriggerObservation:
        if self._pending is None:
            raise RuntimeError("next_window() must be called before observe()")
        expected = len(self._pending.step_indices)
        if len(probabilities) != expected:
            raise ValueError(
                f"Expected {expected} probabilities for pending window, got {len(probabilities)}"
            )
        available = []
        had_unavailable = False
        for value in probabilities:
            if value is None:
                had_unavailable = True
                continue
            if isinstance(value, bool):
                raise ValueError("probabilities cannot be booleans")
            number = float(value)
            if not math.isfinite(number) or not 0.0 <= number <= 1.0:
                raise ValueError("probabilities must be finite and in [0, 1]")
            available.append(number)
            self._recent.append(number)
        monitored = float(fmean(self._recent)) if self._recent else None
        low = (
            hard_conflict
            or had_unavailable
            or monitored is None
            or monitored < self.config.threshold
        )
        previous = self.current_interval
        if hard_conflict:
            next_interval = self.config.minimum_interval
        elif low:
            next_interval = max(
                self.config.minimum_interval,
                previous - self.config.decrease_step,
            )
        else:
            next_interval = min(
                self.config.maximum_interval,
                previous + self.config.increase_step,
            )
        observation = TriggerObservation(
            window=self._pending,
            probabilities=tuple(probabilities),
            monitored_confidence=monitored,
            threshold=self.config.threshold,
            low_confidence=low,
            hard_conflict=hard_conflict,
            had_unavailable=had_unavailable,
            previous_interval=previous,
            next_interval=next_interval,
        )
        self.history.append(observation)
        self.current_interval = next_interval
        self.cursor = self._pending.end_index + 1
        self._pending = None
        return observation

    def restart_after_revision(self, start_index: int, total_steps: int) -> None:
        if self._pending is not None:
            raise RuntimeError("Cannot restart while a trigger window is pending")
        if total_steps <= 0:
            raise ValueError("total_steps must be positive")
        if not 0 <= start_index < total_steps:
            raise ValueError("start_index is out of range for revised plan")
        self.total_steps = int(total_steps)
        self.cursor = int(start_index)
        # Scores from an earlier plan version must not influence the revised plan.
        self._recent.clear()
        self._forced_next = True
        self._forced_reason = "post_revision_validation"
