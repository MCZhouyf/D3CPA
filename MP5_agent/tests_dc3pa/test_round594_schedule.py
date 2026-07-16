from dc3pa.experiments.formal_acquisition_schedule import build_formal_acquisition_schedule

def test_acquisition_schedule_has_100_policy_bound_entries():
    assignments=[{"group_id":f"g{i}","task":f"t{i // 4}","seed":str(i),"difficulty":"easy","sequence_index":i} for i in range(100)]
    s=build_formal_acquisition_schedule(assignments,schedule_name="a",source_commit="c",blueprint_id="b",bootstrap_policy_id="p",bootstrap_amendment_id="m")
    assert s.episode_count==100
    assert all(e.bootstrap_policy_id=="p" for e in s.entries)
    assert not s.dual_chain_enabled and not s.fusion_enabled and not s.adaptive_trigger_enabled
