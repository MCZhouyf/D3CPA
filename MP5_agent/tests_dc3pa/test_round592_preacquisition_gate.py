from dc3pa.experiments.final_taskset_release import FinalTasksetRelease
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from dc3pa.experiments.model_epoch import (
    ProbeObservation,
    close_epoch,
    open_epoch,
)
from dc3pa.experiments.phase_state import ExperimentPhaseState
from dc3pa.experiments.preacquisition_gate import (
    advance_round592_dry_run_phase,
    audit_preacquisition_gate,
)


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


def closed_epoch():
    now = datetime.now(timezone.utc)
    probe = ProbeObservation(
        now.isoformat(), "gpt-5.1", "gpt-5.1", "profile", "low",
        "planning", True, False, False, "endpoint", "client", "probe",
        1, 1, 0, 2,
    )
    opened = open_epoch(
        epoch_name="dry", blueprint_id="blueprint", source_commit="commit",
        prompt_hashes={"planner": "hash"}, model_profile_id="profile",
        client_context_fingerprint="client",
        endpoint_fingerprint="endpoint", schedule_id="schedule",
        start_probes=[probe],
    )
    return close_epoch(
        opened,
        [replace(probe, observed_at=(now + timedelta(hours=1)).isoformat())],
    )


def test_phase_advance_requires_permitted_meta_gate():
    taskset = release()
    epoch = closed_epoch()
    state = ExperimentPhaseState("blueprint", ()).with_id().advance(
        phase="blueprint_frozen", source_commit="commit"
    )
    gate = {
        "gate_id": "gate", "formal_acquisition_permitted": False,
        "phase_can_advance": False, "reasons": ["blocked"],
    }
    with pytest.raises(ValueError, match="does not permit"):
        advance_round592_dry_run_phase(
            state=state, source_commit="commit", gate=gate,
            readiness={"eligible": True}, model_epoch=epoch,
            final_taskset=taskset,
            migration_report={"report_id": "migration"},
        )


def test_phase_advance_binds_all_round592_evidence():
    taskset = release()
    epoch = closed_epoch()
    state = ExperimentPhaseState("blueprint", ()).with_id().advance(
        phase="blueprint_frozen", source_commit="commit"
    )
    gate = {
        "gate_id": "gate", "formal_acquisition_permitted": True,
        "phase_can_advance": True, "reasons": [],
        "source_commit": "commit", "blueprint_id": "blueprint",
        "acquisition_readiness_id": "readiness",
        "closed_model_epoch_id": epoch.epoch_id,
        "final_taskset_release_id": taskset.release_id,
        "semantic_migration_report_id": "migration",
    }
    advanced = advance_round592_dry_run_phase(
        state=state, source_commit="commit", gate=gate,
        readiness={
            "eligible": True, "readiness_id": "readiness",
            "final_taskset_release_id": taskset.release_id,
        },
        model_epoch=epoch, final_taskset=taskset,
        migration_report={"report_id": "migration"},
    )
    artifacts = advanced.records[-1].artifact_ids
    assert set(artifacts) == {
        "preacquisition_gate_id", "acquisition_readiness_id",
        "closed_model_epoch_id", "blueprint_id",
        "final_taskset_release_id", "semantic_migration_report_id",
    }
