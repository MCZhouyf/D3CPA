from dc3pa.experiments.development_tooling_binding import (
    ALLOWED_CHANGE_CLASSES,
    DevelopmentToolingBinding,
)


def test_development_tooling_binding_preserves_runtime_and_memory():
    item = DevelopmentToolingBinding(
        binding_name="round511 tooling",
        approved_by="ZYF",
        approval_record_id="DC3PA-ZYF-R511-008",
        parent_source_commit="30d455add0ef302d9ac967da083a82426a16187c",
        new_source_commit="b" * 40,
        paper_memory_v5_release_id="memory",
        active_taskset_release_id="taskset",
        formal_bootstrap_policy_id="bootstrap",
        prompt_hash_bundle_id_before="prompts",
        prompt_hash_bundle_id_after="prompts",
        controller_identity_sha256_before="controller",
        controller_identity_sha256_after="controller",
        evaluator_identity_sha256_before="evaluator",
        evaluator_identity_sha256_after="evaluator",
        active_catalog_sha256_before="catalog",
        active_catalog_sha256_after="catalog",
        paper_memory_snapshot_root_before="snapshot",
        paper_memory_snapshot_root_after="snapshot",
        allowed_change_classes=tuple(sorted(ALLOWED_CHANGE_CLASSES)),
        prompts_changed=False,
        controller_behavior_changed=False,
        evaluator_behavior_changed=False,
        active_taskset_changed=False,
        paper_memory_changed=False,
        bootstrap_policy_changed=False,
        development_collection_started_before_binding=False,
    ).with_id()
    assert item.binding_id
