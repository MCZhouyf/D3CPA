"""Memory lifecycle modes used by acquisition, calibration, and evaluation."""
from __future__ import annotations

from enum import Enum
from typing import Any


class MemoryMode(str, Enum):
    ACQUIRE = "acquire"
    CALIBRATE = "calibrate"
    EVALUATE_READONLY = "evaluate_readonly"
    DISABLED = "disabled"

    @classmethod
    def parse(cls, value: Any) -> "MemoryMode":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value))
        except ValueError as exc:
            allowed = ", ".join(mode.value for mode in cls)
            raise ValueError(f"memory_mode must be one of: {allowed}") from exc

    @property
    def allows_long_term_write(self) -> bool:
        return self is MemoryMode.ACQUIRE

    @property
    def requires_frozen_snapshot(self) -> bool:
        return self in {MemoryMode.CALIBRATE, MemoryMode.EVALUATE_READONLY}

    @property
    def memory_enabled(self) -> bool:
        return self is not MemoryMode.DISABLED
