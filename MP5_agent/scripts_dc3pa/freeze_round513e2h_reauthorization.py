#!/usr/bin/env python3
"""Freeze the approved E2H runtime release and pending smoke reauthorization."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round513e2h import (  # noqa: E402
    ADAPTER_VERSION,
    CHRMLiteEngineeringSmokeAssignmentsV4_1_2_R1,
    CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2_R1,
    CHRMLiteEngineeringSmokeExclusionAuditV4_1_2_R1,
    CHRMLiteEngineeringSmokeRuntimeReleaseV4_1_2_R1,
    CHRMLiteEngineeringSmokeSealV4_1_2_R1,
    ContractCompatibilityEntry,
    ProcessCleanupPolicyV4_1_2_R1,
    Round513E2ContractCompatibilityReleaseR1,
    Round513E2SourceHardeningAudit,
    SmokeAssignmentScientificPayloadEquivalenceAudit,
    SmokeAssignmentV4_1_2_R1,
    TechnicalRetryPolicyV4_1_2_R1,
    TrackERunBindingV4_1_2_R1,
    canonical_sha256,
    dataclass_schema_id,
    file_sha256,
    load_versioned_contract,
    ordered_scientific_payload_root,
)


DECISION_INPUT_ID = "e5c2d8df67d3448a3c7792fac1abc900033cb2b932eeefee408d65a15b3035ab"
DECISION_INPUT_SHA256 = "cdc4997ab0aab78f59a839fbe1c3e8738630f9f8d9d827db17e01b465b998eaf"
GAMMA_CANDIDATE_B = "0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f"


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write(path: Path, payload: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _verify_hashed(payload: dict, id_field: str, expected: str | None = None) -> str:
    object_id = str(payload[id_field])
    if expected is not None and object_id != expected:
        raise ValueError(f"{id_field} does not match the approved object")
    canonical = dict(payload)
    canonical.pop(id_field)
    if canonical_sha256(canonical) != object_id:
        raise ValueError(f"{id_field} canonical hash mismatch")
    return object_id


def _normalize_statement(value: str) -> str:
    return " ".join(value.split())


def _validate_policy_approval(value: str) -> None:
    normalized = _normalize_statement(value)
    if any(token in normalized for token in ("<", ">", "[...]", "|")):
        raise ValueError("Policy approval still contains unresolved placeholders")
    required_literals = (
        DECISION_INPUT_ID,
        DECISION_INPUT_SHA256,
        "retry_candidate=T1_one_retry",
        'allowed_technical_failure_categories=["environment_start_failure","seed_application_failure","provider_transport_failure","provider_empty_response"]',
        "maximum_attempts_per_technical_category=2",
        "total_maximum_attempts=2",
        "backoff_seconds=30",
        "cleanup_candidate=C1_scoped_process_group_cleanup",
        "cleanup_grace_seconds=20",
        'campaign_owned_ports=["runtime-allocated ports recorded in the campaign launch ownership ledger"]',
        'campaign_owned_lock_patterns=["lock files created and recorded by the campaign launch ownership ledger"]',
        'campaign_owned_display_sessions=["DISPLAY sessions created and recorded by the campaign launch ownership ledger"]',
        "scientific_success_retries=0",
        "scientific_failure_retries=0",
        "technical retry is permitted only before any environment action has started",
        "approved_by=ZYF",
    )
    missing = [literal for literal in required_literals if literal not in normalized]
    if missing:
        raise ValueError(f"Policy approval is missing frozen selections: {missing}")


def _source_commit() -> str:
    source = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT.parent, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT.parent, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if dirty:
        raise ValueError("E2H source freeze requires a clean worktree")
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy-decision-input", type=Path, required=True)
    parser.add_argument("--policy-approval", type=Path, required=True)
    parser.add_argument("--supersession", type=Path, required=True)
    parser.add_argument("--old-assignments", type=Path, required=True)
    parser.add_argument("--old-exclusion", type=Path, required=True)
    parser.add_argument("--prior-integrity-audit", type=Path, required=True)
    parser.add_argument("--v41-contract-root", type=Path, required=True)
    parser.add_argument("--v412-contract-root", type=Path, required=True)
    parser.add_argument("--paper-memory-release", type=Path, required=True)
    parser.add_argument("--scene-release", type=Path, required=True)
    args = parser.parse_args()

    source = _source_commit()
    if args.output.exists():
        raise FileExistsError("E2H reauthorization output already exists")

    decision = _load(args.policy_decision_input)
    _verify_hashed(decision, "decision_input_id", DECISION_INPUT_ID)
    if file_sha256(args.policy_decision_input) != DECISION_INPUT_SHA256:
        raise ValueError("Policy Decision Input file SHA-256 mismatch")
    approval_text = args.policy_approval.read_text(encoding="utf-8")
    _validate_policy_approval(approval_text)
    approval_sha = file_sha256(args.policy_approval)

    supersession = _load(args.supersession)
    supersession_id = _verify_hashed(supersession, "decision_id")
    old_assignments = _load(args.old_assignments)
    old_exclusion = _load(args.old_exclusion)
    prior_integrity = _load(args.prior_integrity_audit)
    if not (
        prior_integrity.get("snapshot_guard_passed") is True
        and prior_integrity.get("write_probe_rejected") is True
        and prior_integrity.get("minedojo_smoke_started") is False
    ):
        raise ValueError("Prior full-environment integrity evidence is incomplete")

    retry_policy = TechnicalRetryPolicyV4_1_2_R1(
        source_commit=source,
        decision_input_id=DECISION_INPUT_ID,
        decision_input_file_sha256=DECISION_INPUT_SHA256,
        approval_statement_sha256=approval_sha,
        retry_candidate="T1_one_retry",
        allowed_technical_failure_categories=(
            "environment_start_failure", "seed_application_failure",
            "provider_transport_failure", "provider_empty_response",
        ),
        maximum_attempts_per_technical_category=2,
        total_maximum_attempts=2,
        backoff_seconds=30,
        scientific_success_retries=0,
        scientific_failure_retries=0,
        pre_action_proof_required=True,
        attempt_isolation_required=True,
        technical_partial_record_disposition="technical_quarantine",
        unclassified_technical_failure_policy="stop_immediately",
    ).with_id()
    cleanup_policy = ProcessCleanupPolicyV4_1_2_R1(
        source_commit=source,
        decision_input_id=DECISION_INPUT_ID,
        decision_input_file_sha256=DECISION_INPUT_SHA256,
        approval_statement_sha256=approval_sha,
        cleanup_candidate="C1_scoped_process_group_cleanup",
        cleanup_grace_seconds=20,
        campaign_owned_ports=(
            "runtime-allocated ports recorded in the campaign launch ownership ledger",
        ),
        campaign_owned_lock_patterns=(
            "lock files created and recorded by the campaign launch ownership ledger",
        ),
        campaign_owned_display_sessions=(
            "DISPLAY sessions created and recorded by the campaign launch ownership ledger",
        ),
        required_target_checks=(
            "MineDojo", "Minecraft", "Mineflayer", "bridge",
            "ports", "lock_files", "display_sessions",
        ),
        launch_ownership_ledger_required=True,
        unrelated_process_kill_permitted=False,
        residual_process_policy="stop_if_campaign_owned_residual_remains",
        output_directory_policy="exclusive_per_attempt_then_atomic_disposition",
    ).with_id()

    contract_specs = {
        "planner_schema": (args.v41_contract_root / "chrmlite_planner_output_schema_v4_1.json", "schema_id"),
        "rule_registry": (args.v41_contract_root / "chrmlite_rule_type_registry_v4_1.json", "registry_id"),
        "step_outcome_registry": (args.v41_contract_root / "chrmlite_step_outcome_registry_v4_1.json", "registry_id"),
        "support_policy": (args.v41_contract_root / "chrmlite_support_and_degradation_policy.json", "policy_id"),
        "bilateral_retrieval_policy": (args.v412_contract_root / "chrmlite_bilateral_retrieval_policy_v4_1_2.json", "policy_id"),
        "decision_record_schema": (args.v412_contract_root / "chrmlite_decision_record_schema_v4_1_2.json", "schema_id"),
        "instrumentation_release": (args.v412_contract_root / "chrmlite_instrumentation_release_v4_1_2.json", "release_id"),
    }
    adapters = {}
    entries = []
    for contract_type, (path, id_field) in contract_specs.items():
        payload = _load(path)
        adapter = load_versioned_contract(
            path,
            contract_type=contract_type,
            expected_contract_id=str(payload[id_field]),
            expected_file_sha256=file_sha256(path),
        )
        adapters[contract_type] = adapter
        entries.append(ContractCompatibilityEntry(
            contract_type=contract_type,
            filename=path.name,
            contract_id=adapter.raw_contract_id,
            file_sha256=adapter.raw_file_sha256,
            contract_version=adapter.contract_version,
            authoring_source_commit=adapter.authoring_source_commit,
            runtime_adapter_version=ADAPTER_VERSION,
            allowed_execution_source_commits=(source,),
        ))
    compatibility = Round513E2ContractCompatibilityReleaseR1(
        source_commit=source,
        scientific_method_version="V4.1.2",
        runtime_binding_revision="R1",
        entries=tuple(entries),
    ).with_id()
    for adapter in adapters.values():
        compatibility.require_compatible(adapter, source)

    source_audit = Round513E2SourceHardeningAudit(
        source_commit=source,
        supersession_decision_id=supersession_id,
        compatibility_release_id=compatibility.release_id,
        technical_retry_policy_id=retry_policy.policy_id,
        process_cleanup_policy_id=cleanup_policy.policy_id,
        adapter_version=ADAPTER_VERSION,
        raw_identity_round_trip_passed=True,
        canonical_hash_before_adaptation_passed=True,
        source_provenance_separation_passed=True,
        exact_compatibility_allowlist_passed=True,
        controller_evaluator_budget_validation_passed=True,
        snapshot_guard_passed=True,
        paper_memory_write_probe_rejected=True,
        relevant_skips=0,
        minedojo_launch_count=0,
        scientific_method_changed=False,
        gamma_changed=False,
    ).with_id()
    run_binding_schema_id = dataclass_schema_id(
        TrackERunBindingV4_1_2_R1,
        invariants={
            "scientific_method_version": "V4.1.2",
            "runtime_binding_revision": "R1",
            "engineering_only": True,
            "gamma_candidate": "B",
        },
    )
    assignment_schema_id = dataclass_schema_id(
        SmokeAssignmentV4_1_2_R1,
        invariants={
            "contract_version": "4.1.2-R1",
            "engineering_only": True,
            "all_fit_holdout_final_eligibility": False,
        },
    )
    runtime_release = CHRMLiteEngineeringSmokeRuntimeReleaseV4_1_2_R1(
        source_commit=source,
        compatibility_release_id=compatibility.release_id,
        technical_retry_policy_id=retry_policy.policy_id,
        process_cleanup_policy_id=cleanup_policy.policy_id,
        source_hardening_audit_id=source_audit.audit_id,
        run_binding_schema_id=run_binding_schema_id,
        assignment_schema_id=assignment_schema_id,
        decision_store_revision="orthogonal-disposition-r1",
        preflight_before_environment=True,
        controller_evaluator_budget_validation=True,
    ).with_id()

    new_rows = tuple(
        SmokeAssignmentV4_1_2_R1.from_legacy(item, source_commit=source)
        for item in old_assignments["assignments"]
    )
    for row in new_rows:
        task_file = ROOT / row.task_path_label
        if file_sha256(task_file) != row.task_file_sha256:
            raise ValueError(f"Task file changed after the original seal: {row.task_path_label}")
    assignments = CHRMLiteEngineeringSmokeAssignmentsV4_1_2_R1(
        source_commit=source,
        legacy_assignments_id=str(old_assignments["assignments_id"]),
        pool_id=str(old_assignments["pool_id"]),
        runtime_release_id=runtime_release.release_id,
        technical_retry_policy_id=retry_policy.policy_id,
        process_cleanup_policy_id=cleanup_policy.policy_id,
        assignments=new_rows,
    ).with_id()
    old_root = ordered_scientific_payload_root(old_assignments["assignments"])
    new_root = canonical_sha256([
        {"order": index, **item.scientific_payload()}
        for index, item in enumerate(new_rows)
    ])
    equivalence = SmokeAssignmentScientificPayloadEquivalenceAudit(
        source_commit=source,
        old_assignments_id=str(old_assignments["assignments_id"]),
        new_assignments_id=assignments.assignments_id,
        old_ordered_scientific_payload_root=old_root,
        new_ordered_scientific_payload_root=new_root,
        assignment_count=len(new_rows),
        tasks_changed=0,
        seeds_changed=0,
        order_changed=0,
        status="EQUIVALENT" if old_root == new_root else "MISMATCH",
    ).with_id()
    if equivalence.status != "EQUIVALENT":
        raise ValueError("Old/new task-seed-order payloads are not equivalent")
    exclusion = CHRMLiteEngineeringSmokeExclusionAuditV4_1_2_R1(
        source_commit=source,
        assignments_id=assignments.assignments_id,
        prior_exclusion_audit_id=str(old_exclusion["audit_id"]),
        acquisition_overlap_count=int(old_exclusion["acquisition_overlap_count"]),
        historical_development_overlap_count=int(old_exclusion["historical_development_overlap_count"]),
        previous_smoke_overlap_count=int(old_exclusion["previous_smoke_overlap_count"]),
        future_formal_v412_overlap_count=int(old_exclusion["future_formal_v412_overlap_count"]),
        holdout_overlap_count=int(old_exclusion["holdout_overlap_count"]),
        final_overlap_count=int(old_exclusion["final_overlap_count"]),
        proof_method="legacy_cryptographic_namespace_proof_rebound_to_equivalent_payload",
        eligible=bool(old_exclusion["eligible"]),
    ).with_id()
    assignment_payloads = [item.to_dict() for item in new_rows]
    seal = CHRMLiteEngineeringSmokeSealV4_1_2_R1(
        source_commit=source,
        compatibility_release_id=compatibility.release_id,
        runtime_release_id=runtime_release.release_id,
        technical_retry_policy_id=retry_policy.policy_id,
        process_cleanup_policy_id=cleanup_policy.policy_id,
        assignments_id=assignments.assignments_id,
        assignments_root_sha256=canonical_sha256(assignment_payloads),
        ordered_scientific_payload_root=new_root,
        exclusion_audit_id=exclusion.audit_id,
        equivalence_audit_id=equivalence.audit_id,
        assignment_count=9,
        permanently_engineering_only=True,
        fitting_ineligible=True,
        sealed=True,
    ).with_id()

    paper = _load(args.paper_memory_release)
    scene = _load(args.scene_release)
    retrieval = adapters["bilateral_retrieval_policy"].raw_contract_payload
    planner = adapters["planner_schema"].raw_contract_payload
    outcome = adapters["step_outcome_registry"].raw_contract_payload
    authorization = CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2_R1(
        source_commit=source,
        runtime_release_id=runtime_release.release_id,
        compatibility_release_id=compatibility.release_id,
        run_binding_schema_id=run_binding_schema_id,
        assignment_schema_id=assignment_schema_id,
        smoke_assignments_id=assignments.assignments_id,
        smoke_assignment_seal_id=seal.seal_id,
        smoke_exclusion_audit_id=exclusion.audit_id,
        scientific_payload_equivalence_audit_id=equivalence.audit_id,
        technical_retry_policy_id=retry_policy.policy_id,
        process_cleanup_policy_id=cleanup_policy.policy_id,
        paper_memory_release_id=str(paper["release_id"]),
        paper_memory_root=str(paper["snapshot_root_sha256"]),
        mineclip_policy_id=str(retrieval["mineclip_policy_id"]),
        scene_exemplar_release_id=str(scene["release_id"]),
        planner_prompt_id=canonical_sha256(planner["prompt_template"]),
        planner_schema_id=str(planner["schema_id"]),
        planner_parser_id=canonical_sha256(planner["parser_policy"]),
        rule_registry_id=adapters["rule_registry"].raw_contract_id,
        bilateral_policy_id=adapters["bilateral_retrieval_policy"].raw_contract_id,
        decision_record_schema_id=adapters["decision_record_schema"].raw_contract_id,
        step_outcome_registry_id=adapters["step_outcome_registry"].raw_contract_id,
        instrumentation_release_id=adapters["instrumentation_release"].raw_contract_id,
        controller_id=str(outcome["controller_contract_id"]),
        evaluator_id=str(outcome["evaluator_contract_id"]),
        budget_profile_id=str(outcome["execution_budget_profile_id"]),
        gamma_candidate=GAMMA_CANDIDATE_B,
        gamma_cov_text="1.0",
        gamma_minus_text="-0.01040883",
        gamma_plus_text="0.00744657",
        declarations=(
            "The prior authorization was valid but retired before execution because of source hardening.",
            "No environment was started and no smoke outcome was observed under the prior authorization.",
            "The nine task, seed, and order values are identical to the prior approved set.",
            "The new seal differs only for schema, explicit eligibility, source, runtime, and policy bindings.",
            "Candidate B and all three exact gamma decimal strings are unchanged.",
            "Every smoke record is engineering-only and permanently excluded from fitting.",
            "Scientific success and scientific failure receive zero retries.",
            "Technical retries are limited to the frozen pre-action-only policy.",
            "Evaluation remains disabled before the original action.",
            "Confidence and plan are generated together with one Planner call per decision.",
            "Memory and Acquisition remain no-write.",
            "Formal Development, Holdout, Final Evaluation, and Round 6 remain closed.",
        ),
    ).with_id()

    args.output.mkdir(parents=True)
    objects = (
        ("technical_retry_policy_v4_1_2_r1.json", retry_policy.to_dict(), retry_policy.policy_id),
        ("process_cleanup_policy_v4_1_2_r1.json", cleanup_policy.to_dict(), cleanup_policy.policy_id),
        ("contract_compatibility_release_r1.json", compatibility.to_dict(), compatibility.release_id),
        ("source_hardening_audit.json", source_audit.to_dict(), source_audit.audit_id),
        ("engineering_smoke_runtime_release_v4_1_2_r1.json", runtime_release.to_dict(), runtime_release.release_id),
        ("engineering_smoke_assignments_v4_1_2_r1.json", assignments.to_dict(), assignments.assignments_id),
        ("assignment_scientific_payload_equivalence_audit.json", equivalence.to_dict(), equivalence.audit_id),
        ("engineering_smoke_exclusion_audit_v4_1_2_r1.json", exclusion.to_dict(), exclusion.audit_id),
        ("engineering_smoke_seal_v4_1_2_r1.json", seal.to_dict(), seal.seal_id),
        ("engineering_smoke_authorization_input_v4_1_2_r1.json", authorization.to_dict(), authorization.authorization_input_id),
    )
    manifest_entries = []
    for filename, payload, object_id in objects:
        path = args.output / filename
        _write(path, payload)
        manifest_entries.append({"filename": filename, "id": object_id, "sha256": file_sha256(path)})
    manifest = {
        "schema_version": 1,
        "source_commit": source,
        "status": "PENDING_ZYF_SMOKE_REAUTHORIZATION",
        "minedojo_started": False,
        "smoke_outcomes_observed": False,
        "task_seed_order_changed": False,
        "scientific_method_changed": False,
        "gamma_changed": False,
        "artifacts": manifest_entries,
    }
    _write(args.output / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
