#!/usr/bin/env python3
"""Freeze E5F audits and a pending diagnostic authorization input.

This command is offline-only. It never imports or starts MineDojo.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round513_instrumentation import (  # noqa: E402
    BilateralEvidenceV4_1,
    BilateralMatchV4_1,
)
from dc3pa.experiments.round513e2h import file_sha256  # noqa: E402
from dc3pa.experiments.round513e5 import (  # noqa: E402
    ActionSignatureCanonicalizationRegistryV4_1_3,
    ActionSignatureProvenanceAuditV4_1_3,
    ActionTransitionLabelPolicyV4_1_3,
    AtomicDecisionStoreContractV4_1_3,
    CHRMLiteInstrumentationRuntimeReleaseV4_1_3,
    DecisionRecordSchemaV4_1_3,
    DiagnosticSeedStrategyDecisionInput,
    DualLevelOutcomeContractV4_1_3,
    FindBoundedFailurePolicyV4_1_3,
    FindObservationEvidenceContractV4_1_3,
    OutcomeEvidenceRegistryV4_1_3,
    Round513E4FailureAttributionAudit,
    Round513E4ObservationGapCloseout,
    Round513E4ScientificUseRestriction,
    Round513E5DiagnosticAuthorizationInput,
    Round513E5LabelFreeCompatibilityAudit,
    Round513E5ObservationLabelHardeningAudit,
    Round513E5SignatureNormalizationAudit,
    SceneCompatibilityNormalizationPolicyV4_1_3,
    TerminalGoalLabelPolicyV4_1_3,
    canonical_action_signature_v4_1_3,
    canonical_sha256,
    canonicalize_bilateral_evidence_v4_1_3,
)


DIAGNOSTIC_TASKS = (
    ("mine sapling", "mine_sapling.json"),
    ("mine iron ore", "mine_iron_ore.json"),
    ("mine log", "mine_log.json"),
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write(path: Path, payload: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _match(payload: dict[str, Any]) -> BilateralMatchV4_1:
    return BilateralMatchV4_1(
        str(payload["exemplar_id"]),
        str(payload["action_signature"]),
        float(payload["score"]),
    )


def _environment(payload: dict[str, Any]) -> BilateralEvidenceV4_1:
    return BilateralEvidenceV4_1(
        query_observation_id=str(payload["query_observation_id"]),
        query_observation_hash=str(payload["query_observation_hash"]),
        action_signature=str(payload["action_signature"]),
        compatible_pool=tuple(_match(item) for item in payload["compatible_pool"]),
        incompatible_pool=tuple(_match(item) for item in payload["incompatible_pool"]),
        positive=tuple(_match(item) for item in payload["positive"]),
        negative=tuple(_match(item) for item in payload["negative"]),
        coverage_positive=float(payload["coverage_positive"]),
        coverage_negative=float(payload["coverage_negative"]),
        contrast=(float(payload["contrast"]) if payload["contrast"] is not None else None),
        raw_state=str(payload["raw_state"]),
    )


def _label_free_audit(
    record_roots: list[Path],
    closeout_id: str,
    policy_id: str,
) -> tuple[Round513E5LabelFreeCompatibilityAudit, bool]:
    records: list[dict[str, Any]] = []
    for root in record_roots:
        for path in sorted(root.glob("outputs/*/audit_only_ambiguous/*.json")):
            records.append(json.loads(path.read_text(encoding="utf-8")))
    if len(records) != 9:
        raise ValueError(f"Expected nine frozen E4 records, found {len(records)}")
    rows = []
    score_hashes_equal = True
    for record in records:
        pre = record["pre"]
        raw = _environment(pre["environment"])
        action = pre["action"]
        canonical = canonicalize_bilateral_evidence_v4_1_3(raw, action=action)
        before = sorted(
            (item.exemplar_id, item.score)
            for item in (*raw.compatible_pool, *raw.incompatible_pool)
        )
        after = sorted(
            (item.exemplar_id, item.score)
            for item in (*canonical.compatible_pool, *canonical.incompatible_pool)
        )
        score_hashes_equal = score_hashes_equal and before == after
        rows.append(
            {
                "task": pre["binding"]["task"],
                "raw_action_signature": raw.action_signature,
                "canonical_action_signature": canonical.action_signature,
                "raw_compatible_pool_size": len(raw.compatible_pool),
                "canonical_compatible_pool_size": len(canonical.compatible_pool),
                "canonical_incompatible_pool_size": len(canonical.incompatible_pool),
                "raw_coverage_positive": raw.coverage_positive,
                "canonical_coverage_positive": canonical.coverage_positive,
                "raw_coverage_negative": raw.coverage_negative,
                "canonical_coverage_negative": canonical.coverage_negative,
                "candidate_b_raw_environment_state": raw.raw_state,
                "canonicalized_environment_state": canonical.raw_state,
                "visual_score_multiset_sha256": canonical_sha256(before),
            }
        )
    conclusion = (
        "canonical_compatible_coverage_present"
        if any(row["canonical_compatible_pool_size"] for row in rows)
        else "memory_compatible_coverage_still_absent"
    )
    return (
        Round513E5LabelFreeCompatibilityAudit(
            source_closeout_id=closeout_id,
            signature_policy_id=policy_id,
            rows=tuple(rows),
            outcome_labels_used=False,
            gamma_changed=False,
            conclusion=conclusion,
        ).with_id(),
        score_hashes_equal,
    )


def _diagnostic_design(formal_root: Path, source: str) -> dict[str, Any]:
    catalog_path = formal_root / "final_task_catalog.csv"
    with catalog_path.open(encoding="utf-8", newline="") as handle:
        rows = {row["task"]: row for row in csv.DictReader(handle)}
    assignments = []
    for order, (task, asset_name) in enumerate(DIAGNOSTIC_TASKS):
        if task not in rows:
            raise ValueError(f"Formal catalog does not contain {task}")
        asset = formal_root / "creative_task_jsons" / asset_name
        if not asset.is_file():
            raise FileNotFoundError(asset)
        assignments.append(
            {
                "order": order,
                "formal_task": task,
                "formal_difficulty": rows[task]["difficulty"],
                "asset": f"creative_task_jsons/{asset_name}",
                "asset_sha256": file_sha256(asset),
                "seed_strategy": "PENDING_ZYF_D1_OR_D2",
                "seed_published": False,
                "diagnostic_only": True,
                "formal_fitting_eligible": False,
                "channel_calibration_eligible": False,
                "chrm_fitting_eligible": False,
                "cdt_identification_eligible": False,
                "holdout_eligible": False,
                "final_evaluation_eligible": False,
            }
        )
    payload = {
        "contract_type": "Round513E5DiagnosticDesign",
        "source_commit": source,
        "namespace": "dc3pa-round513e5-diagnostic-only-pending-seed-strategy",
        "assignments": assignments,
        "assignment_seal_id": "PENDING_ZYF_SEED_DECISION",
        "full_9_assignment_rerun_permitted": False,
        "minedojo_execution_permitted": False,
    }
    payload["design_id"] = canonical_sha256(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--public-e4-closeout", type=Path, required=True)
    parser.add_argument("--e4-record-root", type=Path, action="append", required=True)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--reference-binding", type=Path, required=True)
    parser.add_argument("--synthetic-test-count", type=int, required=True)
    parser.add_argument("--minedojo-test-count", type=int, required=True)
    args = parser.parse_args()

    source = _git("rev-parse", "HEAD")
    if source != args.source_commit:
        raise ValueError("E5 source commit does not match HEAD")
    if _git("status", "--porcelain"):
        raise ValueError("E5 freeze requires a clean worktree")
    args.output.mkdir(parents=True, mode=0o700)
    if any(args.output.iterdir()):
        raise ValueError("E5 output must be empty")

    public = json.loads(args.public_e4_closeout.read_text(encoding="utf-8"))
    closeout = Round513E4ObservationGapCloseout(
        source_closeout_id=str(public["closeout_id"])
    ).with_id()
    restriction = Round513E4ScientificUseRestriction(closeout.closeout_id).with_id()
    attribution = Round513E4FailureAttributionAudit(closeout.closeout_id).with_id()

    dual = DualLevelOutcomeContractV4_1_3().with_id()
    action_policy = ActionTransitionLabelPolicyV4_1_3().with_id()
    goal_policy = TerminalGoalLabelPolicyV4_1_3().with_id()
    find_contract = FindObservationEvidenceContractV4_1_3().with_id()
    bounded_policy = FindBoundedFailurePolicyV4_1_3().with_id()
    outcome_registry = OutcomeEvidenceRegistryV4_1_3(
        dual.contract_id,
        action_policy.policy_id,
        goal_policy.policy_id,
        find_contract.contract_id,
        bounded_policy.policy_id,
    ).with_id()

    signature_registry = ActionSignatureCanonicalizationRegistryV4_1_3().with_id()
    provenance = ActionSignatureProvenanceAuditV4_1_3(
        registry_id=signature_registry.registry_id,
        audited_tokens=(
            "tree", "wood", "log", "oak_log", "redstone", "redstone_ore",
            "iron", "iron_ore", "iron_ingot", "sapling", "cobblestone", "stone",
            "crafting_table", "wooden_pickaxe",
        ),
        required_forbidden_pairs=(("redstone", "redstone_ore"), ("iron_ore", "iron_ingot")),
        raw_lineage_preserved=True,
        outcome_labels_used=False,
        status="PASS",
    ).with_id()
    normalization = SceneCompatibilityNormalizationPolicyV4_1_3(
        registry_id=signature_registry.registry_id
    ).with_id()
    compatibility, score_hash_unchanged = _label_free_audit(
        args.e4_record_root,
        closeout.closeout_id,
        normalization.policy_id,
    )
    signature_audit = Round513E5SignatureNormalizationAudit(
        signature_registry_id=signature_registry.registry_id,
        provenance_audit_id=provenance.audit_id,
        normalization_policy_id=normalization.policy_id,
        compatibility_audit_id=compatibility.audit_id,
        visual_score_hash_unchanged=score_hash_unchanged,
        candidate_b_unchanged=True,
        gamma_unchanged=True,
        outcome_labels_used=False,
        status="PASS" if score_hash_unchanged else "BLOCKED",
    ).with_id()
    observation_audit = Round513E5ObservationLabelHardeningAudit(
        observation_closeout_id=closeout.closeout_id,
        outcome_registry_id=outcome_registry.registry_id,
        find_evidence_contract_id=find_contract.contract_id,
        bounded_failure_policy_id=bounded_policy.policy_id,
        synthetic_test_count=args.synthetic_test_count,
        minedojo_import_test_count=args.minedojo_test_count,
        relevant_minedojo_skips=0,
    ).with_id()
    record_schema = DecisionRecordSchemaV4_1_3().with_id()
    store_contract = AtomicDecisionStoreContractV4_1_3().with_id()

    binding = json.loads(args.reference_binding.read_text(encoding="utf-8"))
    runtime = CHRMLiteInstrumentationRuntimeReleaseV4_1_3(
        source_commit=source,
        observation_hardening_audit_id=observation_audit.audit_id,
        signature_normalization_audit_id=signature_audit.audit_id,
        outcome_registry_id=outcome_registry.registry_id,
        signature_registry_id=signature_registry.registry_id,
        decision_record_schema_id=record_schema.schema_id,
        atomic_store_contract_id=store_contract.contract_id,
        paper_memory_release_id=binding["paper_memory_release_id"],
        mineclip_policy_id=binding["mineclip_policy_id"],
        scene_exemplar_release_id=binding["scene_exemplar_release_id"],
        controller_contract_id=binding["controller_id"],
        evaluator_contract_id=binding["evaluator_id"],
        technical_retry_policy_id=binding["technical_retry_policy_id"],
        process_cleanup_policy_id=binding["process_cleanup_policy_id"],
    ).with_id()
    seed_decision = DiagnosticSeedStrategyDecisionInput(source_commit=source).with_id()
    design = _diagnostic_design(args.formal_root, source)
    authorization = Round513E5DiagnosticAuthorizationInput(
        source_commit=source,
        runtime_release_id=runtime.release_id,
        outcome_registry_id=outcome_registry.registry_id,
        signature_registry_id=signature_registry.registry_id,
        signature_audit_id=signature_audit.audit_id,
        compatibility_audit_id=compatibility.audit_id,
        decision_record_schema_id=record_schema.schema_id,
        atomic_store_contract_id=store_contract.contract_id,
        diagnostic_seed_decision_input_id=seed_decision.decision_input_id,
        diagnostic_design_id=design["design_id"],
    ).with_id()

    artifacts = {
        "e4_observation_gap_closeout.json": (closeout.to_dict(), "closeout_id"),
        "e4_scientific_use_restriction.json": (restriction.to_dict(), "restriction_id"),
        "e4_failure_attribution_audit.json": (attribution.to_dict(), "audit_id"),
        "dual_level_outcome_contract_v4_1_3.json": (dual.to_dict(), "contract_id"),
        "action_transition_label_policy_v4_1_3.json": (action_policy.to_dict(), "policy_id"),
        "terminal_goal_label_policy_v4_1_3.json": (goal_policy.to_dict(), "policy_id"),
        "find_observation_evidence_contract_v4_1_3.json": (find_contract.to_dict(), "contract_id"),
        "find_bounded_failure_policy_v4_1_3.json": (bounded_policy.to_dict(), "policy_id"),
        "outcome_evidence_registry_v4_1_3.json": (outcome_registry.to_dict(), "registry_id"),
        "action_signature_registry_v4_1_3.json": (signature_registry.to_dict(), "registry_id"),
        "action_signature_provenance_audit_v4_1_3.json": (provenance.to_dict(), "audit_id"),
        "scene_compatibility_normalization_policy_v4_1_3.json": (normalization.to_dict(), "policy_id"),
        "label_free_compatibility_audit.json": (compatibility.to_dict(), "audit_id"),
        "observation_label_hardening_audit.json": (observation_audit.to_dict(), "audit_id"),
        "signature_normalization_audit.json": (signature_audit.to_dict(), "audit_id"),
        "decision_record_schema_v4_1_3.json": (record_schema.to_dict(), "schema_id"),
        "atomic_decision_store_contract_v4_1_3.json": (store_contract.to_dict(), "contract_id"),
        "instrumentation_runtime_release_v4_1_3.json": (runtime.to_dict(), "release_id"),
        "diagnostic_seed_strategy_decision_input.json": (seed_decision.to_dict(), "decision_input_id"),
        "diagnostic_design.json": (design, "design_id"),
        "diagnostic_authorization_input.json": (authorization.to_dict(), "authorization_input_id"),
    }
    manifest_rows = []
    for filename, (payload, id_field) in artifacts.items():
        path = args.output / filename
        _write(path, payload)
        manifest_rows.append(
            {"filename": filename, "id": payload[id_field], "sha256": file_sha256(path)}
        )
    manifest = {
        "source_commit": source,
        "phase": "PENDING_ZYF_DIAGNOSTIC_SEED_DECISION_AND_AUTHORIZATION",
        "minedojo_execution_permitted": False,
        "full_9_assignment_rerun_permitted": False,
        "candidate_b_unchanged": True,
        "gamma_unchanged": True,
        "historical_records_relabelled": False,
        "artifacts": manifest_rows,
    }
    manifest["manifest_id"] = canonical_sha256(manifest)
    _write(args.output / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "manifest_id": manifest["manifest_id"],
                "runtime_release_id": runtime.release_id,
                "diagnostic_seed_decision_input_id": seed_decision.decision_input_id,
                "diagnostic_authorization_input_id": authorization.authorization_input_id,
                "compatibility_conclusion": compatibility.conclusion,
                "minedojo_started": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
