import json
import hashlib
from dataclasses import replace
from datetime import datetime, timezone, timedelta

from dc3pa.experiments.acquisition_binding import (
    AcquisitionRecordProvenance,
    bind_record_metadata,
)
from dc3pa.experiments.formal_acquisition_audit import (
    audit_formal_acquisition,
)
from dc3pa.experiments.formal_acquisition_execution import (
    EntryAttemptLedger,
    FormalAcquisitionAttempt,
    FormalAcquisitionCampaign,
    TechnicalRetryPolicy,
    deterministic_attempt_id,
)


NOW = datetime.now(timezone.utc)


def make_attempt(index, success, campaign_id):
    attempt_id = deterministic_attempt_id(campaign_id, index, 0)
    status = "completed_success" if success else "completed_scientific_failure"
    failure_category = "" if success else "planner_failure"
    return FormalAcquisitionAttempt(
        attempt_id=attempt_id,
        stage6_receipt_id=f"stage6-{index}",
        campaign_id=campaign_id,
        schedule_id="schedule",
        formal_authorization_id="authorization",
        execution_tooling_binding_id="tooling",
        episode_index=index,
        group_id=f"group-{index}",
        task=f"task-{index}",
        seed=str(index + 1),
        difficulty="easy",
        method_id="single_chain_reactive_acquisition",
        attempt_index=0,
        retry_of_attempt_id="",
        source_commit="commit",
        blueprint_id="blueprint",
        bootstrap_policy_id="policy",
        bootstrap_amendment_id="amendment",
        bootstrap_data_binding_id="binding",
        prompt_hash_bundle_id="prompts",
        model_profile_id="profile",
        requested_model="gpt-5.1",
        returned_model_identities=("returned-id",),
        started_at=NOW.isoformat(),
        finished_at=(NOW + timedelta(seconds=1)).isoformat(),
        status=status,
        failure_category=failure_category,
        failure_detail="" if success else "valid scientific failure",
        pipeline_pass=True,
        task_completed=success,
        planner_calls=1,
        reflection_calls=0 if success else 1,
        evaluation_chain_calls=0,
        controller_execution_count=1,
        bootstrap_event_ids=("event",) if success else (),
        intervention_trigger_count=1 if success else 0,
        injected_log_count=2 if success else 0,
        naturally_collected_log_count=1,
        natural_completion=False,
        bootstrap_assisted_completion=success,
        acquisition_record_path=(
            f"episodes/{attempt_id}.json" if success else ""
        ),
        acquisition_record_sha256="record-sha" if success else "",
        trace_sha256=f"trace-{index}",
        formal_memory_write_count=0,
        acquisition_write_count=1 if success else 0,
        secret_scan_passed=True,
        inline_rgb_detected=False,
    ).with_id()


def test_complete_campaign_audit_binds_successful_records(tmp_path):
    retry = TechnicalRetryPolicy().with_id()
    campaign = FormalAcquisitionCampaign(
        campaign_name="formal",
        source_commit="commit",
        blueprint_id="blueprint",
        formal_authorization_id="authorization",
        execution_tooling_binding_id="tooling",
        schedule_id="schedule",
        bootstrap_policy_id="policy",
        bootstrap_amendment_id="amendment",
        bootstrap_data_binding_id="binding",
        model_profile_id="profile",
        prompt_hash_bundle_id="prompts",
        controller_identity_sha256="controller",
        evaluator_identity_sha256="evaluator",
        retry_policy_id=retry.policy_id,
    ).with_id()
    schedule = {
        "schedule_id": "schedule",
        "episode_count": 100,
        "entries": [
            {
                "episode_index": index,
                "group_id": f"group-{index}",
                "task": f"task-{index}",
                "seed": str(index + 1),
                "difficulty": "easy",
            }
            for index in range(100)
        ],
    }
    authorization = {
        "authorization_id": "authorization",
        "formal_acquisition_permitted": True,
        "acquisition_schedule_id": "schedule",
        "bootstrap_policy_id": "policy",
        "bootstrap_amendment_id": "amendment",
    }
    ledgers = []
    success_attempt = None
    for index in range(100):
        attempt = make_attempt(index, success=index == 0, campaign_id=campaign.campaign_id)
        if index == 0:
            success_attempt = attempt
        ledgers.append(
            EntryAttemptLedger(
                campaign_id=campaign.campaign_id,
                schedule_id="schedule",
                episode_index=index,
                group_id=f"group-{index}",
                task=f"task-{index}",
                seed=str(index + 1),
                retry_policy_id=retry.policy_id,
                attempts=(attempt,),
            ).with_id()
        )

    root = tmp_path / "acquisition"
    (root / "episodes").mkdir(parents=True)
    run_id = success_attempt.attempt_id
    image = root / "images" / run_id / "step.npy"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    provenance = AcquisitionRecordProvenance(
        campaign_id=campaign.campaign_id,
        schedule_id="schedule",
        formal_authorization_id="authorization",
        execution_tooling_binding_id="tooling",
        episode_index=0,
        run_id=run_id,
        attempt_id=run_id,
        stage6_receipt_id=success_attempt.stage6_receipt_id,
        source_commit="commit",
        blueprint_id="blueprint",
        bootstrap_policy_id="policy",
        bootstrap_amendment_id="amendment",
        bootstrap_data_binding_id="binding",
        prompt_hash_bundle_id="prompts",
        model_profile_id="profile",
        requested_model="gpt-5.1",
        returned_model_identities=("returned-id",),
        task="task-0",
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
        trace_sha256="trace-0",
    ).with_id()
    payload = {
        "schema_version": 1,
        "record": {
            "episode_id": run_id,
            "task_name": "task-0",
            "seed": "1",
            "plan": {"task": "task-0", "steps": []},
            "telemetry": [],
            "scene_candidates": [
                {
                    "status": "success",
                    "image_path": f"images/{run_id}/step.npy",
                    "metadata": {"bootstrap_policy_id": "policy"},
                }
            ],
            "metadata": bind_record_metadata({}, provenance),
        },
    }
    payload["record"]["scene_candidates"][0]["metadata"]["image_sha256"] = hashlib.sha256(
        image.read_bytes()
    ).hexdigest()
    record_path = root / "episodes" / f"{run_id}.json"
    record_path.write_text(json.dumps(payload), encoding="utf-8")
    success_attempt = replace(
        success_attempt,
        acquisition_record_sha256=hashlib.sha256(record_path.read_bytes()).hexdigest(),
        receipt_id="",
    ).with_id()
    ledgers[0] = replace(
        ledgers[0], attempts=(success_attempt,), ledger_id=""
    ).with_id()

    report = audit_formal_acquisition(
        campaign=campaign,
        schedule=schedule,
        authorization=authorization,
        blueprint={"final_test_exclusion": {"tasks": []}},
        retry_policy=retry,
        ledgers=ledgers,
        acquisition_root=root,
    )
    assert report.eligible
    assert report.successful_episode_count == 1
    assert report.scientific_failure_count == 99
    assert report.acquisition_record_count == 1
