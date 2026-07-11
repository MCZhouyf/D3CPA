#!/usr/bin/env python3
"""Offline Stage-5 adaptive-trigger state transition demo."""

from __future__ import annotations

import sys
from pathlib import Path

_MP5_ROOT = Path(__file__).resolve().parents[1]
if str(_MP5_ROOT) not in sys.path:
    sys.path.insert(0, str(_MP5_ROOT))

import json

from dc3pa.reliability import AdaptiveTriggerConfig
from dc3pa.trigger import AdaptiveTriggerSession


def main() -> int:
    session = AdaptiveTriggerSession(
        total_steps=10,
        config=AdaptiveTriggerConfig(
            threshold=0.8,
            initial_interval=3,
            window_size=3,
            minimum_interval=1,
            maximum_interval=6,
        ),
    )
    scripted = [
        ([0.9, 0.9, 0.9], False),
        ([0.4, 0.4, 0.4, 0.4], False),
        ([0.95, 0.95, 0.95], True),
    ]
    observations = []
    for probabilities, hard_conflict in scripted:
        window = session.next_window()
        assert window is not None
        assert len(probabilities) == len(window.step_indices)
        observations.append(
            session.observe(probabilities, hard_conflict=hard_conflict).to_dict()
        )
    assert [item["next_interval"] for item in observations] == [4, 3, 1]
    assert session.finished
    print(json.dumps(observations, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
