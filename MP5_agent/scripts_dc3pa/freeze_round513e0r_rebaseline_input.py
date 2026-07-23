#!/usr/bin/env python3
"""Freeze E0R closure and DRAFT re-baseline input; never run MineDojo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round513e_rebaseline import (
    InvalidBindingRetirementRegistry,
    ProspectiveRebaselineImpactAudit,
    RetirementEntry,
    audit_actual_paper_memory_v5,
    build_authorization_input,
    build_candidate_release,
    transitive_dependency_ids,
)


PRIMARY_ID_KEYS = {
    "chrmlite_bilateral_retrieval_policy_v4_1.json": "policy_id",
    "chrmlite_decision_record_schema_v4_1.json": "schema_id",
    "chrmlite_development_collection_authorization.json": "authorization_id",
    "chrmlite_development_collection_blueprint.json": "blueprint_id",
    "chrmlite_development_seed_namespace.json": "namespace_id",
    "chrmlite_engineering_smoke_design.json": "design_id",
    "chrmlite_planner_output_schema_v4_1.json": "schema_id",
    "chrmlite_rule_type_registry_v4_1.json": "registry_id",
    "chrmlite_step_outcome_registry_v4_1.json": "registry_id",
    "chrmlite_collection_exclusion_registry.json": "registry_id",
    "chrmlite_support_and_degradation_policy.json": "policy_id",
    "cdt_replay_feasibility_blueprint.json": "blueprint_id",
    "chrmlite_behavior_equivalence_audit.json": "audit_id",
    "chrmlite_data_readiness_report.json": "report_id",
    "chrmlite_engineering_smoke_audit.json": "audit_id",
    "chrmlite_instrumentation_release_v4_1.json": "release_id",
    "round513cd_readiness_decision.json": "decision_id",
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


def _write_exclusive(path: Path, payload: object) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _full_hex_values(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        result: set[str] = set()
        for child in value.values():
            result.update(_full_hex_values(child))
        return result
    if isinstance(value, list):
        result = set()
        for child in value:
            result.update(_full_hex_values(child))
        return result
    if isinstance(value, str) and 8 <= len(value) <= 64:
        try:
            int(value, 16)
        except ValueError:
            return set()
        return {value}
    return set()


def _contract_nodes(*roots: Path) -> dict[str, set[str]]:
    nodes: dict[str, set[str]] = {}
    for root in roots:
        for path in sorted(root.glob("*.json")):
            key = PRIMARY_ID_KEYS.get(path.name)
            if key is None:
                continue
            payload = _load(path)
            object_id = str(payload.get(key, ""))
            references = _full_hex_values(payload) - {object_id}
            nodes[object_id] = references
    return nodes


def _assert_zero_result_evidence(
    readiness: Mapping[str, Any],
    v1: Mapping[str, Any],
    v2: Mapping[str, Any],
    smoke: Mapping[str, Any],
) -> None:
    required = {
        "formal collection closed": readiness.get("formal_collection_authorized") is False,
        "CDT not estimated": readiness.get("cdt_parameters_estimated") is False,
        "Holdout/final closed": readiness.get("holdout_or_final_accessed") is False,
        "V1 blocked": v1.get("eligible") is False,
        "V1 smoke not started": v1.get("phase_safety", {}).get("minedojo_smoke_started") is False,
        "V1 formal assignments absent": v1.get("phase_safety", {}).get("round513_formal_assignments_generated") is False,
        "V1 Holdout/final unread": v1.get("phase_safety", {}).get("holdout_or_final_content_read") is False,
        "V2 blocked": v2.get("eligible_for_preparation") is False,
        "V2 smoke not started": v2.get("minedojo_started") is False,
        "V2 formal Development not started": v2.get("formal_development_started") is False,
        "V2 Holdout/final unread": v2.get("holdout_final_accessed") is False,
        "engineering smoke not executed": smoke.get("executed") is False,
        "engineering smoke rows zero": smoke.get("unit_count") == 0,
        "formal fitting rows zero": smoke.get("formal_fitting_eligible_rows") == 0,
        "Memory writes zero": smoke.get("memory_writes") == 0,
        "Acquisition writes zero": smoke.get("acquisition_writes") == 0,
    }
    failures = [label for label, passed in required.items() if not passed]
    if failures:
        raise ValueError("Zero-result evidence failed: " + ", ".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--actual-acquisition-manifest", type=Path, required=True)
    parser.add_argument("--accepted-source-manifest", type=Path, required=True)
    parser.add_argument("--acquisition-root", type=Path, required=True)
    parser.add_argument("--lineage-input", type=Path, required=True)
    parser.add_argument("--lineage-audit", type=Path, required=True)
    parser.add_argument("--mineclip-policy", type=Path, required=True)
    parser.add_argument("--checkpoint-manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--mineclip-probe", type=Path, required=True)
    parser.add_argument("--rebuild-contract", type=Path, required=True)
    parser.add_argument("--build-stats", type=Path, required=True)
    parser.add_argument("--readonly-snapshot-smoke", type=Path, required=True)
    parser.add_argument("--blocked-v1-audit", type=Path, required=True)
    parser.add_argument("--blocked-v2-audit", type=Path, required=True)
    parser.add_argument("--readiness-decision", type=Path, required=True)
    parser.add_argument("--engineering-smoke-audit", type=Path, required=True)
    parser.add_argument("--contracts-root", type=Path, required=True)
    parser.add_argument("--readiness-root", type=Path, required=True)
    parser.add_argument("--invalid-mineclip-policy-id", required=True)
    parser.add_argument("--invalid-snapshot-manifest-id", required=True)
    parser.add_argument("--invalid-acquisition-manifest-id", required=True)
    parser.add_argument("--missing-scene-release-id", required=True)
    parser.add_argument("--historical-paper-memory-release-id", required=True)
    parser.add_argument("--quarantined-scene-release-id", required=True)
    args = parser.parse_args()

    source = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=ROOT.parent, text=True
    ).strip()
    if source != args.expected_source_commit:
        raise ValueError("Round 5.13E0R source commit mismatch")
    if subprocess.check_output(
        ("git", "status", "--short"), cwd=ROOT.parent, text=True
    ).strip():
        raise ValueError("Round 5.13E0R freezing requires a clean worktree")

    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Round 5.13E0R output root must be empty")

    closure = audit_actual_paper_memory_v5(
        source_commit=source,
        snapshot_manifest_path=args.snapshot_manifest,
        actual_acquisition_manifest_path=args.actual_acquisition_manifest,
        accepted_source_manifest_path=args.accepted_source_manifest,
        acquisition_root=args.acquisition_root,
        lineage_input_path=args.lineage_input,
        lineage_audit_path=args.lineage_audit,
        mineclip_policy_path=args.mineclip_policy,
        checkpoint_manifest_path=args.checkpoint_manifest,
        checkpoint_path=args.checkpoint,
        mineclip_probe_path=args.mineclip_probe,
        rebuild_contract_path=args.rebuild_contract,
        build_stats_path=args.build_stats,
        readonly_snapshot_smoke_path=args.readonly_snapshot_smoke,
    )
    if closure.status != "ACTUAL_PROVENANCE_CLOSED":
        _write_exclusive(output / "actual_paper_memory_v5_provenance_closure_audit.json", closure.to_dict())
        raise ValueError("Actual V5 provenance is not closed")

    readiness = _load(args.readiness_decision)
    v1 = _load(args.blocked_v1_audit)
    v2 = _load(args.blocked_v2_audit)
    smoke = _load(args.engineering_smoke_audit)
    _assert_zero_result_evidence(readiness, v1, v2, smoke)

    invalid_roots = {
        args.invalid_mineclip_policy_id,
        args.missing_scene_release_id,
        args.historical_paper_memory_release_id,
    }
    nodes = _contract_nodes(args.contracts_root, args.readiness_root)
    dependent_ids = transitive_dependency_ids(nodes=nodes, invalid_roots=invalid_roots)
    required_objects = [
        (args.invalid_mineclip_policy_id, "invalid_mineclip_reference", "unresolvable historical policy identity"),
        (args.invalid_snapshot_manifest_id, "invalid_expected_snapshot_manifest", "historical expected manifest is unavailable and is not the actual manifest"),
        (args.invalid_acquisition_manifest_id, "invalid_expected_acquisition_manifest", "historical expected snapshot-local binding; preserved only as source-build evidence"),
        (args.missing_scene_release_id, "missing_scene_release_reference", "historical Scene release is unresolvable"),
        (args.quarantined_scene_release_id, "quarantined_scene_release", "incorrect S2 release remains unusable"),
    ]
    required_objects.extend(
        (object_id, "dependent_invalid_cd_object", "directly or transitively binds invalid evidence")
        for object_id in dependent_ids
    )
    retirement = InvalidBindingRetirementRegistry(
        source_commit=source,
        entries=tuple(
            RetirementEntry(
                object_id=object_id,
                object_kind=kind,
                reason=reason,
                identity_complete=len(object_id) == 64,
            )
            for object_id, kind, reason in required_objects
        ),
    ).with_id()

    impact = ProspectiveRebaselineImpactAudit(
        source_commit=source,
        invalid_binding_retirement_registry_id=retirement.registry_id,
        readiness_decision_id=str(readiness["decision_id"]),
        readiness_decision_file_sha256=_sha(args.readiness_decision),
        blocked_v1_audit_id=str(v1["audit_id"]),
        blocked_v1_audit_file_sha256=_sha(args.blocked_v1_audit),
        blocked_v2_audit_id=str(v2["audit_id"]),
        blocked_v2_audit_file_sha256=_sha(args.blocked_v2_audit),
        engineering_smoke_audit_id=str(smoke["audit_id"]),
        engineering_smoke_audit_file_sha256=_sha(args.engineering_smoke_audit),
        engineering_smoke_rows_under_invalid_contracts=0,
        formal_v4_1_development_rows=0,
        chrm_cdt_fitted_artifact_count=0,
        holdout_final_row_count=0,
        prospective_rebaseline_justified=True,
    ).with_id()
    paper_candidate = build_candidate_release(
        release_name="PaperMemoryV5ActualArtifactCandidateRelease",
        closure=closure,
    )
    scene_candidate = build_candidate_release(
        release_name="SceneExemplarActualArtifactCandidateRelease",
        closure=closure,
    )

    preliminary = (
        ("actual_paper_memory_v5_provenance_closure_audit.json", closure.to_dict(), closure.audit_id),
        ("invalid_binding_retirement_registry.json", retirement.to_dict(), retirement.registry_id),
        ("prospective_rebaseline_impact_audit.json", impact.to_dict(), impact.audit_id),
        ("paper_memory_v5_actual_artifact_candidate_release.json", paper_candidate.to_dict(), paper_candidate.release_id),
        ("scene_exemplar_actual_artifact_candidate_release.json", scene_candidate.to_dict(), scene_candidate.release_id),
    )
    entries = []
    file_hashes: dict[str, str] = {}
    for filename, payload, object_id in preliminary:
        path = output / filename
        _write_exclusive(path, payload)
        file_hashes[filename] = _sha(path)
        entries.append({"filename": filename, "id": object_id, "sha256": file_hashes[filename]})

    authorization = build_authorization_input(
        source_commit=source,
        closure=closure,
        closure_file_sha256=file_hashes[preliminary[0][0]],
        retirement=retirement,
        retirement_file_sha256=file_hashes[preliminary[1][0]],
        impact=impact,
        impact_file_sha256=file_hashes[preliminary[2][0]],
        paper_candidate=paper_candidate,
        paper_candidate_file_sha256=file_hashes[preliminary[3][0]],
        scene_candidate=scene_candidate,
        scene_candidate_file_sha256=file_hashes[preliminary[4][0]],
    )
    authorization_path = output / "prospective_memory_rebaseline_authorization_input.json"
    _write_exclusive(authorization_path, authorization.to_dict())
    authorization_sha = _sha(authorization_path)
    entries.append(
        {
            "filename": authorization_path.name,
            "id": authorization.authorization_input_id,
            "sha256": authorization_sha,
        }
    )
    manifest = {
        "schema_version": 1,
        "source_commit": source,
        "actual_provenance_status": closure.status,
        "embedding_evidence_path": closure.embedding_evidence_path,
        "rebaseline_authorization_status": "pending",
        "contract_regeneration_permitted": False,
        "minedojo_started": False,
        "formal_development_started": False,
        "chrm_cdt_fitted": False,
        "holdout_final_round6_accessed": False,
        "dependent_invalid_object_ids": list(dependent_ids),
        "artifacts": entries,
    }
    _write_exclusive(output / "manifest.json", manifest)
    print(json.dumps(manifest, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
