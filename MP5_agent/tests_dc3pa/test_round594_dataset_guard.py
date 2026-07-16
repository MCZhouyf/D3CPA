from dc3pa.experiments.bootstrap_data_guard import audit_bootstrap_records

def test_dataset_rejects_mixed_conditions():
    records=[{"bootstrap_policy_id":"p","bootstrap_data_binding_id":"b","task_completed":True,"natural_completion":False,"bootstrap_assisted_completion":True},{"bootstrap_policy_id":"q","bootstrap_data_binding_id":"b","task_completed":False,"natural_completion":False,"bootstrap_assisted_completion":False}]
    assert not audit_bootstrap_records(records,expected_policy_id="p",expected_binding_id="b").eligible

def test_uniform_dataset_passes():
    records=[{"bootstrap_policy_id":"p","bootstrap_data_binding_id":"b","formal_bootstrap_amendment_id":"a","bootstrap_event_ids":[],"injected_log_count":0,"source_commit":"c","blueprint_id":"bp","task_completed":True,"natural_completion":True,"bootstrap_assisted_completion":False}]
    assert audit_bootstrap_records(records,expected_policy_id="p",expected_binding_id="b").eligible
