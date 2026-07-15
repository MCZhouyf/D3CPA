from __future__ import annotations

import pytest

from dc3pa.reliability.environment_v2 import (
    ENVIRONMENT_IMPLS,
    ENVIRONMENT_SCOPES,
    validate_environment_impl,
    validate_environment_scope,
)


def test_round4_modes_have_backward_compatible_defaults_available():
    assert "legacy_v1" in ENVIRONMENT_IMPLS
    assert "shadow_v2" in ENVIRONMENT_IMPLS
    assert "topk_v2" in ENVIRONMENT_IMPLS
    assert "legacy_all_steps" in ENVIRONMENT_SCOPES
    assert "current_context_only" in ENVIRONMENT_SCOPES


@pytest.mark.parametrize("value", ["", "TOP_K", "v2", None])
def test_invalid_environment_impl_fails_closed(value):
    with pytest.raises(ValueError):
        validate_environment_impl(value)


@pytest.mark.parametrize("value", ["", "future", "all_current", None])
def test_invalid_environment_scope_fails_closed(value):
    with pytest.raises(ValueError):
        validate_environment_scope(value)
