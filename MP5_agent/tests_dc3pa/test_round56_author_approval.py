from __future__ import annotations

from dataclasses import replace

import pytest

from tests_dc3pa.round56_helpers import make_blueprint


def test_blueprint_change_invalidates_author_approval():
    blueprint = make_blueprint()
    mutated = replace(blueprint, planner_model_id="different-model", blueprint_id="")
    with pytest.raises(ValueError):
        mutated.with_id()
