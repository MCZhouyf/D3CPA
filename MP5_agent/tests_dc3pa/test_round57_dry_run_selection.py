from __future__ import annotations

import pytest

from dc3pa.experiments.dry_run import build_dry_run_campaign
from tests_dc3pa.round56_helpers import make_blueprint


def test_dry_run_only_accepts_dev_train_groups():
    blueprint = make_blueprint()
    campaign = build_dry_run_campaign(
        blueprint=blueprint,
        selected_group_ids=["train"],
        source_commit="commit",
        require_confidence_observations=False,
        require_execution_label_joins=False,
    )
    assert campaign.entries[0].group_id == "train"
    assert campaign.entries[0].excluded_from_formal_fitting

    with pytest.raises(ValueError):
        build_dry_run_campaign(
            blueprint=blueprint,
            selected_group_ids=["tune"],
            source_commit="commit",
        )
