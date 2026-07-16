from dc3pa.experiments.formal_bootstrap_authorization import FormalBootstrapReadinessEvidence,audit_formal_bootstrap_authorization,audit_formal_bootstrap_readiness
from dc3pa.experiments.formal_log_bootstrap import FormalBootstrapRunReceipt

def test_complete_new_condition_authorizes_formal_acquisition():
    r=FormalBootstrapReadinessEvidence(readiness_campaign_id="r",source_commit="c",blueprint_id="b",bootstrap_policy_id="p",bootstrap_amendment_id="m",run_receipt_ids=tuple(str(i) for i in range(6)),expected_run_count=6,pipeline_pass_count=6,task_completed_count=4,intervention_trigger_count=6,total_injected_logs=11,returned_model_identities=("returned-a","returned-b"),returned_identity_stable_within_epoch=False,requested_returned_equality_required=False,model_epoch_id="e",task_seed_match_count=6,provider_call_contract_passed=True,no_formal_memory_writes=True,no_acquisition_writes=True,eligible=True,errors=()).with_id()
    result=audit_formal_bootstrap_authorization(source_commit="c",policy={"policy_id":"p","enabled_for_all_formal_scopes":True},amendment={"amendment_id":"m","formal_log_bootstrap_policy_id":"p","source_commit":"db8778ddcaf4655ee86cf50c9d0a9919a832d7d3","old_preacquisition_gate_superseded":True,"returned_model_identity_policy":"record_only_no_stability_requirement"},blueprint_validation={"eligible":True,"blueprint_id":"b","report_id":"bv"},approval_binding={"blueprint_id":"b","source_commit":"c","zyf_approval_sha256":"02aa04d0bdf45d5e7dad1afb3f6ff295a687a91707c693e9d5dd9e1f040fffab","model_identity_approval_sha256":"26ec20eb43aab76a8a9ba61a5072f11d24f1a2981a698acd68edf3b56583f6d0","formal_log_bootstrap_policy_id":"p","formal_bootstrap_amendment_id":"m","binding_id":"ab","development_records_bootstrap_metadata":True,"final_results_report_natural_and_assisted_separately":True},taskset_release={"eligible":True,"release_id":"ts"},migration_report={"eligible":True,"report_id":"mr"},readiness=r,acquisition_schedule={"schedule_id":"s","episode_count":100,"source_commit":"c","bootstrap_policy_id":"p","bootstrap_amendment_id":"m","blueprint_id":"b","all_methods_share_policy":True,"memory_records_bootstrap_metadata":True})
    assert result.formal_acquisition_permitted

def test_readiness_records_but_does_not_gate_identity_variation():
    receipts=[]
    for index in range(6):
        identities=("gpt-4o",) if index < 5 else ("gpt-4o-iri","gpt-4o")
        receipts.append(FormalBootstrapRunReceipt(
            run_id=f"run-{index}",readiness_campaign_id="campaign",
            policy_id="policy",bootstrap_amendment_id="amendment",
            bootstrap_data_binding_id="binding",scope="bootstrap_readiness_dry_run",
            method_id="reasoning_only_single_chain",task=f"task-{index}",seed=str(index),
            source_commit="commit",blueprint_id="blueprint",model_profile_id="profile",
            requested_model="gpt-5.1",returned_model_identities=identities,
            returned_identity_stable_within_run=len(set(identities))==1,
            process_exit_code=0,pipeline_pass=True,task_completed=False,
            planner_calls=1,reflection_calls=int(index==5),evaluation_chain_calls=0,
            controller_execution_count=1,event_ids=(),intervention_trigger_count=0,
            total_injected_logs=0,total_naturally_collected_logs=0,
            natural_completion=False,bootstrap_assisted_completion=False,
            formal_memory_write_count=0,acquisition_write_count=0,
            provider_call_contract_passed=True,output_root_guard_passed=True,
            trace_sha256=f"trace-{index}").with_id().to_dict())
    evidence=audit_formal_bootstrap_readiness(
        receipts,readiness_campaign_id="campaign",source_commit="commit",
        blueprint_id="blueprint",bootstrap_policy_id="policy",
        bootstrap_amendment_id="amendment",model_epoch_id="epoch")
    assert evidence.eligible
    assert not evidence.returned_identity_stable_within_epoch
    assert evidence.returned_model_identities == ("gpt-4o", "gpt-4o-iri")
