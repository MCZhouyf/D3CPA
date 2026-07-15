from __future__ import annotations

import pytest

from dc3pa.reliability.development_binding import CollectionOutcome


def test_excluded_group_needs_reason_and_zero_examples():
    with pytest.raises(ValueError):
        CollectionOutcome(
            group_id="g",
            role="dev_train",
            task="t",
            seed="s",
            status="technical_failure",
            usable_example_count=1,
            exclusion_reason="provider failure",
        )
    with pytest.raises(ValueError):
        CollectionOutcome(
            group_id="g",
            role="dev_train",
            task="t",
            seed="s",
            status="technical_failure",
            usable_example_count=0,
            exclusion_reason="",
        )
