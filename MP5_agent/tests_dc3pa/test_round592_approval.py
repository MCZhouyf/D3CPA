import pytest

from dc3pa.experiments.prompt_identity import build_prompt_identity_manifest
from dc3pa.experiments.round592_approval import Round592ApprovalBinding


def binding(**changes):
    payload = dict(
        approval_record_id="approval",
        approved_by="ZYF",
        approved_at="2026-07-15",
        source_commit="a" * 40,
        blueprint_id="blueprint",
        approved_blueprint_content_sha256="content",
        final_taskset_release_id="release",
        taskset_amendment_id="amendment",
        task_semantic_smoke_report_id="smoke",
        task_asset_validation_report_id="tasks",
        runtime_task_tree_sha256="tree",
        semantic_migration_report_id="migration",
        schema_v2_design_id="design",
        prompt_hashes={name: "b" * 64 for name in (
            "planner", "confidence", "evaluation", "reflexion"
        )},
        controller_source_sha256="controller-source",
        controller_config_sha256="controller-config",
        evaluator_source_sha256="evaluator-source",
        evaluator_config_sha256="evaluator-config",
        model_id="gpt-5.1",
        reasoning_effort="low",
        mutable_alias_risk_acknowledged=True,
        maximum_model_epoch_hours=12.0,
        model_epoch_policy_version="round592-12h-v1",
        execution_schedule_policy_version="round592-block-interleaved-v1",
        execution_schedule_salt="salt",
    )
    payload.update(changes)
    return Round592ApprovalBinding(**payload)


def test_prompt_identity_has_all_formal_paths():
    manifest = build_prompt_identity_manifest(source_commit="a" * 40)
    assert set(manifest["prompt_hashes"]) == {
        "planner", "confidence", "evaluation", "reflexion"
    }
    assert all(len(value) == 64 for value in manifest["prompt_hashes"].values())


def test_approval_binding_fails_without_complete_prompt_set():
    with pytest.raises(ValueError, match="four formal prompt"):
        binding(prompt_hashes={"planner": "b" * 64})


def test_approval_binding_requires_mutable_alias_acknowledgement():
    with pytest.raises(ValueError, match="alias risk"):
        binding(mutable_alias_risk_acknowledged=False)


def test_approval_binding_detects_payload_tampering():
    frozen = binding().with_id()
    with pytest.raises(ValueError, match="hash mismatch"):
        binding(binding_id=frozen.binding_id, execution_schedule_salt="changed")
