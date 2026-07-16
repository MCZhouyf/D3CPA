import pytest

from dc3pa.experiments.controller_revision import (
    ControllerRevisionManifest,
)


def revision(**changes):
    value = dict(
        revision_name="controller-natural-fixes-and-diagnostic-fallback",
        parent_commit="da85da1",
        source_commit="new-commit",
        natural_fix_ids=(
            "reuse_placed_crafting_table",
            "propagate_underground_state",
            "stabilize_navigation_target_coordinates",
            "stop_navigation_after_target_acquired",
        ),
        natural_fix_test_ids=("a", "b", "c", "d"),
        fallback_policy_id="policy",
        fallback_approval_sha256="approval-sha",
        fallback_default_enabled=False,
        fallback_allowed_scopes=("diagnostic_dry_run",),
        fallback_forbidden_scopes=(
            "formal_acquisition",
            "dev_train",
            "dev_tune",
            "dev_holdout",
            "fusion_fitting",
            "final_evaluation",
        ),
        prompts_changed=False,
        controller_success_logic_changed=False,
        evaluator_success_logic_changed=False,
        task_specific_planner_rules_added=False,
        formal_acquisition_started=False,
    )
    value.update(changes)
    return ControllerRevisionManifest(**value)


def test_approved_revision_contract_passes():
    assert revision().with_id().revision_id


def test_prompt_or_success_logic_change_fails():
    with pytest.raises(ValueError):
        revision(prompts_changed=True)
    with pytest.raises(ValueError):
        revision(controller_success_logic_changed=True)
