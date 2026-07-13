"""Test-only dependency gate for legacy MineDojo Controller integration tests.

Hosted infrastructure CI intentionally does not install the full simulator stack.
This module must never be imported by production code.
"""

from __future__ import annotations

import importlib.util
from typing import Iterable, Tuple

import pytest


LEGACY_CONTROLLER_OPTIONAL_MODULES: Tuple[str, ...] = (
    "minedojo",
    "openai",
    "langchain",
    "requests",
)


def missing_legacy_controller_dependencies(
    modules: Iterable[str] = LEGACY_CONTROLLER_OPTIONAL_MODULES,
) -> Tuple[str, ...]:
    """Return optional modules unavailable in the current test environment."""

    missing = []
    for module_name in modules:
        try:
            available = importlib.util.find_spec(module_name) is not None
        except (ImportError, AttributeError, ValueError):
            available = False
        if not available:
            missing.append(module_name)
    return tuple(missing)


def require_legacy_controller_test_dependencies() -> None:
    """Skip one genuine legacy-Controller test when its runtime stack is absent.

    This is deliberately narrow: pure DC3PA infrastructure tests must not call this
    function and must continue to fail normally when broken.
    """

    missing = missing_legacy_controller_dependencies()
    if missing:
        pytest.skip(
            "legacy Controller integration requires optional runtime modules: "
            + ", ".join(missing)
        )
