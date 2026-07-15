from dc3pa.experiments.final_taskset_release import FinalTasksetRelease
from dc3pa.experiments.preacquisition_gate import audit_preacquisition_gate


def release():
    return FinalTasksetRelease(
        release_name="final",
        source_commit="commit",
        amendment_id="amendment",
        task_asset_validation_report_id="task-report",
        task_asset_validation_report_sha256="task-sha",
        task_semantic_smoke_report_id="semantic",
        task_semantic_smoke_report_sha256="semantic-sha",
        catalog_sha256="catalog",
        runtime_task_tree_sha256="runtime-tree",
        resolution_report_sha256="resolution",
        task_count=50,
        difficulty_counts={
            "basic": 10, "easy": 10, "medium": 10,
            "hard": 10, "complex": 10,
        },
        environment_construction_count=50,
        critical_task_count=6,
        eligible=True,
    ).with_id()


def test_complete_preacquisition_bindings_permit_phase():
    taskset = release()
    result = audit_preacquisition_gate(
        source_commit="commit",
        final_taskset=taskset,
        migration_report={"eligible": True, "report_id": "migration"},
        approval_binding={
            "binding_id": "approval",
            "blueprint_id": "blueprint",
            "final_taskset_release_id": taskset.release_id,
            "taskset_amendment_id": taskset.amendment_id,
            "task_semantic_smoke_report_id": (
                taskset.task_semantic_smoke_report_id
            ),
            "semantic_migration_report_id": "migration",
        },
        blueprint_validation={
            "eligible": True,
            "report_id": "blueprint-validation",
            "blueprint_id": "blueprint",
        },
        closed_model_epoch={"status": "closed", "epoch_id": "epoch"},
        acquisition_readiness={
            "eligible": True,
            "readiness_id": "readiness",
            "source_commit": "commit",
            "task_asset_validation_report_id": "task-report",
            "final_taskset_release_id": taskset.release_id,
            "model_epoch_id": "epoch",
        },
    )
    assert result.formal_acquisition_permitted


def test_missing_taskset_binding_fails():
    taskset = release()
    result = audit_preacquisition_gate(
        source_commit="commit",
        final_taskset=taskset,
        migration_report={"eligible": True, "report_id": "migration"},
        approval_binding={
            "binding_id": "approval",
            "blueprint_id": "blueprint",
            "taskset_amendment_id": taskset.amendment_id,
            "task_semantic_smoke_report_id": (
                taskset.task_semantic_smoke_report_id
            ),
            "semantic_migration_report_id": "migration",
        },
        blueprint_validation={
            "eligible": True,
            "report_id": "blueprint-validation",
            "blueprint_id": "blueprint",
        },
        closed_model_epoch={"status": "closed", "epoch_id": "epoch"},
        acquisition_readiness={
            "eligible": True,
            "readiness_id": "readiness",
            "source_commit": "commit",
            "task_asset_validation_report_id": "task-report",
            "final_taskset_release_id": taskset.release_id,
            "model_epoch_id": "epoch",
        },
    )
    assert not result.formal_acquisition_permitted
