from datetime import datetime,timedelta,timezone
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

def test_complete_evidence_passes():
    now=datetime.now(timezone.utc)
    epoch=open_epoch(epoch_name="dry",blueprint_id="bp",
        source_commit="commit",prompt_hashes={"p":"h"},
        model_profile_id="profile",client_context_fingerprint="client",
        endpoint_fingerprint="endpoint",schedule_id="schedule",
        start_probes=[probe(now)])
    epoch=close_epoch(epoch,[probe(now+timedelta(hours=1))])
    result=audit_readiness(blueprint_id="bp",source_commit="commit",
        migration_report={"eligible":True,"report_id":"m"},
        approval_binding={"binding_id":"binding","blueprint_id":"bp",
            "migration_report_id":"m","mutable_alias_risk_acknowledged":True},
        blueprint_validation={"eligible":True,"blueprint_id":"bp"},model_epoch=epoch,
        dry_run_audit={"eligible":True,"summary":{"expected_entry_count":6,
            "receipt_count":6}},dry_run_audit_sha256="audit",
        smoke_receipts=[receipt(1,"basic"),receipt(2,"medium"),
                        receipt(3,"complex")],
        minedojo_marker_passed=True)
    assert result.eligible

def test_process_success_cannot_replace_missing_six_entry_evidence():
    now=datetime.now(timezone.utc)
    epoch=close_epoch(open_epoch(epoch_name="dry",blueprint_id="bp",
        source_commit="commit",prompt_hashes={"p":"h"},model_profile_id="profile",
        client_context_fingerprint="client",endpoint_fingerprint="endpoint",
        schedule_id="schedule",start_probes=[probe(now)]),
        [probe(now+timedelta(hours=1))])
    result=audit_readiness(blueprint_id="bp",source_commit="commit",
        migration_report={"eligible":True,"report_id":"m"},
        approval_binding={"binding_id":"b","blueprint_id":"bp",
            "migration_report_id":"m","mutable_alias_risk_acknowledged":True},
        blueprint_validation={"eligible":True,"blueprint_id":"bp"},
        model_epoch=epoch,dry_run_audit={"eligible":True,"summary":{}},
        dry_run_audit_sha256="audit",smoke_receipts=[],minedojo_marker_passed=True)
    assert not result.eligible
