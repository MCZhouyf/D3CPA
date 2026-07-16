import pytest

from dc3pa.experiments.memory_snapshot_release import MemoryBuildContract


def contract(**changes):
    values = dict(
        contract_name="memory-v1",
        source_commit="commit",
        formal_acquisition_campaign_id="campaign",
        formal_acquisition_audit_id="audit",
        formal_authorization_id="authorization",
        execution_tooling_binding_id="tooling",
        acquisition_schedule_id="schedule",
        bootstrap_policy_id="policy",
        bootstrap_amendment_id="amendment",
        bootstrap_data_binding_id="binding",
        blueprint_id="blueprint",
        acquisition_root_sha256="root",
        successful_acquisition_episode_count=10,
        min_dependency_support=2,
        image_encoder_identity="image",
        text_encoder_identity="text",
        encoder_config_sha256="config",
    )
    values.update(changes)
    return MemoryBuildContract(**values)


def test_memory_contract_requires_offline_dependencies_and_real_encoders():
    item = contract().with_id()
    assert item.dependency_extraction_offline_only
    assert item.require_structured_action_key_coverage
    assert item.minimum_structured_action_key_coverage == 0.95
    assert item.image_encoder_identity == "image"
    assert item.text_encoder_identity == "text"


def test_invalid_dependency_support_fails():
    with pytest.raises(ValueError):
        contract(min_dependency_support=0)
