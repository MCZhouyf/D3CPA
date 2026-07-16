import json

from dc3pa.experiments.memory_snapshot_release import (
    MemoryBuildContract,
    ReadOnlySnapshotSmoke,
    audit_snapshot_and_build_release,
)


def test_snapshot_release_binds_acquisition_and_build(tmp_path):
    contract = MemoryBuildContract(
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
        acquisition_root_sha256="acquisition-root",
        successful_acquisition_episode_count=3,
        min_dependency_support=2,
        image_encoder_identity="mineclip-image-v1",
        text_encoder_identity="mineclip-text-v1",
        encoder_config_sha256="encoder-config",
    ).with_id()
    stats = {
        "acquisition_episodes": 3,
        "retained_dependency_edges": 2,
        "stored_scene_exemplars": 4,
        "structured_action_key_coverage": 1.0,
        "min_dependency_support": 2,
    }
    stats_path = tmp_path / "build_stats.json"
    stats_path.write_text(json.dumps(stats))
    snapshot = {
        "schema_version": 2,
        "database_sha256": "database",
        "snapshot_root_sha256": "snapshot-root",
        "acquisition_manifest_sha256": "acquisition-manifest",
        "table_counts": {
            "episodes": 3,
            "dependency_edges": 2,
            "scene_exemplars": 4,
        },
        "metadata": {
            "formal_acquisition_campaign_id": "campaign",
            "formal_acquisition_audit_id": "audit",
            "formal_authorization_id": "authorization",
            "execution_tooling_binding_id": "tooling",
            "acquisition_schedule_id": "schedule",
            "bootstrap_policy_id": "policy",
            "bootstrap_amendment_id": "amendment",
            "bootstrap_data_binding_id": "binding",
            "blueprint_id": "blueprint",
            "memory_build_contract_id": contract.contract_id,
        },
    }
    snapshot_path = tmp_path / "snapshot_manifest.json"
    snapshot_path.write_text(json.dumps(snapshot))
    import hashlib
    snapshot_sha = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    smoke = ReadOnlySnapshotSmoke(
        snapshot_manifest_sha256=snapshot_sha,
        snapshot_root_sha256_before="snapshot-root",
        snapshot_root_sha256_after="snapshot-root",
        readonly_open_passed=True,
        mutation_attempt_blocked=True,
        database_query_only=True,
        successful_episode_count=3,
        dependency_edge_count=2,
        scene_exemplar_count=4,
        eligible=True,
        errors=(),
    ).with_id()
    audit = {
        "eligible": True,
        "audit_id": "audit",
        "source_commit": "commit",
        "acquisition_root_sha256": "acquisition-root",
        "successful_episode_count": 3,
    }
    release = audit_snapshot_and_build_release(
        release_name="frozen-memory-v1",
        contract=contract,
        acquisition_audit=audit,
        snapshot_manifest_path=snapshot_path,
        build_stats_path=stats_path,
        read_only_smoke=smoke,
    )
    assert release.release_id
    assert release.successful_episode_count == 3
    assert release.scene_exemplar_count == 4
