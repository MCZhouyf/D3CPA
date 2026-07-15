from __future__ import annotations

import inspect

from dc3pa.reliability import holdout_evaluation


def test_holdout_module_does_not_import_or_call_fitter():
    source = inspect.getsource(holdout_evaluation)
    assert "fusion_training" not in source
    assert "fit_monotonic_logistic" not in source
    assert "TrainerConfig" not in source
