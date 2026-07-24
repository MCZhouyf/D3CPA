from dataclasses import replace

import pytest

from dc3pa.contracts import ALLOWED_ACTIONS
from dc3pa.experiments.round513e_authoritative import (
    AuthoritativeEvidenceRelease,
    BilateralGammaProvenanceReport,
    CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2,
    CHRMLiteEngineeringSmokePoolV4_1_2,
    GammaCandidate,
    RebaselineAuthorizationReceipt,
    Round513EPreSmokeIntegrityAuditV3,
    SMOKE_DECLARATIONS,
    algorithmic_payload,
    build_gamma_candidates,
    derive_formal_50_task_smoke_assignments,
    derive_smoke_assignments,
    expected_rebaseline_approval_statement,
    formal_fitting_accepts_smoke_row,
    regenerate_v412_contracts,
    verify_rebaseline_approval,
)


def _authorization_input():
    return {
        "authorization_input_id": "a" * 64,
        "rebaseline_authorization_status": "pending",
        "contract_regeneration_permitted": False,
        "actual_mineclip_policy_id": "b" * 64,
        "actual_snapshot_manifest_id": "c" * 64,
        "actual_acquisition_manifest_id": "d" * 64,
        "scene_candidate_release_id": "e" * 64,
        "declarations": [f"declaration-{index}" for index in range(10)],
    }


def _approval():
    payload = _authorization_input()
    binding = {**payload, "authorization_input_file_sha256": "f" * 64}
    statement = expected_rebaseline_approval_statement(binding)
    return verify_rebaseline_approval(
        source_commit="s" * 40,
        authorization_input=payload,
        authorization_input_file_sha256="f" * 64,
        approval_statement=statement,
    )


def test_rebaseline_approval_requires_exact_frozen_sentence():
    approval = _approval()
    assert approval.approved_by == "ZYF"
    assert approval.contract_regeneration_permitted
    payload = _authorization_input()
    with pytest.raises(ValueError, match="exactly bind"):
        verify_rebaseline_approval(
            source_commit="s" * 40,
            authorization_input=payload,
            authorization_input_file_sha256="f" * 64,
            approval_statement="ZYF approves something else",
        )


def test_authoritative_release_is_prospective_and_cannot_mutate_memory():
    release = AuthoritativeEvidenceRelease(
        release_type="SceneExemplarEvidenceReleaseV5R",
        source_commit="s" * 40,
        authorization_receipt_id="a" * 64,
        authorization_input_id="b" * 64,
        provenance_closure_audit_id="c" * 64,
        retirement_registry_id="d" * 64,
        impact_audit_id="e" * 64,
        candidate_release_id="f" * 64,
        mineclip_policy_id="1" * 64,
        mineclip_checkpoint_manifest_id="2" * 64,
        mineclip_checkpoint_sha256="3" * 64,
        snapshot_manifest_id="4" * 64,
        acquisition_manifest_id="5" * 64,
        snapshot_root_sha256="6" * 64,
        database_sha256="7" * 64,
        asset_manifest_sha256="8" * 64,
        accepted_episode_count=40,
        scene_source_episode_count=36,
        dependency_edge_count=27,
        scene_exemplar_count=144,
        scene_lineage_root="9" * 64,
    ).with_id()
    assert release.usable and not release.historical_equivalence_claimed
    with pytest.raises(ValueError, match="mutated or equated"):
        replace(release, stored_embedding_bytes_changed=True, release_id="")


def _old_objects():
    return {
        "Bilateral Retrieval Policy": {
            "source_commit": "o" * 40,
            "paper_memory_v5_release_id": "p" * 64,
            "scene_exemplar_release_id": "s" * 64,
            "mineclip_policy_id": "m" * 63,
            "top_k_per_side": 3,
            "minimum_count_per_side": 3,
            "compatible_rule": "canonical_action_signature_exact_match",
            "incompatible_rule": "different_signature_with_known_action_family",
            "tie_break": "similarity_desc_exemplar_id_asc",
            "undercovered_state": "unknown",
            "policy_id": "1" * 64,
        },
        "Decision Record Schema": {
            "source_commit": "o" * 40,
            "retrieval_policy_id": "1" * 64,
            "planner_schema_id": "2" * 64,
            "required_field_coverage": 1.0,
            "schema_id": "3" * 64,
        },
        "Collection Blueprint": {
            "source_commit": "o" * 40,
            "retrieval_policy_id": "1" * 64,
            "record_schema_id": "3" * 64,
            "formal_assignments_generated": False,
            "blueprint_id": "4" * 64,
        },
        "Instrumentation Release": {
            "source_commit": "o" * 40,
            "record_schema_id": "3" * 64,
            "behavior_equivalence_audit_id": "5" * 64,
            "smoke_audit_id": "6" * 64,
            "released_for_formal_collection": False,
            "release_id": "7" * 64,
        },
        "Data Readiness Report": {
            "source_commit": "o" * 40,
            "instrumentation_release_id": "7" * 64,
            "smoke_audit_id": "6" * 64,
            "status": "BLOCKED",
            "reason": "engineering_smoke_authorization_missing",
            "report_id": "8" * 64,
        },
        "Readiness Decision": {
            "source_commit": "o" * 40,
            "instrumentation_release_id": "7" * 64,
            "data_readiness_report_id": "8" * 64,
            "state": "BLOCKED",
            "exact_reason": "engineering_smoke_authorization_missing",
            "decision_id": "9" * 64,
        },
    }


def test_v412_regenerates_only_evidence_bindings_and_parent_ids():
    old = _old_objects()
    before = {name: dict(value) for name, value in old.items()}
    new = regenerate_v412_contracts(
        source_commit="n" * 40,
        old_objects=old,
        authoritative_paper_release_id="a" * 64,
        authoritative_scene_release_id="b" * 64,
        actual_mineclip_policy_id="c" * 64,
        algorithmic_audit_id="d" * 64,
    )
    assert old == before
    assert set(new) == set(old)
    assert new["Bilateral Retrieval Policy"]["top_k_per_side"] == 3
    assert new["Bilateral Retrieval Policy"]["tie_break"] == before["Bilateral Retrieval Policy"]["tie_break"]
    for name, id_field in {
        "Bilateral Retrieval Policy": "policy_id",
        "Decision Record Schema": "schema_id",
        "Collection Blueprint": "blueprint_id",
        "Instrumentation Release": "release_id",
        "Data Readiness Report": "report_id",
        "Readiness Decision": "decision_id",
    }.items():
        assert new[name][id_field] != old[name][id_field]


def test_algorithmic_payload_ignores_only_allowed_evidence_fields():
    old = _old_objects()["Bilateral Retrieval Policy"]
    new = dict(old)
    new.update(
        source_commit="n" * 40,
        paper_memory_v5_release_id="a" * 64,
        scene_exemplar_release_id="b" * 64,
        mineclip_policy_id="c" * 64,
        contract_version="4.1.2",
        policy_id="d" * 64,
    )
    assert algorithmic_payload(old, "policy_id") == algorithmic_payload(new, "policy_id")
    new["top_k_per_side"] = 4
    assert algorithmic_payload(old, "policy_id") != algorithmic_payload(new, "policy_id")


def test_v3_requires_all_external_gates_and_never_uses_v1_v2_status():
    v3 = Round513EPreSmokeIntegrityAuditV3(
        source_commit="s" * 40,
        prior_v1_audit_id="0" * 64,
        prior_v2_audit_id="9" * 64,
        provenance_closure_audit_id="a" * 64,
        authorization_receipt_id="b" * 64,
        authoritative_paper_release_id="c" * 64,
        authoritative_scene_release_id="d" * 64,
        mineclip_binding_release_id="e" * 64,
        dependency_graph_id="f" * 64,
        regeneration_plan_id="1" * 64,
        algorithmic_equivalence_audit_id="2" * 64,
        instrumentation_revalidation_audit_id="3" * 64,
        full_test_passed=700,
        full_test_failed=0,
        minedojo_marker_passed=64,
        minedojo_marker_skipped=0,
        snapshot_guard_passed=True,
        write_probe_rejected=True,
        actual_mineclip_strict_probe_passed=True,
        actions_green=True,
        actions_url="https://example.invalid/actions/1",
        historical_gate_count=7,
        worktree_clean=True,
        accepted_episode_count=40,
        scene_source_episode_count=36,
        dependency_edge_count=27,
        scene_exemplar_count=144,
        status="ELIGIBLE_FOR_SMOKE_PREPARATION",
        eligible_for_smoke_preparation=True,
    ).with_id()
    assert v3.eligible_for_smoke_preparation
    with pytest.raises(ValueError, match="eligibility"):
        replace(v3, actions_green=False, audit_id="")
    with pytest.raises(ValueError, match="reuse V1/V2"):
        replace(v3, authoritative_paper_release_id="0" * 64, audit_id="")


def test_smoke_pool_is_deterministic_covers_actions_and_five_difficulties():
    first_namespace, first = derive_smoke_assignments(
        source_commit="s" * 40,
        namespace_label="round513e1r-engineering-smoke-v412",
    )
    second_namespace, second = derive_smoke_assignments(
        source_commit="x" * 40,
        namespace_label="round513e1r-engineering-smoke-v412",
    )
    assert first_namespace == second_namespace and first == second
    assert {item.target_action_family for item in first} == ALLOWED_ACTIONS
    assert {item.difficulty for item in first} == {
        "basic", "easy", "medium", "hard", "complex"
    }
    assert sum(item.coverage_feasibility == "feasible" for item in first) == 5
    assert sum(item.coverage_feasibility == "proxy_only" for item in first) == 4
    assert any(item.terminal_task == "creature" for item in first)
    pool = CHRMLiteEngineeringSmokePoolV4_1_2(
        source_commit="s" * 40,
        v3_audit_id="a" * 64,
        v3_status="ELIGIBLE_FOR_SMOKE_PREPARATION",
        namespace_id=first_namespace,
        assignments=first,
    ).with_id()
    assert not pool.outcome_selected and not pool.fitting_eligible
    with pytest.raises(ValueError, match="requires eligible V3"):
        replace(pool, v3_status="BLOCKED", pool_id="")


def test_formal_50_task_smoke_replaces_creature_without_rewriting_history():
    historical_namespace, historical = derive_smoke_assignments(
        source_commit="s" * 40,
        namespace_label="round513e1r-engineering-smoke-v412",
    )
    aligned_namespace, aligned = derive_formal_50_task_smoke_assignments(
        source_commit="s" * 40,
        namespace_label="round513e3-formal50-engineering-smoke-v412",
    )
    assert historical_namespace != aligned_namespace
    assert len(historical) == len(aligned) == 9
    assert any(item.terminal_task == "creature" for item in historical)
    assert not any(item.terminal_task == "creature" for item in aligned)
    assert {item.difficulty for item in aligned} == {
        "basic", "easy", "medium", "hard", "complex"
    }
    assert {item.target_action_family for item in aligned} == ALLOWED_ACTIONS - {"fight"}
    iron_ingot = next(item for item in aligned if item.terminal_task == "iron ingot")
    assert iron_ingot.task_path_label == "agent/tasks/creative/iron_ingot.json"
    assert iron_ingot.difficulty == "hard"
    assert iron_ingot.target_action_family == "craft"
    assert iron_ingot.coverage_feasibility == "feasible"


def test_gamma_g3_candidates_are_not_automatically_selected():
    quantiles = {"q10": -0.01, "q25": -0.004, "q75": 0.003, "q90": 0.008}
    candidates = build_gamma_candidates(quantiles)
    assert len(candidates) == 3
    assert all(item.gamma_cov == 1.0 and item.gamma_minus < item.gamma_plus for item in candidates)
    report = BilateralGammaProvenanceReport(
        source_commit="s" * 40,
        authoritative_scene_release_id="a" * 64,
        mineclip_policy_id="b" * 64,
        query_corpus_root="c" * 64,
        query_count=144,
        action_signature_count=19,
        full_coverage_query_count=140,
        undercovered_query_count=4,
        contrast_count=140,
        contrast_quantiles=quantiles,
        gamma_case="G3",
        candidates=candidates,
    ).with_id()
    assert not report.candidate_selected and not report.outcome_labels_used
    assert report.classification_semantics.startswith(
        "if min(cov_positive,cov_negative) < gamma_cov"
    )


def test_smoke_authorization_remains_pending_and_fitting_rejects_rows():
    candidates = (
        GammaCandidate("a" * 64, 1.0, -0.01, 0.01, "candidate"),
    )
    authorization = CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2(
        source_commit="s" * 40,
        v3_audit_id="a" * 64,
        smoke_pool_id="b" * 64,
        smoke_assignments_id="c" * 64,
        smoke_exclusion_audit_id="d" * 64,
        smoke_assignment_seal_id="e" * 64,
        gamma_report_id="f" * 64,
        gamma_case="G3",
        gamma_candidates=candidates,
        declarations=SMOKE_DECLARATIONS,
    ).with_id()
    assert authorization.smoke_authorization_status == "pending"
    assert not authorization.minedojo_smoke_permitted
    assert not formal_fitting_accepts_smoke_row(engineering_only=True)
    assert formal_fitting_accepts_smoke_row(engineering_only=False)
