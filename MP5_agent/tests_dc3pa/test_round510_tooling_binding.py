from dc3pa.experiments.execution_tooling_binding import (
    ALLOWED_CHANGE_CLASSES,
    ExecutionToolingBinding,
)


def test_tooling_binding_requires_protected_identities_unchanged():
    item = ExecutionToolingBinding(
        binding_name="round510 execution tooling",
        approved_by="ZYF",
        approval_record_id="DC3PA-ZYF-R510-EXECUTION-006",
        source_extension_audit_sha256="audit-sha",
        parent_source_commit="540e83f9d75358e1eacb218bfc75fc4ae41f3b9c",
        new_source_commit="new-commit",
        parent_formal_authorization_id=(
            "21acefe77baa226742088b61f5d792cd7d490f83df67c7ea3ab76d9b08ead03f"
        ),
        bootstrap_policy_id="policy",
        bootstrap_amendment_id="amendment",
        blueprint_id="blueprint",
        acquisition_schedule_id="schedule",
        taskset_release_id="taskset",
        prompt_hash_bundle_id_before="prompts",
        prompt_hash_bundle_id_after="prompts",
        controller_identity_sha256_before="controller",
        controller_identity_sha256_after="controller",
        evaluator_identity_sha256_before="evaluator",
        evaluator_identity_sha256_after="evaluator",
        task_catalog_sha256_before="tasks",
        task_catalog_sha256_after="tasks",
        allowed_change_classes=tuple(sorted(ALLOWED_CHANGE_CLASSES)),
        prompts_changed=False,
        controller_behavior_changed=False,
        evaluator_behavior_changed=False,
        task_catalog_changed=False,
        seeds_or_schedule_changed=False,
        bootstrap_policy_changed=False,
        formal_acquisition_started_before_binding=False,
    ).with_id()
    assert item.binding_id
