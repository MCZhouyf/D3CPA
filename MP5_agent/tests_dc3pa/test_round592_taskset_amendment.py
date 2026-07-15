from dc3pa.experiments.final_taskset_release import (
    TasksetAmendment,
)


def test_approved_taskset_amendment_is_deterministic():
    item = TasksetAmendment(
        approval_record_id="DC3PA-V2-ZYF-TASKSET-FINAL-003",
        approved_by="ZYF",
        approval_effective_date="2026-07-15",
        source_commit_prefix="4113559",
        source_commit="4113559efa1458126b10b6bd61976aa9f4c75b8c",
        change_type="pre-design runtime compatibility amendment",
        reason="Replace runtime-incompatible tasks before design generation.",
        removed_tasks=(
            "craft wooden pressure plate",
            "craft barrel",
            "craft carpentry table",
            "craft raw gold block",
        ),
        added_tasks=(
            "craft fence",
            "craft wooden door",
            "craft shears",
            "craft diamond axe",
        ),
        final_task_count=50,
        difficulty_counts={
            "basic": 10,
            "easy": 10,
            "medium": 10,
            "hard": 10,
            "complex": 10,
        },
        before_reconstructed_v1=True,
        before_schema_v2_design=True,
        before_blueprint=True,
        before_holdout_lock=True,
        before_formal_acquisition=True,
        outcome_selected=False,
    ).with_id()
    assert item.amendment_id == item.compute_amendment_id()


def test_taskset_amendment_rejects_prefix_without_full_commit():
    import pytest

    with pytest.raises(ValueError, match="full lowercase Git SHA"):
        TasksetAmendment(
            approval_record_id="DC3PA-V2-ZYF-TASKSET-FINAL-003",
            approved_by="ZYF",
            approval_effective_date="2026-07-15",
            source_commit_prefix="4113559",
            source_commit="4113559",
            change_type="pre-design runtime compatibility amendment",
            reason="Compatibility before design.",
            removed_tasks=tuple(sorted({
                "craft wooden pressure plate", "craft barrel",
                "craft carpentry table", "craft raw gold block",
            })),
            added_tasks=tuple(sorted({
                "craft fence", "craft wooden door", "craft shears",
                "craft diamond axe",
            })),
            final_task_count=50,
            difficulty_counts={name: 10 for name in (
                "basic", "easy", "medium", "hard", "complex"
            )},
            before_reconstructed_v1=True,
            before_schema_v2_design=True,
            before_blueprint=True,
            before_holdout_lock=True,
            before_formal_acquisition=True,
            outcome_selected=False,
        )
