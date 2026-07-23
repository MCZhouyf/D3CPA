from __future__ import annotations

from dataclasses import replace

import pytest

from dc3pa.experiments.round5126_supersession import (
    OldMonotonicLogisticBaselineRelease,
    RetiredAuthorizationRegistry,
    Round5126SupersessionDecision,
)


def test_supersession_cannot_claim_consumption_or_reuse():
    decision = Round5126SupersessionDecision(
        source_sha="source",
        pending_authorization_input_id="authorization",
        invalidation_receipt_id="invalidation",
    ).with_id()
    assert decision.status == "superseded_before_assignment_generation"
    assert not decision.scientific_holdout_consumed
    with pytest.raises(ValueError, match="consume, reopen, or discard"):
        replace(decision, old_assignments_generated=True, decision_id="")
    with pytest.raises(ValueError, match="consume, reopen, or discard"):
        replace(decision, old_salt_namespace_reusable=True, decision_id="")


def test_retired_registry_binds_every_old_identity_and_preserves_files():
    registry = RetiredAuthorizationRegistry(
        source_sha="source",
        pending_authorization_input_id="authorization",
        pending_authorization_input_sha256="authorization-sha",
        salt_commitment_sha256="salt-commitment",
        namespace_id="namespace",
        preflight_binding_id="preflight",
        preflight_binding_sha256="preflight-sha",
        runtime_release_id="runtime",
        runtime_release_sha256="runtime-sha",
        exclusion_registry_id="exclusion",
        exclusion_registry_sha256="exclusion-sha",
        invalidation_receipt_id="invalidation",
        supersession_decision_id="decision",
    ).with_id()
    assert registry.registry_id
    with pytest.raises(ValueError, match="cannot be reused"):
        replace(registry, authorization_reusable=True, registry_id="")


def test_old_logistic_is_comparison_only_and_schema_bound():
    release = OldMonotonicLogisticBaselineRelease(
        release_name="OldMonotonicLogisticBaselineRelease",
        retired_from_source_sha="source",
        model_source_commit="model-source",
        feature_schema_id="schema",
        feature_schema_sha256="schema-sha",
        feature_order=("k", "u", "l", "e"),
        coefficients={"k": 0.0, "u": 0.0, "l": 1.5, "e": 0.0},
        intercept=0.3,
        selected_l2=0.001,
        selected_checkpoint=5000,
        confidence_release_id="confidence",
        confidence_release_sha256="confidence-sha",
        environment_release_id="environment",
        environment_release_sha256="environment-sha",
        paper_memory_v5_release_id="memory",
        paper_memory_v5_root_sha256="memory-root",
        development_train_sha256="train",
        development_tune_sha256="tune",
        fusion_train_sha256="fusion-train",
        fusion_tune_sha256="fusion-tune",
        activation_policy_id="activation",
        activation_policy_sha256="activation-sha",
    ).with_id()
    assert release.release_id
    with pytest.raises(ValueError, match="frozen baseline"):
        replace(release, fitting_reopened=True, release_id="")
