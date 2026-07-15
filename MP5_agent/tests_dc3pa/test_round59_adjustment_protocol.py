import pytest
from dc3pa.experiments.adjustment_protocol import AdjustmentRecord

def make(**changes):
    value=dict(adjustment_name="env",component=
        "environment_selection_within_preregistered_grid",
        blueprint_id_before="bp",source_commit_before="commit",
        evidence_roles=("dev_train","dev_tune"),
        evidence_artifact_sha256=("a","b"),
        previous_value={"top_k":1},proposed_value={"top_k":3},
        rationale="Pre-registered dev-tune comparison.",
        holdout_lock_exists=False,final_evaluation_started=False,
        within_preregistered_space=True,
        requires_new_blueprint_approval=False)
    value.update(changes)
    return AdjustmentRecord(**value)

def test_train_tune_adjustment_passes():
    assert make().with_id().adjustment_id

def test_protected_holdout_adjustments_fail():
    with pytest.raises(ValueError): make(component="final_seeds")
    with pytest.raises(ValueError): make(evidence_roles=("dev_holdout",))
    with pytest.raises(ValueError): make(holdout_lock_exists=True)
