from datetime import datetime,timedelta,timezone
from dc3pa.experiments.model_epoch import ProbeObservation,open_epoch,close_epoch

def probe(at):
    return ProbeObservation(
        observed_at=at.isoformat(),requested_model="gpt-5.1",
        returned_model="gpt-5.1",profile_id="profile",
        reasoning_effort="low",purpose="planning",
        request_succeeded=True,request_text_logged=False,
        response_text_logged=False,endpoint_fingerprint="endpoint",
        client_context_fingerprint="client",probe_protocol_id="probe",
        input_tokens=1,output_tokens=1,reasoning_tokens=0,total_tokens=2)

def opened(now):
    return open_epoch(epoch_name="dry",blueprint_id="bp",
        source_commit="commit",prompt_hashes={"planner":"h"},
        model_profile_id="profile",client_context_fingerprint="client",
        endpoint_fingerprint="endpoint",schedule_id="schedule",
        start_probes=[probe(now)])

def test_valid_epoch_closes():
    now=datetime.now(timezone.utc)
    assert close_epoch(opened(now),[probe(now+timedelta(hours=1))]).status=="closed"

def test_overlong_epoch_invalidates():
    now=datetime.now(timezone.utc)
    assert close_epoch(opened(now),[probe(now+timedelta(hours=13))]).status=="invalid"
