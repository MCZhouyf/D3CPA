import pytest
from dc3pa.experiments.formal_log_bootstrap import FormalLogBootstrapEvent,FormalBootstrapRunReceipt

def event(**changes):
    value=dict(policy_id="p",scope="formal_acquisition",method_id="single_chain_reactive_acquisition",task="craft chest",seed="1",plan_id="plan",plan_version=1,event_index=0,target_source="planner_declared_log_requirement",planner_declared_log_requirement=4,inventory_before=1,natural_collection_attempts=3,naturally_collected_logs=1,bounded_attempts_exhausted=True,injected_logs=3,inventory_after=4,intervention_triggered=True,source_commit="c")
    value.update(changes); return FormalLogBootstrapEvent(**value)

def test_event_injects_exact_shortfall():
    assert event().with_id().event_id
    with pytest.raises(ValueError): event(injected_logs=4,inventory_after=5)

def test_receipt_records_identity_variation_without_failing_pipeline():
    e=event().with_id()
    r=FormalBootstrapRunReceipt(run_id="r",readiness_campaign_id="",policy_id="p",bootstrap_amendment_id="a",bootstrap_data_binding_id="bnd",scope="formal_acquisition",method_id="single_chain_reactive_acquisition",task="craft chest",seed="1",source_commit="c",blueprint_id="b",model_profile_id="m",requested_model="gpt-5.1",returned_model_identities=("gpt-4o-iri","gpt-4o"),returned_identity_stable_within_run=False,process_exit_code=0,pipeline_pass=True,task_completed=True,planner_calls=1,reflection_calls=1,evaluation_chain_calls=0,controller_execution_count=1,event_ids=(e.event_id,),intervention_trigger_count=1,total_injected_logs=3,total_naturally_collected_logs=1,natural_completion=False,bootstrap_assisted_completion=True,formal_memory_write_count=1,acquisition_write_count=1,provider_call_contract_passed=True,output_root_guard_passed=True,trace_sha256="t")
    assert r.with_id().receipt_id
