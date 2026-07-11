from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _read_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise ValueError(
        f"Environment variable {name}={raw!r} is not a supported boolean value"
    )


def legacy_task_hacks_enabled() -> bool:
    return _read_bool("DC3PA_LEGACY_TASK_HACKS", True)


def controller_low_level_recovery_enabled() -> bool:
    return _read_bool("DC3PA_CONTROLLER_LOW_LEVEL_RECOVERY", True)
