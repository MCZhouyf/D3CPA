from datetime import datetime, timezone

import pytest

from dc3pa.contracts import Action, Plan, PlanStep
from dc3pa.experiments.bootstrap_data_guard import (
    assert_bootstrap_snapshot_binding,
)
from dc3pa.experiments.formal_log_bootstrap import (
    FormalLogBootstrapPolicy,
    FormalLogBootstrapSession,
    mark_formal_bootstrap_output_root,
    planner_declared_log_requirement,
)
from dc3pa.experiments.model_epoch import (
    EpochPolicy,
    ProbeObservation,
    open_epoch,
)
from dc3pa.integration.controller import LegacyControllerAdapter


def _plan(*steps):
    return Plan(task="craft chest", plan_id="plan-1", version=2, steps=list(steps))


def _mine_log(times):
    return PlanStep(
        times=times,
        actions=[Action(name="mine", args={"obj": "log", "tool": ""})],
    )


def test_planner_log_target_uses_only_explicit_acquisition_declarations():
    craft_only = PlanStep(
        times=1,
        actions=[
            Action(
                name="craft",
                args={
                    "obj": {"planks": 4},
                    "materials": {"log": 99},
                    "platform": "",
                },
            )
        ],
    )
    assert planner_declared_log_requirement(_plan(_mine_log(2), craft_only)) == 2
    assert planner_declared_log_requirement(_plan(craft_only)) == 0


def test_planner_log_target_accepts_minecraft_log_item_names():
    oak_log = PlanStep(
        times=2,
        actions=[Action(name="mine", args={"obj": "oak_log", "tool": ""})],
    )
    assert planner_declared_log_requirement(_plan(oak_log)) == 2


def test_formal_session_injects_declared_shortfall_and_binds_plan_version():
    policy = FormalLogBootstrapPolicy().with_id()
    session = FormalLogBootstrapSession(
        policy=policy,
        amendment_id="amendment",
        source_commit="commit",
        blueprint_id="blueprint",
        scope="formal_acquisition",
        method_id="single_chain_reactive_acquisition",
        task="craft chest",
        seed="17",
    )
    session.bind_plan(_plan(_mine_log(3)))

    def apply_inventory(requested):
        assert requested == {"cobblestone": 4, "log": 3}
        return requested

    event = session.intervene(
        target_item="log",
        target_quantity=session.target_quantity(999),
        inventory_before={"log": 1, "cobblestone": 4},
        naturally_collected_count=1,
        natural_collection_attempts=3,
        bounded_attempts_exhausted=True,
        apply_inventory=apply_inventory,
    )
    assert event.plan_id == "plan-1"
    assert event.plan_version == 2
    assert event.injected_logs == 2
    assert session.record_metadata(task_completed=True)[
        "bootstrap_assisted_completion"
    ]


def test_output_and_snapshot_bindings_fail_closed(tmp_path):
    marker = mark_formal_bootstrap_output_root(
        tmp_path,
        policy_id="policy",
        amendment_id="amendment",
        blueprint_id="blueprint",
        scope="dev_train",
        method_id="method",
    )
    assert marker.is_file()
    metadata = {
        "bootstrap_policy_id": "policy",
        "formal_bootstrap_amendment_id": "amendment",
        "bootstrap_data_binding_id": "binding",
    }
    assert_bootstrap_snapshot_binding(
        metadata,
        expected_policy_id="policy",
        expected_amendment_id="amendment",
        expected_binding_id="binding",
    )
    with pytest.raises(ValueError, match="snapshot bootstrap binding mismatch"):
        assert_bootstrap_snapshot_binding(
            metadata,
            expected_policy_id="other",
            expected_amendment_id="amendment",
            expected_binding_id="binding",
        )


def _probe(returned_model):
    return ProbeObservation(
        observed_at=datetime.now(timezone.utc).isoformat(),
        requested_model="gpt-5.1",
        returned_model=returned_model,
        profile_id="profile",
        reasoning_effort="low",
        purpose="probe",
        request_succeeded=True,
        request_text_logged=False,
        response_text_logged=False,
        endpoint_fingerprint="endpoint",
        client_context_fingerprint="client",
        probe_protocol_id="protocol",
        input_tokens=1,
        output_tokens=1,
        reasoning_tokens=0,
        total_tokens=2,
        provider_model_alias_policy_id="alias-policy",
    )


def test_model_epoch_rejects_returned_identity_drift():
    policy = EpochPolicy(
        require_returned_model_match=False,
        provider_model_alias_policy_id="alias-policy",
    )
    with pytest.raises(ValueError, match="changed within epoch"):
        open_epoch(
            epoch_name="epoch",
            blueprint_id="blueprint",
            source_commit="commit",
            prompt_hashes={"planner": "hash"},
            model_profile_id="profile",
            client_context_fingerprint="client",
            endpoint_fingerprint="endpoint",
            schedule_id="schedule",
            start_probes=(_probe("returned-a"), _probe("returned-b")),
            policy=policy,
        )


def test_legacy_adapter_binds_exact_plan_before_controller_execution():
    policy = FormalLogBootstrapPolicy().with_id()
    session = FormalLogBootstrapSession(
        policy=policy,
        amendment_id="amendment",
        source_commit="commit",
        blueprint_id="blueprint",
        scope="formal_acquisition",
        method_id="method",
        task="craft chest",
        seed="17",
    )

    class LegacyController:
        _dc3pa_log_fallback_session = session

        def check_and_execute_workflow(self, **_kwargs):
            assert session.target_quantity(999) == 2
            return {"success": True}, False

    result = LegacyControllerAdapter(LegacyController()).execute(
        object(), _plan(_mine_log(2)), {"task": "craft chest"}, False
    )
    assert result.success
