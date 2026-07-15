import json

from dc3pa.experiments.final_taskset_release import (
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
