import json
from dataclasses import replace

import pytest

from dc3pa.experiments.final_taskset_release import (
    FinalTasksetRelease,
    TaskSemanticSmokeReport,
    TasksetAmendment,
    build_final_taskset_release,
)


def amendment():
    source_commit = "4113559efa1458126b10b6bd61976aa9f4c75b8c"
    return TasksetAmendment(
        approval_record_id="DC3PA-V2-ZYF-TASKSET-FINAL-003",
        approved_by="ZYF",
        approval_effective_date="2026-07-15",
        source_commit_prefix="4113559",
        source_commit=source_commit,
        change_type="pre-design runtime compatibility amendment",
        reason="Compatibility only.",
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
            "basic": 10, "easy": 10, "medium": 10,
            "hard": 10, "complex": 10,
        },
        before_reconstructed_v1=True,
        before_schema_v2_design=True,
        before_blueprint=True,
        before_holdout_lock=True,
        before_formal_acquisition=True,
        outcome_selected=False,
    ).with_id()


def test_final_taskset_release_binds_reports(tmp_path):
    source_commit = "4113559efa1458126b10b6bd61976aa9f4c75b8c"
    task_report = {
        "eligible": True,
        "source_commit": source_commit,
        "report_id": "task-report",
        "task_count": 50,
        "difficulty_counts": {
            "basic": 10, "easy": 10, "medium": 10,
            "hard": 10, "complex": 10,
        },
        "environment_construction_count": 50,
        "catalog_sha256": "catalog",
        "runtime_task_tree_sha256": "runtime-tree",
    }
    smoke = TaskSemanticSmokeReport(
        source_commit=source_commit,
        task_asset_validation_report_id="task-report",
        required_tasks=(
            "craft fence", "craft wooden door", "craft shears",
            "craft diamond axe", "mine coal ore", "mine iron ore",
        ),
        receipt_ids=tuple(f"r{i}" for i in range(6)),
        receipt_count=6,
        eligible=True,
        errors=(),
        warnings=(),
    ).with_id()
    task_path = tmp_path / "task.json"
    smoke_path = tmp_path / "smoke.json"
    resolution_path = tmp_path / "resolution.json"
    task_path.write_text(json.dumps(task_report))
    smoke_path.write_text(json.dumps(smoke.to_dict()))
    resolution_path.write_text("{}")
    release = build_final_taskset_release(
        release_name="final-taskset-v3",
        source_commit=source_commit,
        amendment=amendment(),
        task_asset_validation=task_report,
        task_asset_validation_path=task_path,
        semantic_smoke=smoke,
        semantic_smoke_path=smoke_path,
        resolution_report_path=resolution_path,
    )
    assert release.release_id
    assert release.environment_construction_count == 50


def test_taskset_amendment_reuse_requires_unchanged_catalog_and_revision(tmp_path):
    old_source = amendment().source_commit
    new_source = "a" * 40
    task_report = {
        "eligible": True,
        "source_commit": new_source,
        "report_id": "new-task-report",
        "task_count": 50,
        "difficulty_counts": {
            "basic": 10, "easy": 10, "medium": 10,
            "hard": 10, "complex": 10,
        },
        "environment_construction_count": 50,
        "catalog_sha256": "same-catalog",
        "runtime_task_tree_sha256": "same-tree",
    }
    smoke = TaskSemanticSmokeReport(
        source_commit=new_source,
        task_asset_validation_report_id="new-task-report",
        required_tasks=(
            "craft fence", "craft wooden door", "craft shears",
            "craft diamond axe", "mine coal ore", "mine iron ore",
        ),
        receipt_ids=tuple(f"new-r{i}" for i in range(6)),
        receipt_count=6,
        eligible=True,
        errors=(),
        warnings=(),
    ).with_id()
    prior = FinalTasksetRelease(
        release_name="prior",
        source_commit=old_source,
        amendment_id=amendment().amendment_id,
        task_asset_validation_report_id="old-tasks",
        task_asset_validation_report_sha256="old-tasks-sha",
        task_semantic_smoke_report_id="old-smoke",
        task_semantic_smoke_report_sha256="old-smoke-sha",
        catalog_sha256="same-catalog",
        runtime_task_tree_sha256="same-tree",
        resolution_report_sha256="old-resolution",
        task_count=50,
        difficulty_counts=task_report["difficulty_counts"],
        environment_construction_count=50,
        critical_task_count=6,
        eligible=True,
    ).with_id()
    task_path = tmp_path / "new-task.json"
    smoke_path = tmp_path / "new-smoke.json"
    resolution_path = tmp_path / "new-resolution.json"
    task_path.write_text(json.dumps(task_report))
    smoke_path.write_text(json.dumps(smoke.to_dict()))
    resolution_path.write_text("{}")

    release = build_final_taskset_release(
        release_name="round593-taskset",
        source_commit=new_source,
        amendment=amendment(),
        task_asset_validation=task_report,
        task_asset_validation_path=task_path,
        semantic_smoke=smoke,
        semantic_smoke_path=smoke_path,
        resolution_report_path=resolution_path,
        prior_taskset_release=prior,
        controller_revision={"source_commit": new_source},
    )
    assert release.source_commit == new_source
    assert release.catalog_sha256 == prior.catalog_sha256
    drifted_prior = replace(
        prior, catalog_sha256="drifted-catalog", release_id=""
    ).with_id()
    with pytest.raises(ValueError, match="catalog hash"):
        build_final_taskset_release(
            release_name="round593-taskset",
            source_commit=new_source,
            amendment=amendment(),
            task_asset_validation=task_report,
            task_asset_validation_path=task_path,
            semantic_smoke=smoke,
            semantic_smoke_path=smoke_path,
            resolution_report_path=resolution_path,
            prior_taskset_release=drifted_prior,
            controller_revision={"source_commit": new_source},
        )
