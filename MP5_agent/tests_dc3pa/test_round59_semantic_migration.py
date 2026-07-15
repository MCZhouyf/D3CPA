import pytest
from dc3pa.experiments.design_migration import Round59ApprovalBinding,compare_designs

def design(schema, model_key, model):
    return {
        "schema_version": schema, "design_id": str(schema),
        "config": {
            "split_salt":"s","final_seed_salt":"f","acquisition_seed_salt":"a",
            "development_seed_salt":"d","role_salt":"r","final_seed_count":30,
            "acquisition_seeds_per_covered_task":4,
            "development_seeds_per_task":3, model_key:model,
            "source_commit":str(schema),
        },
        "task_catalog":[{"task":"log","difficulty":"basic","minimum_subgoals":1}],
        "final_test_exclusion":{"tasks":[{
            "task":"log","difficulty":"basic","goal_status":"experience_covered",
            "test_seeds":["1"],"metadata":{"minimum_subgoals":1}}]},
        "acquisition_assignments":[{"group_id":"a","task":"log","seed":"2",
            "task_kind":"experience_covered_final_goal","difficulty":"basic",
            "sequence_index":0}],
        "development_assignments":[{"group_id":"d","task":"log","seed":"3",
            "role":"dev_train","difficulty":"basic",
            "goal_status":"experience_covered"}],
        "phase_budgets":[{"phase":"dry_run","maximum_episodes":1,
            "maximum_high_level_steps_per_episode":60,
            "maximum_llm_calls_per_episode":30,
            "maximum_replans_per_episode":3,
            "timeout_seconds_per_episode":1800.0,
            "temperature":0.0,"top_p":1.0}],
        "environment_search_space":{"top_k_values":[1,3]},
        "activation_policy":{"policy_id":"id","ece_bins":10},
        "data_sufficiency_policy":{"minimum":1},
        "dry_run_group_ids":["d"],
        "model_profile":{"model":model,
            "mutable_alias_author_approved":schema==2},
    }

def test_only_model_policy_change_passes():
    result=compare_designs(
        design(1,"model_snapshot","gpt-5.1-2025-11-13"),
        design(2,"model_id","gpt-5.1"))
    assert result.eligible and result.protected_semantics_equal

def test_seed_change_fails():
    old=design(1,"model_snapshot","gpt-5.1-2025-11-13")
    new=design(2,"model_id","gpt-5.1")
    new["final_test_exclusion"]["tasks"][0]["test_seeds"]=["9"]
    assert not compare_designs(old,new).eligible

def test_new_approval_binding_requires_alias_acknowledgement():
    values=dict(blueprint_id="bp-v2",approval_record_id="approval-v2",
        approved_blueprint_content_sha256="content",migration_report_id="migration",
        reference_design_id="design-v2",model_epoch_policy_version="epoch-v1",
        interleaved_schedule_policy_version="schedule-v1",
        interleaved_schedule_salt="salt")
    with pytest.raises(ValueError):
        Round59ApprovalBinding(**values,mutable_alias_risk_acknowledged=False)
    assert Round59ApprovalBinding(**values,
        mutable_alias_risk_acknowledged=True).with_id().binding_id
