import pytest
from dc3pa.experiments.formal_log_bootstrap import FormalLogBootstrapPolicy

def test_policy_covers_all_formal_scopes_and_not_semantic_smoke():
    p=FormalLogBootstrapPolicy().with_id()
    for scope in ("formal_acquisition","dev_train","dev_tune","dev_holdout","final_evaluation"):
        p.assert_scope(scope)
    with pytest.raises(ValueError):
        p.assert_scope("task_semantic_smoke")
    assert not p.counts_as_natural_task_success
    assert p.counts_as_bootstrap_condition_success
