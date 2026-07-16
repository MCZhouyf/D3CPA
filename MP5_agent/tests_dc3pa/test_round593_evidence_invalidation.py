from dc3pa.experiments.controller_revision import (
    EvidenceInvalidationManifest,
    InvalidatedEvidence,
)


def test_controller_change_requires_complete_evidence_regeneration():
    required = (
        "github_actions",
        "full_pytest",
        "minedojo_marker",
        "controller_identity",
        "task_semantic_smoke",
        "final_taskset_release",
        "schema_v2_design",
        "semantic_migration",
        "approval_binding",
        "blueprint_validation",
        "model_epoch",
        "six_entry_readiness_campaign",
        "acquisition_readiness",
        "preacquisition_gate",
    )
    item = EvidenceInvalidationManifest(
        manifest_name="post-controller-fix-regeneration",
        previous_source_commit="da85da1",
        replacement_source_commit="new",
        controller_revision_id="revision",
        artifacts=(
            InvalidatedEvidence(
                artifact_label="old dry run",
                artifact_id="campaign",
                artifact_sha256="sha",
                bound_source_commit="da85da1",
                invalidation_reason="Controller behavior changed.",
            ),
        ),
        required_regeneration_labels=required,
    ).with_id()
    assert item.manifest_id
