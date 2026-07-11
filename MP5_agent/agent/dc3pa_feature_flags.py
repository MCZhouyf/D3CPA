"""Small local compatibility module for legacy agent scripts.

The original MP5 scripts are commonly executed with ``MP5_agent/agent`` as the only
import root. Keeping this module beside them avoids fragile PYTHONPATH assumptions.
"""

import os

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _read_bool(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise ValueError("Unsupported boolean value for %s: %r" % (name, raw))


def legacy_task_hacks_enabled():
    return _read_bool("DC3PA_LEGACY_TASK_HACKS", True)


def controller_low_level_recovery_enabled():
    return _read_bool("DC3PA_CONTROLLER_LOW_LEVEL_RECOVERY", True)
