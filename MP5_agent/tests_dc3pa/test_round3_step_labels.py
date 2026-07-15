from dc3pa.reliability.confidence_observation import ModelConfidenceObservation
from dc3pa.reliability.step_labels import join_confidence_with_execution


def observation(version, step_id, index):
    return ModelConfidenceObservation(
        plan_id="plan",
        plan_version=version,
        step_id=step_id,
        step_index=index,
        request_hash=f"h-{version}-{step_id}",
        implementation="ordinal_v2",
        confidence_level="likely",
        base_probability=0.7,
        decision_probability=0.7,
        model_id="model",
        prompt_version="v1",
        prompt_sha256="prompt",
    )


def event(step_id, index, event_type, status, version=2):
    return {
        "event_type": event_type,
        "plan_id": "plan",
        "plan_version": version,
        "step_id": step_id,
        "step_index": index,
        "status": status,
        "payload": {},
    }


def test_join_labels_success_failure_censored_and_old_revision():
    plan = {"plan_id": "plan", "version": 2}
    observations = [
        observation(2, "success", 0),
        observation(2, "failure", 1),
        observation(2, "censored", 2),
        observation(1, "old", 0),
    ]
    telemetry = [
        event("success", 0, "step_finished", "success"),
        event("failure", 1, "action_finished", "failure"),
        event("censored", 2, "step_finished", "censored"),
        event("old", 0, "step_finished", "success", version=1),
    ]
    included, excluded = join_confidence_with_execution(
        episode_id="episode",
        plan=plan,
        telemetry=telemetry,
        observations=observations,
    )
    assert [(item.step_id, item.label) for item in included] == [
        ("success", 1),
        ("failure", 0),
    ]
    reasons = {item.step_id: item.reason for item in excluded}
    assert reasons["censored"] == "censored"
    assert reasons["old"] == "non_executed_plan_version"
