from dataclasses import replace

import pytest

from dc3pa.experiments.round513e_rebaseline import (
    ActualArtifactCandidateRelease,
    ActualPaperMemoryV5ProvenanceClosureAudit,
    InvalidBindingRetirementRegistry,
    ProspectiveMemoryRebaselineAuthorizationInput,
    ProspectiveRebaselineImpactAudit,
    REBASELINE_DECLARATIONS,
    RetirementEntry,
    build_authorization_input,
    build_candidate_release,
    exact_full_id_equal,
    retired_reference_is_eligible,
    transitive_dependency_ids,
)


def _lineage(index):
    return {
        "scene_id": f"scene-{index:03d}",
        "source_episode_id": f"episode-{index % 36:02d}",
        "stored_image_embedding_sha256": "a" * 64,
        "stored_text_embedding_sha256": "b" * 64,
    }


def _closure(status="ACTUAL_PROVENANCE_CLOSED", errors=()):
    return ActualPaperMemoryV5ProvenanceClosureAudit(
        source_commit="s" * 40,
        status=status,
        embedding_evidence_path="P1",
        actual_snapshot_manifest_id="1" * 64,
        actual_snapshot_manifest_file_sha256="1" * 64,
        actual_acquisition_manifest_id="2" * 64,
        actual_acquisition_manifest_file_sha256="2" * 64,
        actual_acquisition_root_sha256="3" * 64,
        accepted_source_manifest_id="4" * 64,
        accepted_source_manifest_file_sha256="4" * 64,
        accepted_source_root_sha256="5" * 64,
        accepted_source_file_map_sha256="5" * 64,
        accepted_source_file_count=184,
        snapshot_root_sha256="6" * 64,
        database_sha256="7" * 64,
        asset_manifest_sha256="8" * 64,
        builder_source_commit="t" * 40,
        builder_contract_id="9" * 64,
        builder_contract_file_sha256="a" * 64,
        build_stats_file_sha256="b" * 64,
        mineclip_policy_id="c" * 64,
        mineclip_policy_file_sha256="d" * 64,
        mineclip_checkpoint_manifest_id="e" * 64,
        mineclip_checkpoint_manifest_file_sha256="f" * 64,
        mineclip_checkpoint_sha256="0" * 64,
        mineclip_checkpoint_md5="1" * 32,
        mineclip_probe_id="2" * 64,
        mineclip_probe_file_sha256="3" * 64,
        readonly_snapshot_smoke_id="9" * 64,
        readonly_snapshot_smoke_file_sha256="a" * 64,
        accepted_episode_count=40,
        accepted_episode_identity_root="4" * 64,
        source_receipt_hash_root="5" * 64,
        scene_source_episode_count=36,
        scene_source_episode_identity_root="6" * 64,
        no_scene_episode_count=4,
        no_scene_reason="frozen_no_valid_scene_candidate",
        dependency_edge_count=27,
        scene_exemplar_count=144,
        unique_scene_count=144,
        scene_lineage_root="7" * 64,
        embedding_row_hash_root="8" * 64,
        duplicate_scene_id_count=0,
        orphan_scene_count=0,
        missing_image_count=0,
        missing_embedding_count=0,
        source_episode_outside_acquisition_count=0,
        task_seed_run_identity_count=40,
        holdout_final_source_count=0,
        snapshot_guard_passed=True,
        sqlite_integrity_passed=True,
        database_sha256_after="7" * 64,
        snapshot_root_sha256_after="6" * 64,
        asset_manifest_sha256_after="8" * 64,
        write_count=0,
        memory_rebuilt=False,
        reencoding_count=0,
        row_mutation_count=0,
        scene_lineage=tuple(_lineage(index) for index in range(144)),
        errors=tuple(errors),
    ).with_id()


def _retirement():
    return InvalidBindingRetirementRegistry(
        source_commit="s" * 40,
        entries=(
            RetirementEntry(
                object_id="a" * 64,
                object_kind="quarantined_scene_release",
                reason="unusable",
            ),
        ),
    ).with_id()


def _impact(retirement):
    return ProspectiveRebaselineImpactAudit(
        source_commit="s" * 40,
        invalid_binding_retirement_registry_id=retirement.registry_id,
        readiness_decision_id="b" * 64,
        readiness_decision_file_sha256="c" * 64,
        blocked_v1_audit_id="d" * 64,
        blocked_v1_audit_file_sha256="e" * 64,
        blocked_v2_audit_id="f" * 64,
        blocked_v2_audit_file_sha256="0" * 64,
        engineering_smoke_audit_id="1" * 64,
        engineering_smoke_audit_file_sha256="2" * 64,
        engineering_smoke_rows_under_invalid_contracts=0,
        formal_v4_1_development_rows=0,
        chrm_cdt_fitted_artifact_count=0,
        holdout_final_row_count=0,
        prospective_rebaseline_justified=True,
    ).with_id()


def test_invalid_prefixes_never_compare_as_full_ids():
    value = "a" * 64
    assert exact_full_id_equal(value, value)
    assert not exact_full_id_equal(value[:12], value)
    assert not exact_full_id_equal(value, value[:12])


def test_malformed_63_character_historical_reference_is_retired_without_padding():
    malformed = "a" * 63
    entry = RetirementEntry(
        object_id=malformed,
        object_kind="invalid_mineclip_reference",
        reason="historical reference is not a complete SHA-256 identity",
        identity_complete=False,
    )
    registry = InvalidBindingRetirementRegistry(
        source_commit="s" * 40,
        entries=(entry,),
    ).with_id()
    assert registry.rejects(malformed)
    with pytest.raises(ValueError, match="completeness"):
        replace(entry, identity_complete=True)


def test_closed_actual_provenance_requires_40_36_27_144_and_no_mutation():
    closure = _closure()
    assert closure.accepted_episode_count == 40
    assert closure.scene_source_episode_count == 36
    assert len({row["source_episode_id"] for row in closure.scene_lineage}) == 36
    with pytest.raises(ValueError, match="immutable closure"):
        replace(closure, write_count=1, audit_id="")
    with pytest.raises(ValueError, match="unexpected aggregate"):
        replace(closure, scene_source_episode_count=40, audit_id="")


def test_p1_candidate_binds_actual_assets_without_reencoding():
    candidate = build_candidate_release(
        release_name="PaperMemoryV5ActualArtifactCandidateRelease",
        closure=_closure(),
    )
    assert candidate.authorization_status == "pending"
    assert not candidate.usable
    assert not candidate.memory_rebuilt
    assert not candidate.embedding_bytes_changed
    assert not candidate.historical_equivalence_claimed


def test_incomplete_provenance_cannot_create_candidate_release():
    incomplete = _closure(
        status="ACTUAL_PROVENANCE_INCOMPLETE",
        errors=("missing immutable binding",),
    )
    with pytest.raises(ValueError, match="not closed"):
        build_candidate_release(release_name="candidate", closure=incomplete)


def test_quarantined_release_and_non_full_references_are_ineligible():
    registry = _retirement()
    assert not retired_reference_is_eligible("a" * 64, registry)
    assert not retired_reference_is_eligible("a" * 12, registry)
    assert retired_reference_is_eligible("b" * 64, registry)


def test_dependency_closure_finds_only_direct_and_transitive_binders():
    invalid = "a" * 64
    direct = "b" * 64
    transitive = "c" * 64
    unrelated = "d" * 64
    nodes = {
        direct: {invalid},
        transitive: {direct},
        unrelated: {"e" * 64},
    }
    assert transitive_dependency_ids(nodes=nodes, invalid_roots={invalid}) == (
        direct,
        transitive,
    )


def test_impact_audit_requires_zero_prior_results():
    retirement = _retirement()
    impact = _impact(retirement)
    assert impact.prospective_rebaseline_justified
    with pytest.raises(ValueError, match="does not match"):
        replace(
            impact,
            engineering_smoke_rows_under_invalid_contracts=1,
            audit_id="",
        )


def test_rebaseline_input_is_pending_and_cannot_fabricate_author_approval():
    closure = _closure()
    retirement = _retirement()
    impact = _impact(retirement)
    paper = build_candidate_release(release_name="paper", closure=closure)
    scene = build_candidate_release(release_name="scene", closure=closure)
    authorization = build_authorization_input(
        source_commit="s" * 40,
        closure=closure,
        closure_file_sha256="1" * 64,
        retirement=retirement,
        retirement_file_sha256="2" * 64,
        impact=impact,
        impact_file_sha256="3" * 64,
        paper_candidate=paper,
        paper_candidate_file_sha256="4" * 64,
        scene_candidate=scene,
        scene_candidate_file_sha256="5" * 64,
    )
    assert authorization.declarations == REBASELINE_DECLARATIONS
    assert authorization.rebaseline_authorization_status == "pending"
    assert not authorization.contract_regeneration_permitted
    with pytest.raises(ValueError, match="cannot be fabricated"):
        replace(authorization, approved_by="ZYF", authorization_input_id="")


def test_old_contract_payload_remains_immutable_during_dependency_audit():
    payload = {"policy_id": "b" * 64, "mineclip_policy_id": "a" * 64}
    before = dict(payload)
    transitive_dependency_ids(
        nodes={payload["policy_id"]: {payload["mineclip_policy_id"]}},
        invalid_roots={payload["mineclip_policy_id"]},
    )
    assert payload == before


def test_candidate_release_rejects_changed_stored_embedding_bytes():
    candidate = build_candidate_release(release_name="scene", closure=_closure())
    with pytest.raises(ValueError, match="changes or equates"):
        replace(candidate, embedding_bytes_changed=True, release_id="")
