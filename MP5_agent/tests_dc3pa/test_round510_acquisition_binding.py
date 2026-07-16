import json

import numpy as np

from dc3pa.experiments.acquisition_binding import (
    AcquisitionRecordProvenance,
    bind_record_metadata,
    validate_acquisition_payload,
    finalize_staged_acquisition,
)
from dc3pa.memory.acquisition import (
    AcquisitionStore,
    LocalSceneCandidate,
    SuccessfulTrajectoryRecord,
)


def provenance(taskset_amendment_id=""):
    return AcquisitionRecordProvenance(
        campaign_id="campaign",
        schedule_id="schedule",
        formal_authorization_id="authorization",
        execution_tooling_binding_id="tooling",
        episode_index=0,
        run_id="run",
        attempt_id="run",
        stage6_receipt_id="receipt",
        source_commit="commit",
        blueprint_id="blueprint",
        bootstrap_policy_id="policy",
        bootstrap_amendment_id="amendment",
        bootstrap_data_binding_id="binding",
        prompt_hash_bundle_id="prompts",
        model_profile_id="profile",
        requested_model="gpt-5.1",
        returned_model_identities=("returned",),
        task="craft chest",
        seed="1",
        difficulty="easy",
        method_id="single_chain_reactive_acquisition",
        bootstrap_event_ids=("event",),
        injected_log_count=2,
        naturally_collected_log_count=1,
        natural_completion=False,
        bootstrap_assisted_completion=True,
        planner_calls=1,
        reflection_calls=0,
        evaluation_chain_calls=0,
        trace_sha256="trace",
        taskset_amendment_id=taskset_amendment_id,
    ).with_id()


def test_successful_payload_requires_formal_provenance():
    p = provenance()
    payload = {
        "schema_version": 1,
        "record": {
            "episode_id": "run",
            "task_name": "craft chest",
            "seed": "1",
            "plan": {"task": "craft chest", "steps": []},
            "telemetry": [],
            "scene_candidates": [
                {
                    "status": "success",
                    "image_path": "images/run/step.npy",
                    "metadata": {"bootstrap_policy_id": "policy"},
                }
            ],
            "metadata": bind_record_metadata({}, p),
        },
    }
    result = validate_acquisition_payload(
        payload,
        expected_campaign_id="campaign",
        expected_schedule_id="schedule",
        expected_authorization_id="authorization",
        expected_tooling_binding_id="tooling",
        expected_policy_id="policy",
        expected_amendment_id="amendment",
        expected_binding_id="binding",
        expected_source_commit="commit",
        expected_blueprint_id="blueprint",
    )
    assert result.provenance_id == p.provenance_id


def test_successful_payload_binds_taskset_amendment():
    p = provenance("taskset-v2")
    payload = {
        "schema_version": 1,
        "record": {
            "episode_id": "run",
            "task_name": "craft chest",
            "seed": "1",
            "plan": {"task": "craft chest", "steps": []},
            "telemetry": [],
            "scene_candidates": [],
            "metadata": bind_record_metadata({}, p),
        },
    }
    result = validate_acquisition_payload(
        payload,
        expected_campaign_id="campaign",
        expected_schedule_id="schedule",
        expected_authorization_id="authorization",
        expected_tooling_binding_id="tooling",
        expected_policy_id="policy",
        expected_amendment_id="amendment",
        expected_binding_id="binding",
        expected_source_commit="commit",
        expected_blueprint_id="blueprint",
        expected_taskset_amendment_id="taskset-v2",
    )
    assert result.taskset_amendment_id == "taskset-v2"


def test_staged_success_promotes_idempotently_without_overwrite(tmp_path):
    p = provenance()
    staging = AcquisitionStore(tmp_path / "staging")
    image = staging.write_rgb_array(
        episode_id="run", step_id="step", action_index=0,
        rgb=np.zeros((2, 2, 3), dtype=np.uint8),
    )
    record = SuccessfulTrajectoryRecord(
        episode_id="run",
        task_name="craft chest",
        seed="1",
        plan={"task": "craft chest", "steps": []},
        telemetry=(),
        scene_candidates=(LocalSceneCandidate(
            episode_id="run", task_name="craft chest", plan_id="p",
            plan_version=1, step_id="step", step_index=0, action_index=0,
            local_subgoal="collect", action={"name": "mine"},
            image_path=image,
        ),),
    )
    staging.commit_success(record)
    first, hashes = finalize_staged_acquisition(
        staging_root=staging.root,
        final_root=tmp_path / "final",
        episode_id="run",
        provenance=p,
    )
    second, repeated_hashes = finalize_staged_acquisition(
        staging_root=staging.root,
        final_root=tmp_path / "final",
        episode_id="run",
        provenance=p,
    )
    assert first == second
    assert hashes == repeated_hashes
