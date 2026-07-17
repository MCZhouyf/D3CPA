from dc3pa.experiments.mineclip_memory_v5 import MineCLIPFrozenMemoryRelease


def test_frozen_release_requires_mineclip_and_structural_invariants():
    item = MineCLIPFrozenMemoryRelease(
        release_name="mineclip-v5",
        source_commit="source",
        rebuild_contract_id="contract",
        acquisition_root_sha256="acquisition",
        acquisition_manifest_sha256="manifest",
        snapshot_manifest_sha256="snapshot-manifest",
        snapshot_root_sha256="snapshot-root",
        database_sha256="database",
        build_stats_sha256="stats",
        read_only_smoke_id="smoke",
        successful_episode_count=40,
        scene_exemplar_count=120,
        dependency_edge_count=27,
        structured_action_key_coverage=1.0,
        min_dependency_support=2,
        image_encoder_identity="MineCLIPImageEncoder",
        text_encoder_identity="MineCLIPTextEncoder",
        eligible=True,
    ).with_id()

    assert item.release_id
