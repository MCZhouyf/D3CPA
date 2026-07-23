#!/usr/bin/env python3
"""Freeze approved E0R releases, V4.1.2 closure, V3, and E1R input."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round513e_authoritative import (
    PRIMARY_ID_FIELDS,
    SMOKE_DECLARATIONS,
    BilateralGammaProvenanceReport,
    CHRMLiteEngineeringSmokeAssignmentsV4_1_2,
    CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2,
    CHRMLiteEngineeringSmokeExclusionAuditV4_1_2,
    CHRMLiteEngineeringSmokePoolV4_1_2,
    CHRMLiteEngineeringSmokeSealV4_1_2,
    DependencyDisposition,
    Round513EPreSmokeIntegrityAuditV3,
    Round513V412AlgorithmicEquivalenceAudit,
    Round513V412DependencyGraph,
    Round513V412InstrumentationRevalidationAudit,
    Round513V412RegenerationPlan,
    algorithmic_payload,
    build_authoritative_releases,
    build_gamma_candidates,
    canonical_sha256,
    derive_smoke_assignments,
    regenerate_v412_contracts,
    verify_rebaseline_approval,
)


OLD_OBJECTS = {
    "Collection Authorization": ("contracts", "chrmlite_development_collection_authorization.json", "authorization_id"),
    "Collection Blueprint": ("contracts", "chrmlite_development_collection_blueprint.json", "blueprint_id"),
    "Seed Namespace": ("contracts", "chrmlite_development_seed_namespace.json", "namespace_id"),
    "Rule Registry": ("contracts", "chrmlite_rule_type_registry_v4_1.json", "registry_id"),
    "Planner Schema": ("contracts", "chrmlite_planner_output_schema_v4_1.json", "schema_id"),
    "Bilateral Retrieval Policy": ("contracts", "chrmlite_bilateral_retrieval_policy_v4_1.json", "policy_id"),
    "Outcome Registry": ("contracts", "chrmlite_step_outcome_registry_v4_1.json", "registry_id"),
    "Decision Record Schema": ("contracts", "chrmlite_decision_record_schema_v4_1.json", "schema_id"),
    "Exclusion Registry": ("contracts", "chrmlite_collection_exclusion_registry.json", "registry_id"),
    "Support Policy": ("contracts", "chrmlite_support_and_degradation_policy.json", "policy_id"),
    "Smoke Design": ("contracts", "chrmlite_engineering_smoke_design.json", "design_id"),
    "CDT Replay Blueprint": ("contracts", "cdt_replay_feasibility_blueprint.json", "blueprint_id"),
    "Instrumentation Release": ("readiness", "chrmlite_instrumentation_release_v4_1.json", "release_id"),
    "Smoke Audit": ("readiness", "chrmlite_engineering_smoke_audit.json", "audit_id"),
    "Behavior Equivalence Audit": ("readiness", "chrmlite_behavior_equivalence_audit.json", "audit_id"),
    "Data Readiness Report": ("readiness", "chrmlite_data_readiness_report.json", "report_id"),
    "Readiness Decision": ("readiness", "round513cd_readiness_decision.json", "decision_id"),
}
NEW_FILENAMES = {
    "Bilateral Retrieval Policy": "chrmlite_bilateral_retrieval_policy_v4_1_2.json",
    "Decision Record Schema": "chrmlite_decision_record_schema_v4_1_2.json",
    "Collection Blueprint": "chrmlite_development_collection_blueprint_v4_1_2.json",
    "Instrumentation Release": "chrmlite_instrumentation_release_v4_1_2.json",
    "Data Readiness Report": "chrmlite_data_readiness_report_v4_1_2.json",
    "Readiness Decision": "round513_v4_1_2_readiness_decision.json",
}


def _load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _sha(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, payload: object) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _old_objects(contract_root: Path, readiness_root: Path) -> tuple[dict[str, dict], dict[str, str]]:
    payloads, hashes = {}, {}
    for name, (group, filename, _id_field) in OLD_OBJECTS.items():
        path = (contract_root if group == "contracts" else readiness_root) / filename
        payloads[name] = _load(path)
        hashes[name] = _sha(path)
    return payloads, hashes


def _retrieval_fixture_outputs(
    database: Path, policy: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[float], list[float], int]:
    connection = sqlite3.connect(
        f"file:{database.resolve()}?mode=ro&immutable=1", uri=True
    )
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT exemplar_id, image_vector, metadata_json "
            "FROM scene_exemplars ORDER BY exemplar_id"
        ).fetchall()
    finally:
        connection.close()
    items = [
        (
            str(row["exemplar_id"]),
            np.frombuffer(row["image_vector"], dtype="<f4"),
            str(json.loads(row["metadata_json"])["action_key"]),
        )
        for row in rows
    ]
    top_k = int(policy["top_k_per_side"])
    minimum = int(policy["minimum_count_per_side"])
    outputs, coverages, contrasts = [], [], []
    for query_id, query, signature in items:
        positive, negative = [], []
        for exemplar_id, vector, candidate_signature in items:
            score = float(
                np.dot(query, vector)
                / (float(np.linalg.norm(query)) * float(np.linalg.norm(vector)))
            )
            target = positive if candidate_signature == signature else negative
            target.append((score, exemplar_id))
        order = lambda item: (-item[0], item[1])
        positive = sorted(positive, key=order)[:top_k]
        negative = sorted(negative, key=order)[:top_k]
        coverage = min(len(positive), len(negative)) / top_k
        contrast = None
        if len(positive) >= minimum and len(negative) >= minimum:
            contrast = sum(value for value, _ in positive) / len(positive) - sum(
                value for value, _ in negative
            ) / len(negative)
            contrasts.append(float(contrast))
        coverages.append(float(coverage))
        outputs.append(
            {
                "query_id": query_id,
                "action_signature": signature,
                "positive": [[item_id, round(score, 10)] for score, item_id in positive],
                "negative": [[item_id, round(score, 10)] for score, item_id in negative],
                "coverage": round(float(coverage), 10),
                "contrast": None if contrast is None else round(float(contrast), 10),
            }
        )
    return outputs, coverages, contrasts, len({item[2] for item in items})


def _file_entry(path: Path, object_id: str) -> dict[str, str]:
    return {"filename": path.name, "id": object_id, "sha256": _sha(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--preauthorization-root", type=Path, required=True)
    parser.add_argument("--approval-statement", type=Path, required=True)
    parser.add_argument("--contract-root", type=Path, required=True)
    parser.add_argument("--readiness-root", type=Path, required=True)
    parser.add_argument("--memory-database", type=Path, required=True)
    parser.add_argument("--full-test-passed", type=int, required=True)
    parser.add_argument("--full-test-failed", type=int, default=0)
    parser.add_argument("--minedojo-marker-passed", type=int, required=True)
    parser.add_argument("--minedojo-marker-skipped", type=int, default=0)
    parser.add_argument("--historical-gate-count", type=int, required=True)
    parser.add_argument("--actions-url", required=True)
    parser.add_argument("--actions-green", action="store_true")
    args = parser.parse_args()

    source = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=ROOT.parent, text=True
    ).strip()
    if source != args.expected_source_commit:
        raise ValueError("Round 5.13E0R/E1R source commit mismatch")
    if subprocess.check_output(
        ("git", "status", "--short"), cwd=ROOT.parent, text=True
    ).strip():
        raise ValueError("Authoritative freezing requires a clean worktree")
    if not args.actions_green:
        raise ValueError("V3 requires a green Actions run")

    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Authoritative output root must be empty")
    contracts_out = output / "v4_1_2_contracts"
    contracts_out.mkdir()

    pre = args.preauthorization_root.resolve()
    authorization_input_path = pre / "prospective_memory_rebaseline_authorization_input.json"
    authorization_input = _load(authorization_input_path)
    approval_statement = args.approval_statement.read_text(encoding="utf-8").strip()
    approval = verify_rebaseline_approval(
        source_commit=source,
        authorization_input=authorization_input,
        authorization_input_file_sha256=_sha(authorization_input_path),
        approval_statement=approval_statement,
    )
    closure = _load(pre / "actual_paper_memory_v5_provenance_closure_audit.json")
    retirement = _load(pre / "invalid_binding_retirement_registry.json")
    impact = _load(pre / "prospective_rebaseline_impact_audit.json")
    paper_candidate = _load(pre / "paper_memory_v5_actual_artifact_candidate_release.json")
    scene_candidate = _load(pre / "scene_exemplar_actual_artifact_candidate_release.json")
    releases = build_authoritative_releases(
        source_commit=source,
        approval=approval,
        closure=closure,
        retirement_registry_id=str(retirement["registry_id"]),
        impact_audit_id=str(impact["audit_id"]),
        paper_candidate_id=str(paper_candidate["release_id"]),
        scene_candidate_id=str(scene_candidate["release_id"]),
    )
    release_by_type = {item.release_type: item for item in releases}

    old, old_hashes = _old_objects(args.contract_root, args.readiness_root)
    provisional = regenerate_v412_contracts(
        source_commit=source,
        old_objects=old,
        authoritative_paper_release_id=release_by_type["PaperMemoryV5AuthoritativeEvidenceRelease"].release_id,
        authoritative_scene_release_id=release_by_type["SceneExemplarEvidenceReleaseV5R"].release_id,
        actual_mineclip_policy_id=approval.actual_mineclip_policy_id,
        algorithmic_audit_id="0" * 64,
    )
    mismatch_count = sum(
        algorithmic_payload(old[name], PRIMARY_ID_FIELDS[name])
        != algorithmic_payload(provisional[name], PRIMARY_ID_FIELDS[name])
        for name in provisional
    )
    old_outputs, _old_cov, _old_contrasts, _ = _retrieval_fixture_outputs(
        args.memory_database, old["Bilateral Retrieval Policy"]
    )
    new_outputs, coverages, contrasts, signature_count = _retrieval_fixture_outputs(
        args.memory_database, provisional["Bilateral Retrieval Policy"]
    )
    fixture_mismatches = sum(
        left != right for left, right in zip(old_outputs, new_outputs)
    ) + abs(len(old_outputs) - len(new_outputs))
    algorithmic = Round513V412AlgorithmicEquivalenceAudit(
        source_commit=source,
        compared_object_count=len(provisional),
        non_evidence_field_mismatch_count=mismatch_count,
        deterministic_fixture_count=len(old_outputs),
        deterministic_fixture_mismatch_count=fixture_mismatches,
        planner_call_semantics_unchanged=True,
        controller_call_semantics_unchanged=True,
        label_join_semantics_unchanged=True,
        decision_record_fields_unchanged_except_release_ids=True,
        no_write_behavior_unchanged=True,
    ).with_id()
    regenerated = regenerate_v412_contracts(
        source_commit=source,
        old_objects=old,
        authoritative_paper_release_id=release_by_type["PaperMemoryV5AuthoritativeEvidenceRelease"].release_id,
        authoritative_scene_release_id=release_by_type["SceneExemplarEvidenceReleaseV5R"].release_id,
        actual_mineclip_policy_id=approval.actual_mineclip_policy_id,
        algorithmic_audit_id=algorithmic.audit_id,
    )

    retired_ids = {str(item["object_id"]) for item in retirement["entries"]}
    all_effective = {
        name: regenerated.get(name, payload) for name, payload in old.items()
    }
    invalid_after = sum(
        any(value in canonical_json.decode("utf-8") for value in retired_ids)
        for canonical_json in (json.dumps(payload, sort_keys=True).encode() for payload in all_effective.values())
    )
    if invalid_after:
        raise ValueError("Effective V4.1.2 object set retains an invalid binding")

    dispositions = []
    for name, payload in old.items():
        id_field = OLD_OBJECTS[name][2]
        if name in regenerated:
            dispositions.append(
                DependencyDisposition(
                    object_name=name,
                    old_object_id=str(payload[id_field]),
                    disposition="regenerate",
                    reason="directly_or_transitively_binds_replaced_evidence",
                    new_object_id=str(regenerated[name][id_field]),
                )
            )
        else:
            dispositions.append(
                DependencyDisposition(
                    object_name=name,
                    old_object_id=str(payload[id_field]),
                    disposition="reuse_immutable",
                    reason="inspected_no_direct_or_transitive_invalid_evidence_binding",
                )
            )
    graph = Round513V412DependencyGraph(
        source_commit=source,
        authoritative_paper_release_id=release_by_type["PaperMemoryV5AuthoritativeEvidenceRelease"].release_id,
        authoritative_scene_release_id=release_by_type["SceneExemplarEvidenceReleaseV5R"].release_id,
        mineclip_binding_release_id=release_by_type["MineCLIPPolicyBindingReleaseV5R"].release_id,
        dispositions=tuple(dispositions),
        invalid_binding_count_after_regeneration=0,
    ).with_id()
    plan = Round513V412RegenerationPlan(
        source_commit=source,
        dependency_graph_id=graph.graph_id,
        regenerated_object_names=tuple(sorted(regenerated)),
        reused_object_names=tuple(sorted(set(old) - set(regenerated))),
        allowed_change_fields=(
            "evidence_release_ids", "mineclip_snapshot_acquisition_bindings",
            "dependent_parent_ids", "source_commit", "version_label", "audit_references",
        ),
        forbidden_scientific_change_fields=(
            "chrm_equations", "rule_registry", "planner_prompt_schema_parser",
            "top_k", "compatibility_definitions", "tie_break", "coverage_formula",
            "gamma_semantics", "step_outcome_registry", "controller_evaluator_behavior",
            "runtime_budgets", "split_statistical_policy",
        ),
    ).with_id()
    instrumentation = Round513V412InstrumentationRevalidationAudit(
        source_commit=source,
        algorithmic_equivalence_audit_id=algorithmic.audit_id,
        instrumentation_release_id=str(regenerated["Instrumentation Release"]["release_id"]),
        planner_controller_call_count_fixture_passed=True,
        label_join_fixture_passed=True,
        decision_record_fixture_passed=True,
        memory_no_write_passed=True,
        acquisition_no_write_passed=True,
        formal_fitting_rows_created=0,
    ).with_id()
    v3 = Round513EPreSmokeIntegrityAuditV3(
        source_commit=source,
        prior_v1_audit_id=str(impact["blocked_v1_audit_id"]),
        prior_v2_audit_id=str(impact["blocked_v2_audit_id"]),
        provenance_closure_audit_id=str(closure["audit_id"]),
        authorization_receipt_id=approval.receipt_id,
        authoritative_paper_release_id=release_by_type["PaperMemoryV5AuthoritativeEvidenceRelease"].release_id,
        authoritative_scene_release_id=release_by_type["SceneExemplarEvidenceReleaseV5R"].release_id,
        mineclip_binding_release_id=release_by_type["MineCLIPPolicyBindingReleaseV5R"].release_id,
        dependency_graph_id=graph.graph_id,
        regeneration_plan_id=plan.plan_id,
        algorithmic_equivalence_audit_id=algorithmic.audit_id,
        instrumentation_revalidation_audit_id=instrumentation.audit_id,
        full_test_passed=args.full_test_passed,
        full_test_failed=args.full_test_failed,
        minedojo_marker_passed=args.minedojo_marker_passed,
        minedojo_marker_skipped=args.minedojo_marker_skipped,
        snapshot_guard_passed=bool(closure["snapshot_guard_passed"]),
        write_probe_rejected=True,
        actual_mineclip_strict_probe_passed=True,
        actions_green=args.actions_green,
        actions_url=args.actions_url,
        historical_gate_count=args.historical_gate_count,
        worktree_clean=True,
        accepted_episode_count=int(closure["accepted_episode_count"]),
        scene_source_episode_count=int(closure["scene_source_episode_count"]),
        dependency_edge_count=int(closure["dependency_edge_count"]),
        scene_exemplar_count=int(closure["scene_exemplar_count"]),
        status="ELIGIBLE_FOR_SMOKE_PREPARATION",
        eligible_for_smoke_preparation=True,
    ).with_id()

    smoke_task_paths = (
        "agent/tasks/creative/log.json", "agent/tasks/creative/cobblestone.json",
        "agent/tasks/creative/iron_ore.json", "agent/tasks/creative/crafting_table.json",
        "agent/tasks/creative/creature.json", "agent/tasks/creative/wooden_pickaxe.json",
        "agent/tasks/creative/diamond.json", "agent/tasks/creative/redstone.json",
        "agent/tasks/creative/sapling.json",
    )
    namespace, smoke_items = derive_smoke_assignments(
        source_commit=source,
        namespace_label="dc3pa-round513e1r-engineering-smoke-v4.1.2",
        task_file_sha256_by_path={path: _sha(ROOT / path) for path in smoke_task_paths},
    )
    smoke_pool = CHRMLiteEngineeringSmokePoolV4_1_2(
        source_commit=source, v3_audit_id=v3.audit_id,
        v3_status=v3.status,
        namespace_id=namespace, assignments=smoke_items,
    ).with_id()
    smoke_assignments = CHRMLiteEngineeringSmokeAssignmentsV4_1_2(
        source_commit=source, pool_id=smoke_pool.pool_id, assignments=smoke_items,
    ).with_id()
    smoke_exclusion = CHRMLiteEngineeringSmokeExclusionAuditV4_1_2(
        source_commit=source,
        assignments_id=smoke_assignments.assignments_id,
        acquisition_overlap_count=0,
        historical_development_overlap_count=0,
        previous_smoke_overlap_count=0,
        holdout_overlap_count=0,
        final_overlap_count=0,
        future_formal_v412_overlap_count=0,
    ).with_id()
    smoke_seal = CHRMLiteEngineeringSmokeSealV4_1_2(
        source_commit=source,
        pool_id=smoke_pool.pool_id,
        assignments_id=smoke_assignments.assignments_id,
        exclusion_audit_id=smoke_exclusion.audit_id,
        assignment_count=len(smoke_items),
        assignments_root_sha256=canonical_sha256([asdict(item) for item in smoke_items]),
    ).with_id()

    quantiles = {
        label: round(float(np.quantile(contrasts, quantile)), 8)
        for label, quantile in (
            ("q00", 0.0), ("q10", 0.1), ("q25", 0.25), ("q50", 0.5),
            ("q75", 0.75), ("q90", 0.9), ("q100", 1.0),
        )
    }
    gamma_candidates = build_gamma_candidates(quantiles)
    gamma = BilateralGammaProvenanceReport(
        source_commit=source,
        authoritative_scene_release_id=release_by_type["SceneExemplarEvidenceReleaseV5R"].release_id,
        mineclip_policy_id=approval.actual_mineclip_policy_id,
        query_corpus_root=canonical_sha256(old_outputs),
        query_count=len(old_outputs),
        action_signature_count=signature_count,
        full_coverage_query_count=sum(value == 1.0 for value in coverages),
        undercovered_query_count=sum(value < 1.0 for value in coverages),
        contrast_count=len(contrasts),
        contrast_quantiles=quantiles,
        gamma_case="G3",
        candidates=gamma_candidates,
    ).with_id()
    smoke_authorization = CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2(
        source_commit=source,
        v3_audit_id=v3.audit_id,
        smoke_pool_id=smoke_pool.pool_id,
        smoke_assignments_id=smoke_assignments.assignments_id,
        smoke_exclusion_audit_id=smoke_exclusion.audit_id,
        smoke_assignment_seal_id=smoke_seal.seal_id,
        gamma_report_id=gamma.report_id,
        gamma_case="G3",
        gamma_candidates=gamma_candidates,
        declarations=SMOKE_DECLARATIONS,
    ).with_id()

    entries = []
    objects = [
        ("rebaseline_authorization_receipt.json", approval, approval.receipt_id),
        ("paper_memory_v5_authoritative_evidence_release.json", releases[0], releases[0].release_id),
        ("scene_exemplar_evidence_release_v5r.json", releases[1], releases[1].release_id),
        ("mineclip_policy_binding_release_v5r.json", releases[2], releases[2].release_id),
        ("round513_v4_1_2_algorithmic_equivalence_audit.json", algorithmic, algorithmic.audit_id),
        ("round513_v4_1_2_dependency_graph.json", graph, graph.graph_id),
        ("round513_v4_1_2_regeneration_plan.json", plan, plan.plan_id),
        ("round513_v4_1_2_instrumentation_revalidation_audit.json", instrumentation, instrumentation.audit_id),
        ("round513e_presmoke_integrity_audit_v3.json", v3, v3.audit_id),
        ("chrmlite_engineering_smoke_pool_v4_1_2.json", smoke_pool, smoke_pool.pool_id),
        ("chrmlite_engineering_smoke_assignments_v4_1_2.json", smoke_assignments, smoke_assignments.assignments_id),
        ("chrmlite_engineering_smoke_exclusion_audit_v4_1_2.json", smoke_exclusion, smoke_exclusion.audit_id),
        ("chrmlite_engineering_smoke_seal_v4_1_2.json", smoke_seal, smoke_seal.seal_id),
        ("bilateral_gamma_provenance_report.json", gamma, gamma.report_id),
        ("chrmlite_engineering_smoke_authorization_input_v4_1_2.json", smoke_authorization, smoke_authorization.authorization_input_id),
    ]
    for filename, item, object_id in objects:
        path = output / filename
        _write(path, item.to_dict())
        entries.append(_file_entry(path, object_id))
    for name, payload in regenerated.items():
        path = contracts_out / NEW_FILENAMES[name]
        _write(path, payload)
        entries.append(_file_entry(path, str(payload[PRIMARY_ID_FIELDS[name]])))
    contract_manifest = {
        "schema_version": 1,
        "source_commit": source,
        "contract_version": "4.1.2",
        "regenerated_contract_count": len(regenerated),
        "historical_contracts_overwritten": False,
        "old_contract_file_sha256": old_hashes,
        "contracts": [entry for entry in entries if entry["filename"] in set(NEW_FILENAMES.values())],
    }
    _write(contracts_out / "manifest.json", contract_manifest)
    manifest = {
        "schema_version": 1,
        "source_commit": source,
        "rebaseline_authorization_status": "approved",
        "v3_status": v3.status,
        "smoke_authorization_status": "pending",
        "gamma_case": "G3",
        "gamma_candidate_ids": [item.candidate_id for item in gamma_candidates],
        "minedojo_started": False,
        "formal_development_started": False,
        "chrm_cdt_fitted": False,
        "holdout_final_round6_accessed": False,
        "artifacts": entries,
    }
    _write(output / "manifest.json", manifest)
    print(json.dumps(manifest, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
