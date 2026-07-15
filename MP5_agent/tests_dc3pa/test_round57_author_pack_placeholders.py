from __future__ import annotations

import pytest

from dc3pa.experiments.author_decisions import (
    contains_placeholder,
    require_final_text,
)


@pytest.mark.parametrize(
    "value",
    ["", "REPLACE", "pending", "TBD_model", "example_only task", "TODO"],
)
def test_placeholders_are_rejected(value):
    assert contains_placeholder(value)
    with pytest.raises(ValueError):
        require_final_text(value, "field")


def test_real_value_is_accepted():
    assert require_final_text("gpt-4-turbo-2024-04-09", "model")
