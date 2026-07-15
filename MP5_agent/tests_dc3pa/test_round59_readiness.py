from datetime import datetime,timedelta,timezone
from dc3pa.experiments.final_taskset_release import FinalTasksetRelease
from dc3pa.experiments.model_epoch import ProbeObservation,open_epoch,close_epoch
from dc3pa.experiments.readiness import SeedProviderSmokeReceipt,audit_readiness

def probe(at):
    return ProbeObservation(at.isoformat(),"gpt-5.1","gpt-5.1","profile",
        "low","planning",True,False,False,"endpoint","client","probe",
        1,1,0,2)

def receipt(i,difficulty):
    return SeedProviderSmokeReceipt(f"r{i}",f"task{i}",difficulty,str(i),str(i),
        0,True,True,"gpt-5.1",("gpt-5.1",),"profile","low",1,1,True,
        False,0,True,"trace")

def taskset():
    return FinalTasksetRelease(
        release_name="final", source_commit="commit", amendment_id="amendment",
        task_asset_validation_report_id="tasks",
        task_asset_validation_report_sha256="task-sha",
        task_semantic_smoke_report_id="semantic",
        task_semantic_smoke_report_sha256="semantic-sha",
        catalog_sha256="catalog", runtime_task_tree_sha256="tree",
        resolution_report_sha256="resolution", task_count=50,
        difficulty_counts={"basic":10,"easy":10,"medium":10,"hard":10,
                           "complex":10}, environment_construction_count=50,
        critical_task_count=6, eligible=True).with_id()

def test_complete_evidence_passes():
    now=datetime.now(timezone.utc)
    epoch=open_epoch(epoch_name="dry",blueprint_id="bp",
        source_commit="commit",prompt_hashes={"p":"h"},
        model_profile_id="profile",client_context_fingerprint="client",
        endpoint_fingerprint="endpoint",schedule_id="schedule",
        start_probes=[probe(now)])
    epoch=close_epoch(epoch,[probe(now+timedelta(hours=1))])
    final_taskset=taskset()
    result=audit_readiness(blueprint_id="bp",source_commit="commit",
        final_taskset=final_taskset,
        migration_report={"eligible":True,"report_id":"m"},
        approval_binding={"blueprint_id":"bp","semantic_migration_report_id":"m",
                          "mutable_alias_risk_acknowledged":True,"binding_id":"a",
                          "final_taskset_release_id":final_taskset.release_id,
                          "taskset_amendment_id":"amendment",
                          "task_semantic_smoke_report_id":"semantic",
                          "task_asset_validation_report_id":"tasks",
                          "runtime_task_tree_sha256":"tree"},
        task_asset_validation={"eligible":True,"report_id":"tasks",
                               "runtime_task_tree_sha256":"tree",
                               "source_commit":"commit"},
        blueprint_validation={"eligible":True,"blueprint_id":"bp",
                              "source_commit":"commit","model_profile_id":"profile"},
        model_epoch=epoch,
        dry_run_audit={"eligible":True,"summary":{"expected_entry_count":6,
                                                    "receipt_count":6}},
        dry_run_audit_sha256="audit",
        smoke_receipts=[receipt(1,"basic"),receipt(2,"medium"),
                        receipt(3,"complex")],
        minedojo_marker_passed=True)
    assert result.eligible
    assert result.final_taskset_release_id == final_taskset.release_id

def test_missing_final_taskset_binding_fails_closed():
    now=datetime.now(timezone.utc)
    epoch=open_epoch(epoch_name="dry",blueprint_id="bp",
        source_commit="commit",prompt_hashes={"p":"h"},
        model_profile_id="profile",client_context_fingerprint="client",
        endpoint_fingerprint="endpoint",schedule_id="schedule",
        start_probes=[probe(now)])
    epoch=close_epoch(epoch,[probe(now+timedelta(hours=1))])
    result=audit_readiness(blueprint_id="bp",source_commit="commit",
        final_taskset=taskset(),
        migration_report={"eligible":True,"report_id":"m"},
        approval_binding={"blueprint_id":"bp","semantic_migration_report_id":"m",
                          "mutable_alias_risk_acknowledged":True,"binding_id":"a",
                          "taskset_amendment_id":"amendment",
                          "task_semantic_smoke_report_id":"semantic",
                          "task_asset_validation_report_id":"tasks",
                          "runtime_task_tree_sha256":"tree"},
        task_asset_validation={"eligible":True,"report_id":"tasks",
                               "runtime_task_tree_sha256":"tree",
                               "source_commit":"commit"},
        blueprint_validation={"eligible":True,"blueprint_id":"bp",
                              "source_commit":"commit","model_profile_id":"profile"},
        model_epoch=epoch,
        dry_run_audit={"eligible":True,"summary":{"expected_entry_count":6,
                                                    "receipt_count":6}},
        dry_run_audit_sha256="audit",
        smoke_receipts=[receipt(1,"basic"),receipt(2,"medium"),
                        receipt(3,"complex")],
        minedojo_marker_passed=True)
    assert not result.eligible
    assert "approval binding final-taskset mismatch" in result.reasons
