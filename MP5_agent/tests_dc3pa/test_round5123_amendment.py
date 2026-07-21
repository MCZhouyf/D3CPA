from __future__ import annotations

from dataclasses import replace

import pytest

from dc3pa.experiments.round5123_audit import build_draft_amendment
from dc3pa.experiments.round5123_contracts import (
    AcceptedUnitBinding,
    AmendedDevelopmentDatasetAcceptance,
    MixedRuntimeDevelopmentAmendment,
    ResumedReplacementLineage,
    RuntimeSegment,
    RuntimeSegmentManifest,
    assert_fusion_feature_names,
)


SEGMENT_COUNTS = (
    # train units, tune units, train rows, tune rows, successes
    (29, 9, 246, 55, 35),
    (8, 3, 141, 47, 1),
    (1, 0, 15, 0, 0),
    (1, 2, 12, 41, 0),
    (6, 1, 114, 10, 0),
)


def _allocate_records(prefix: str, count: int, units: int) -> list[tuple[str, ...]]:
    if not units:
        assert count == 0
        return []
    base, remainder = divmod(count, units)
    cursor = 0
    output = []
    for index in range(units):
        size = base + int(index < remainder)
        output.append(
            tuple(f"{prefix}-record-{value:04d}" for value in range(cursor, cursor + size))
        )
        cursor += size
    return output


def _segments() -> tuple[RuntimeSegment, ...]:
    frozen_index = 0
    segments = []
    for segment_index, (
        train_units,
        tune_units,
        train_rows,
        tune_rows,
        successes,
    ) in enumerate(SEGMENT_COUNTS):
        units = []
        role_records = {
            "dev_train": _allocate_records(
                f"s{segment_index}-train", train_rows, train_units
            ),
            "dev_tune": _allocate_records(
                f"s{segment_index}-tune", tune_rows, tune_units
            ),
        }
        success_remaining = successes
        for role, unit_count in (
            ("dev_train", train_units),
            ("dev_tune", tune_units),
        ):
            for role_index in range(unit_count):
                completed = success_remaining > 0
                success_remaining -= int(completed)
                unit_id = f"group-{frozen_index:02d}"
                units.append(
                    AcceptedUnitBinding(
                        unit_id=unit_id,
                        role=role,
                        task=f"task-{frozen_index // 3}",
                        seed=str(1000 + frozen_index),
                        run_id=f"run-{frozen_index:02d}",
                        status=(
                            "completed_success"
                            if completed
                            else "completed_scientific_failure"
                        ),
                        frozen_order_index=frozen_index,
                        legacy_sequence_index=frozen_index + 3,
                        decision_record_ids=role_records[role][role_index],
                    )
                )
                frozen_index += 1
        budget_id = f"budget-{segment_index}"
        segments.append(
            RuntimeSegment(
                source_commit=f"{segment_index + 1:040x}",
                controller_identity_sha256=f"{segment_index + 11:064x}",
                controller_component_sha256={
                    "controller.py": f"{segment_index + 21:064x}",
                    "structured_actions.py": f"{segment_index + 31:064x}",
                },
                evaluator_identity_sha256=f"{segment_index + 41:064x}",
                prompt_hash_bundle_id="a" * 64,
                paper_memory_v5_release_id="b" * 64,
                paper_memory_snapshot_root_sha256="c" * 64,
                active_taskset_release_id="d" * 64,
                formal_log_bootstrap_policy_id="e" * 64,
                execution_budget_profile_id=budget_id,
                execution_budget_profile={
                    "snapshot_id": budget_id,
                    "max_execution_attempts": 4,
                    "max_explore_steps": 60 if segment_index == 0 else 120,
                    "episode_timeout_seconds": (
                        1800 if segment_index < 2 else 3600
                    ),
                },
                accepted_units=tuple(units),
            ).with_id()
        )
    assert frozen_index == 60
    return tuple(segments)


def _lineage() -> ResumedReplacementLineage:
    return ResumedReplacementLineage(
        assignment_id="group-00",
        task="task-0",
        seed="1000",
        group_id="group-00",
        role="dev_train",
        old_failed_attempt_ids=("old-run:attempt-0",),
        old_failed_attempt_sha256=("f" * 64,),
        replacement_attempt_id="run-00:attempt-0",
        replacement_attempt_sha256="1" * 64,
        replacement_reason="Author approved a bounded retry of prior failures.",
        authorization_id="2" * 64,
        old_decision_row_count=17,
        old_rows_in_accepted_data=0,
        replacement_decision_row_count=8,
        accepted_final_attempt_count=1,
        final_status="completed_success",
    ).with_id()


def _manifest(segments: tuple[RuntimeSegment, ...] | None = None) -> RuntimeSegmentManifest:
    return RuntimeSegmentManifest(
        round5122_result_sha="3" * 40,
        assignment_manifest_id="4" * 64,
        effective_campaign_status_sha256="5" * 64,
        effective_train_jsonl_sha256="6" * 64,
        effective_tune_jsonl_sha256="7" * 64,
        paper_memory_v5_release_id="b" * 64,
        active_taskset_release_id="d" * 64,
        segments=segments or _segments(),
        replacement_lineage=_lineage(),
        failed_attempt_decision_contamination=0,
        duplicate_accepted_decision_ids=0,
        formal_memory_writes=0,
        acquisition_store_writes=0,
        evaluation_chain_calls=0,
        holdout_final_contamination=0,
        mine_sand_records=0,
        legacy_receipt_source_mismatch_count=60,
        legacy_receipt_source_commits=("8" * 40,),
        eligible=True,
        errors=(),
        warnings=("legacy receipt source is historical metadata",),
    ).with_id()


def test_manifest_assigns_all_60_units_and_681_rows_once() -> None:
    manifest = _manifest()
    units = [
        unit.unit_id for segment in manifest.segments for unit in segment.accepted_units
    ]
    rows = [record_id for segment in manifest.segments for record_id in segment.record_ids]

    assert len(manifest.segments) == 5
    assert len(units) == len(set(units)) == 60
    assert len(rows) == len(set(rows)) == 681
    assert sum(unit.role == "dev_train" for segment in manifest.segments for unit in segment.accepted_units) == 45
    assert sum(unit.task_completed for segment in manifest.segments for unit in segment.accepted_units) == 36


def test_manifest_rejects_unit_crossing_segment_boundary() -> None:
    segments = list(_segments())
    duplicate = replace(
        segments[1].accepted_units[0],
        unit_id=segments[0].accepted_units[0].unit_id,
    )
    segments[1] = replace(
        segments[1],
        accepted_units=(duplicate,) + segments[1].accepted_units[1:],
        segment_id="",
    ).with_id()

    with pytest.raises(ValueError, match="more than one segment"):
        _manifest(tuple(segments))


def test_manifest_rejects_record_crossing_segment_boundary() -> None:
    segments = list(_segments())
    duplicate_id = segments[0].accepted_units[0].decision_record_ids[0]
    unit = segments[1].accepted_units[0]
    duplicate = replace(
        unit,
        decision_record_ids=(duplicate_id,) + unit.decision_record_ids[1:],
    )
    segments[1] = replace(
        segments[1],
        accepted_units=(duplicate,) + segments[1].accepted_units[1:],
        segment_id="",
    ).with_id()

    with pytest.raises(ValueError, match="record belongs to more than one segment"):
        _manifest(tuple(segments))


def test_replacement_lineage_rejects_old_row_contamination() -> None:
    with pytest.raises(ValueError, match="contaminated"):
        replace(_lineage(), old_rows_in_accepted_data=1, lineage_id="")


def test_draft_amendment_cannot_authorize_dataset_acceptance() -> None:
    manifest = _manifest()
    draft = build_draft_amendment(manifest)

    assert draft.status == "DRAFT"
    assert not draft.author_approved
    with pytest.raises(ValueError, match="remains DRAFT"):
        AmendedDevelopmentDatasetAcceptance.from_approved_amendment(
            manifest=manifest,
            amendment=draft,
        )


def test_approved_amendment_can_freeze_acceptance() -> None:
    manifest = _manifest()
    draft = build_draft_amendment(manifest)
    approved = replace(
        draft,
        status="APPROVED",
        approved_by="ZYF",
        approved_at="2026-07-21T00:00:00Z",
        approval_statement="I approve the hash-bound mixed-runtime amendment.",
        amendment_id="",
    ).with_id()

    acceptance = AmendedDevelopmentDatasetAcceptance.from_approved_amendment(
        manifest=manifest,
        amendment=approved,
    )
    assert acceptance.eligible
    assert acceptance.accepted_unit_count == 60
    assert acceptance.accepted_decision_record_count == 681


def test_runtime_metadata_is_forbidden_as_fusion_feature() -> None:
    assert_fusion_feature_names(
        (
            "knowledge_coverage",
            "knowledge_known",
            "confidence_probability",
            "environment_probability",
        )
    )
    with pytest.raises(ValueError, match="cannot be Fusion features"):
        assert_fusion_feature_names(("knowledge_coverage", "runtime_segment_id"))


def test_draft_cannot_carry_approval_evidence() -> None:
    manifest = _manifest()
    with pytest.raises(ValueError, match="DRAFT amendment"):
        MixedRuntimeDevelopmentAmendment(
            amendment_name="draft",
            runtime_segment_manifest_id=manifest.manifest_id,
            status="DRAFT",
            controller_changes_accepted=True,
            budget_relaxations_accepted=True,
            all_final_units_and_records_accepted=True,
            no_outcome_selective_exclusions=True,
            no_unit_removed_by_outcome=True,
            runtime_segment_is_audit_metadata_only=True,
            descriptive_success_rate_is_not_homogeneous_benchmark=True,
            holdout_uses_one_frozen_final_runtime=True,
            no_runtime_change_after_candidate_freeze=True,
            approved_by="ZYF",
        )
