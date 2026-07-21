from __future__ import annotations

from collections import Counter

import pytest

from scripts_dc3pa.create_round5125_replacement_holdout import (
    build_replacement_assignments,
)
from scripts_dc3pa.freeze_round5124_holdout_runtime import (
    _required_protocol_id,
)


def _reference_design():
    assignments = []
    seed = 100
    for difficulty in ("basic", "easy", "medium", "hard", "complex"):
        for role in ("dev_train", "dev_tune", "dev_holdout"):
            task = f"{difficulty}-{role}"
            count = 3
            for index in range(count):
                assignments.append(
                    {
                        "difficulty": difficulty,
                        "group_id": f"{role}:{task}:{index}",
                        "role": role,
                        "seed": str(seed),
                        "task": task,
                    }
                )
                seed += 1
    return {"development_assignments": assignments}


def test_replacement_holdout_preserves_strata_and_replaces_all_seeds():
    reference = _reference_design()
    replacements = build_replacement_assignments(
        reference,
        source_commit="a" * 40,
    )
    old_seeds = {
        item["seed"] for item in reference["development_assignments"]
    }

    assert len(replacements) == 15
    assert Counter(item["difficulty"] for item in replacements) == {
        "basic": 3,
        "easy": 3,
        "medium": 3,
        "hard": 3,
        "complex": 3,
    }
    assert len({item["task"] for item in replacements}) == 5
    assert len({item["seed"] for item in replacements}) == 15
    assert not ({item["seed"] for item in replacements} & old_seeds)
    assert [item["sequence_index"] for item in replacements] == list(range(15))


def test_replacement_holdout_is_deterministic_for_frozen_source():
    reference = _reference_design()
    first = build_replacement_assignments(reference, source_commit="b" * 40)
    second = build_replacement_assignments(reference, source_commit="b" * 40)
    assert first == second


def test_holdout_freeze_rejects_unfrozen_protocol_before_writes():
    with pytest.raises(ValueError, match="no frozen protocol ID"):
        _required_protocol_id({"development_assignments": []})
    assert _required_protocol_id({"protocol_id": "frozen"}) == "frozen"
