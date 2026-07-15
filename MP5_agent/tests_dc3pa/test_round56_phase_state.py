from __future__ import annotations

import pytest

from dc3pa.experiments.phase_state import ExperimentPhaseState


def test_phase_state_cannot_skip_or_start_final_test_early():
    state = ExperimentPhaseState(experiment_id="experiment", records=()).with_id()
    with pytest.raises(ValueError):
        state.advance(phase="memory_frozen", source_commit="commit")
    state = state.advance(
        phase="blueprint_frozen",
        source_commit="commit",
        artifact_ids={"blueprint_id": "experiment"},
    )
    assert state.next_phase == "dry_run_completed"
    with pytest.raises(ValueError):
        state.advance(phase="final_test_started", source_commit="commit")
