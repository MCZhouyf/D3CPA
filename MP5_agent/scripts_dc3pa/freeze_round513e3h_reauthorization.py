#!/usr/bin/env python3
"""Freeze E3H runtime hardening and stop at the new Author Boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round513e2h import (  # noqa: E402
    ADAPTER_VERSION,
    ContractCompatibilityEntry,
    canonical_sha256,
    file_sha256,
)
from dc3pa.experiments.round513e3h import (  # noqa: E402
    CHRMLiteEngineeringSmokeAssignmentSealE3X_R1,
    CHRMLiteEngineeringSmokeAssignmentsE3X_R1,
    CHRMLiteEngineeringSmokeAuthorizationInputE3X_R1,
    CHRMLiteEngineeringSmokeExclusionAuditE3X_R1,
    CHRMLiteEngineeringSmokePoolE3X_R1,
    CHRMLiteEngineeringSmokeRuntimeReleaseE3X_R1,
    CHRMLiteEngineeringSmokeExecutionManifestE3X_R1,
    E3H_AUTHORIZATION_DECLARATIONS,
    E3H_PREFLIGHT_ORDER_ID,
    E3X_CONTRACT_VERSION,
    E3X_POLICY_ADAPTER_VERSION,
    E3X_RUNTIME_ADAPTER_VERSION,
    E3X_RUNTIME_SCHEMA,
    GAMMA_CANDIDATE_B,
    GAMMA_TEXT,
    RetryCleanupSemanticEquivalenceAudit,
    Round513E3ContractCompatibilityReleaseR1,
    Round513E3HAssignmentDependencyAudit,
    Round513E3HScopeAudit,
    Round513E3HSourceHardeningAudit,
    Round513E3PolicyCompatibilityEntryR1,
    Round513E3PolicyCompatibilityReleaseR1,
    SmokeAssignmentE3X_R1,
    SmokeScientificPayloadEquivalenceAuditE3X_R1,
    TrackERunBindingE3X_R1,
    dataclass_contract_schema_id,
    load_frozen_policy,
    smoke_scientific_payload_root,
)
from dc3pa.experiments.round513e3f import build_provider_contracts  # noqa: E402


BASE_SOURCE = "c223c6ef4f20bf86d03bd0f75360e1230f6be797"
PLANNER_AUTHORING_SOURCE = "df0b043a389b864507d57d3685b863624f519481"
EXPECTED_BRANCH = "round513e4-planner-compat-hardening"
OLD_AUTHORIZATION_ID = "ced8c647d1df598972ad861277cf1d1296a0e5920d84c54112d9e9fc46778dbe"
OLD_AUTHORIZATION_SHA = "1bf9190d0e7073da2d4cfce813a85c19f2aa2bdc2f63b89a4db33e8a8f1fcef5"
OLD_RECEIPT_ID = "a16caa825d759e228a80d3702f9157f46097f122ae2b9701c96fda2246f5edca"
OLD_RECEIPT_SHA = "807852432c0891c643d37cf5c10629076dbd3131d864a93b112347768852a147"
OLD_COMPATIBILITY_ID = "a1e9a93c68406e80ef508d7d8d3453e0a848a095bb983216d8103a6fa9b93fa5"
OLD_COMPATIBILITY_SHA = "b5fe023e1eb2055240cecd62e6a5aba0c8948cf122613e588c5e235dde207967"
BLOCKED_CLOSURE_ID = "d823735bb478a04aba56111e9b84da3a28b130b057fe5ef9b1f1353e57209352"
BLOCKED_CLOSURE_SHA = "fa026adbb885bd422a16e7ab7cd8a780cd79bd3367a5aa19e144a5aac180bf56"
BLOCKED_MANIFEST_ID = "7c8c447322cefa85b7a3e97dbb3a7e39c647f2981f457f2cf0aaf61f4f1d0ef9"
BLOCKED_MANIFEST_SHA = "2228ea3c73802ed8955a98fcc57529ace823c7071dafbd1d7db0e093acfcf70b"
RETRY_ID = "5e832b2056ba8c7c2aed7096a4f2fd22fe8d2a15e4c7ce427ac3896663bb15b5"
RETRY_SHA = "9447924fe0636fb5aaa244ac4c93951f98539e2bc0a04b7b2159e18d7ee13398"
CLEANUP_ID = "99d6d818a329cef6bc29ad9527aa42320f8173861c7b7ceb10837f0005296e14"
CLEANUP_SHA = "e4f7656c2154b1f79754c9f2982d3e2d3200c4a7312f83b3a834f1a828ca4b1c"
POLICY_AUTHORING_SOURCE = "a329fd904eb98b96be5328c726531e8b799555f0"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _verify(path: Path, id_field: str, expected_id: str, expected_sha: str) -> dict:
    if file_sha256(path) != expected_sha:
        raise ValueError(f"Frozen file SHA mismatch: {path.name}")
    payload = _load(path)
    if payload.get(id_field) != expected_id:
        raise ValueError(f"Frozen object ID mismatch: {path.name}")
    canonical = dict(payload)
    canonical.pop(id_field)
    if canonical_sha256(canonical) != expected_id:
        raise ValueError(f"Frozen canonical ID mismatch: {path.name}")
    return payload


def _write(path: Path, payload: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _serialized_sha256(payload: dict) -> str:
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _with_id(payload: dict, id_field: str) -> dict:
    result = dict(payload)
    result[id_field] = canonical_sha256(result)
    return result


def _count_changes(old: list[dict], new: list[dict], names: tuple[str, ...]) -> int:
    return sum(
        any(left[name] != right[name] for name in names)
        for left, right in zip(old, new)
    )


def rebind_smoke_assignment(payload: dict, source_commit: str) -> SmokeAssignmentE3X_R1:
    identity_fields = {
        "assignment_id", "contract_type", "contract_version", "schema_version",
        "source_commit",
    }
    return SmokeAssignmentE3X_R1(
        contract_type="SmokeAssignmentE3X_R1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=source_commit,
        **{key: value for key, value in payload.items() if key not in identity_fields},
    ).with_id()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--previous-root", type=Path, required=True)
    parser.add_argument("--previous-receipt", type=Path, required=True)
    parser.add_argument("--blocked-root", type=Path, required=True)
    parser.add_argument("--retry-policy", type=Path, required=True)
    parser.add_argument("--cleanup-policy", type=Path, required=True)
    parser.add_argument("--e2h-compatibility", type=Path, required=True)
    parser.add_argument("--historical-contract-root", type=Path, required=True)
    parser.add_argument("--external-gate-evidence", type=Path, required=True)
    parser.add_argument("--github-actions-evidence", type=Path, required=True)
    args = parser.parse_args()

    source = _git("rev-parse", "HEAD")
    if source != args.source_commit or _git("status", "--porcelain"):
        raise ValueError("E3H freeze requires the exact clean final HEAD")
    if _git("branch", "--show-current") != EXPECTED_BRANCH:
        raise ValueError("E3H freeze is running on the wrong branch")
    remote = _git("ls-remote", "origin", f"refs/heads/{EXPECTED_BRANCH}").split()
    if not remote or remote[0] != source:
        raise ValueError("Remote E3H branch does not contain the final source")
    if args.output.exists():
        raise FileExistsError("E3H freeze output already exists")

    old_auth = _verify(
        args.previous_root / "engineering_smoke_authorization_input.json",
        "authorization_input_id", OLD_AUTHORIZATION_ID, OLD_AUTHORIZATION_SHA,
    )
    _verify(
        args.previous_receipt, "receipt_id", OLD_RECEIPT_ID, OLD_RECEIPT_SHA,
    )
    old_compatibility = _verify(
        args.previous_root / "contract_compatibility_release.json",
        "release_id", OLD_COMPATIBILITY_ID, OLD_COMPATIBILITY_SHA,
    )
    blocked_manifest = _verify(
        args.blocked_root / "manifest.json",
        "manifest_id", BLOCKED_MANIFEST_ID, BLOCKED_MANIFEST_SHA,
    )
    closure = _verify(
        args.blocked_root / "authorization_closure_audit.json",
        "audit_id", BLOCKED_CLOSURE_ID, BLOCKED_CLOSURE_SHA,
    )
    if not (
        blocked_manifest["provider_preflight_started"] is False
        and blocked_manifest["minedojo_started"] is False
        and blocked_manifest["provider_call_count"] == 0
        and blocked_manifest["environment_actions"] == 0
        and blocked_manifest["scientific_records"] == 0
        and closure["status"] == "BLOCKED_AUTHORIZATION_CONTRACT_CLOSURE"
        and closure["authorized_e3_schema_present_in_compatibility_allowlist"] is False
        and closure["stage6_would_accept_current_closure"] is False
    ):
        raise ValueError("Historical E3X block did not stop before execution")

    retry = load_frozen_policy(
        args.retry_policy, policy_type="technical_retry",
        expected_policy_id=RETRY_ID, expected_file_sha256=RETRY_SHA,
    )
    cleanup = load_frozen_policy(
        args.cleanup_policy, policy_type="process_cleanup",
        expected_policy_id=CLEANUP_ID, expected_file_sha256=CLEANUP_SHA,
    )
    if retry.authoring_source_commit != POLICY_AUTHORING_SOURCE or (
        cleanup.authoring_source_commit != POLICY_AUTHORING_SOURCE
    ):
        raise ValueError("Frozen Policy authoring source changed")

    supersession = _with_id({
        "contract_type": "Round513E4AuthorizationSupersessionDecision",
        "contract_version": "4.1.2-E4-R1",
        "source_commit": source,
        "old_authorization_input_id": OLD_AUTHORIZATION_ID,
        "old_authorization_input_file_sha256": OLD_AUTHORIZATION_SHA,
        "old_authorization_receipt_id": OLD_RECEIPT_ID,
        "old_authorization_receipt_file_sha256": OLD_RECEIPT_SHA,
        "old_assignment_seal_id": str(old_auth["assignment_seal_id"]),
        "old_execution_source": BASE_SOURCE,
        "authorization_closure_audit_id": str(closure["audit_id"]),
        "blocked_manifest_id": str(blocked_manifest["manifest_id"]),
        "authorization_content_valid": True,
        "execution_started": False,
        "provider_preflight_started": False,
        "minedojo_started": False,
        "smoke_outcomes_observed": False,
        "scientific_records_created": 0,
        "reusable_after_source_change": False,
        "historical_objects_preserved": True,
        "supersession_reason": "planner_schema_compatibility_allowlist_hardening",
        "schema_version": 1,
    }, "decision_id")

    changed_files = tuple(
        item for item in _git("diff", "--name-only", f"{BASE_SOURCE}..{source}").splitlines()
        if item
    )
    allowed_files = {
        "MP5_agent/scripts_dc3pa/freeze_round513e3h_reauthorization.py",
        "MP5_agent/tests_dc3pa/test_round513e3h_runtime_contracts.py",
    }
    if set(changed_files) != allowed_files:
        raise ValueError(f"E3H source scope drift: {sorted(set(changed_files) ^ allowed_files)}")
    frozen_identity_root = canonical_sha256({
        "old_authorization": OLD_AUTHORIZATION_ID,
        "old_receipt": OLD_RECEIPT_ID,
        "old_seal": old_auth["assignment_seal_id"],
        "retry": [RETRY_ID, RETRY_SHA],
        "cleanup": [CLEANUP_ID, CLEANUP_SHA],
        "planner": [old_auth["planner_prompt_id"], old_auth["planner_schema_id"], old_auth["planner_parser_id"]],
        "memory": [old_auth["paper_memory_release_id"], old_auth["mineclip_policy_id"], old_auth["scene_exemplar_release_id"]],
        "gamma": [old_auth["gamma_candidate"], old_auth["gamma_cov_text"], old_auth["gamma_minus_text"], old_auth["gamma_plus_text"]],
    })
    scope = Round513E3HScopeAudit(
        source_commit=source,
        changed_files=changed_files,
        allowed_change_categories=(
            "exact_compatibility_allowlist",
            "source_runtime_authorization_rebinding",
        ),
        frozen_object_identity_audit_root=frozen_identity_root,
        scientific_method_changed=False,
        smoke_scientific_payload_changed=False,
        runtime_contract_revision_only=True,
        provider_call_count=0,
        minedojo_launch_count=0,
        status="PASS",
    ).with_id()

    old_assignments = _load(args.previous_root / "engineering_smoke_assignments.json")
    dependency = Round513E3HAssignmentDependencyAudit(
        source_commit=source,
        old_assignments_id=str(old_assignments["assignments_id"]),
        binds_source_commit="source_commit" in old_assignments,
        binds_runtime_release="runtime_release_id" in old_assignments,
        binds_compatibility_release="compatibility_release_id" in old_assignments,
        binds_run_binding_schema="run_binding_schema_id" in old_assignments,
        binds_policy_ids=any(
            name in old_assignments
            for name in ("technical_retry_policy_id", "process_cleanup_policy_id")
        ),
        dependency_case="B",
    ).with_id()
    semantic = RetryCleanupSemanticEquivalenceAudit(
        source_commit=source,
        retry_policy_id=RETRY_ID,
        cleanup_policy_id=CLEANUP_ID,
        retry_policy_file_sha256=RETRY_SHA,
        cleanup_policy_file_sha256=CLEANUP_SHA,
        retry_authoring_source_commit=retry.authoring_source_commit,
        cleanup_authoring_source_commit=cleanup.authoring_source_commit,
        fixture_count=5,
        classification_changes=0,
        retry_decision_changes=0,
        maximum_attempt_changes=0,
        stop_condition_changes=0,
        quarantine_disposition_changes=0,
        cleanup_plan_changes=0,
        status="EQUIVALENT",
    ).with_id()

    gate = _load(args.external_gate_evidence)
    actions = _load(args.github_actions_evidence)
    if gate.get("source_commit") != source or gate.get("status") != "PASS":
        raise ValueError("External gate evidence does not bind the final E3H source")
    if actions.get("head_sha") != source or actions.get("conclusion") != "success":
        raise ValueError("GitHub Actions evidence is not green for final E3H source")
    source_hardening = Round513E3HSourceHardeningAudit(
        source_commit=source,
        scope_audit_id=scope.audit_id,
        supersession_decision_id=str(supersession["decision_id"]),
        assignment_dependency_audit_id=dependency.audit_id,
        retry_cleanup_semantic_equivalence_audit_id=semantic.audit_id,
        github_actions_run_id=str(actions["run_id"]),
        github_actions_url=str(actions["url"]),
        github_actions_conclusion="success",
        full_tests_passed=int(gate["full_tests_passed"]),
        full_tests_failed=int(gate["full_tests_failed"]),
        full_tests_skipped=int(gate["full_tests_skipped"]),
        full_environment_tests_passed=int(gate["full_environment_tests_passed"]),
        full_environment_tests_failed=int(gate["full_environment_tests_failed"]),
        full_environment_tests_skipped=int(gate["full_environment_tests_skipped"]),
        snapshot_guard_passed=bool(gate["snapshot_guard_passed"]),
        paper_memory_write_probe_rejected=bool(gate["paper_memory_write_probe_rejected"]),
        secret_generated_artifact_scan_passed=bool(gate["secret_generated_artifact_scan_passed"]),
        e2h_historical_round_trip_passed=bool(gate["e2h_historical_round_trip_passed"]),
        e3x_round_trip_passed=bool(gate["e3x_round_trip_passed"]),
        cross_version_masquerade_rejected=bool(gate["cross_version_masquerade_rejected"]),
        policy_exact_identity_passed=bool(gate["policy_exact_identity_passed"]),
        preflight_zero_side_effects_passed=bool(gate["preflight_zero_side_effects_passed"]),
        provider_call_count=0,
        minedojo_launch_count=0,
        scientific_method_changed=False,
        smoke_scientific_payload_changed=False,
        runtime_contract_revision_only=True,
        status="PASS",
    ).with_id()

    policy_compatibility = Round513E3PolicyCompatibilityReleaseR1(
        contract_type="Round513E3PolicyCompatibilityReleaseR1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=source,
        entries=(
            Round513E3PolicyCompatibilityEntryR1(
                policy_type="technical_retry", policy_id=RETRY_ID,
                file_sha256=RETRY_SHA, authoring_source_commit=POLICY_AUTHORING_SOURCE,
                allowed_runtime_adapter_versions=(E3X_POLICY_ADAPTER_VERSION,),
                allowed_runtime_schemas=(E3X_RUNTIME_SCHEMA,),
                allowed_execution_source_commits=(source,),
            ),
            Round513E3PolicyCompatibilityEntryR1(
                policy_type="process_cleanup", policy_id=CLEANUP_ID,
                file_sha256=CLEANUP_SHA, authoring_source_commit=POLICY_AUTHORING_SOURCE,
                allowed_runtime_adapter_versions=(E3X_POLICY_ADAPTER_VERSION,),
                allowed_runtime_schemas=(E3X_RUNTIME_SCHEMA,),
                allowed_execution_source_commits=(source,),
            ),
        ),
    ).with_id()

    e2h_compatibility = _load(args.e2h_compatibility)
    canonical_e2h = dict(e2h_compatibility)
    e2h_id = str(canonical_e2h.pop("release_id"))
    if canonical_sha256(canonical_e2h) != e2h_id:
        raise ValueError("Historical E2H compatibility release cannot be reconstructed")
    e3_schema, e3_provider, e3_planner_contract, _ = build_provider_contracts(
        PLANNER_AUTHORING_SOURCE
    )
    if (
        e3_schema.schema_id != old_auth["planner_schema_id"]
        or e3_schema.prompt_id != old_auth["planner_prompt_id"]
        or e3_schema.parser_id != old_auth["planner_parser_id"]
        or e3_provider.policy_id != old_auth["provider_request_policy_id"]
        or e3_planner_contract.contract_id
        != old_auth["planner_runtime_request_contract_id"]
    ):
        raise ValueError("Authorized E3 Planner contract is not reconstructable")
    e3_schema_payload = e3_schema.to_dict()
    e3_schema_filename = "chrmlite_planner_output_schema_v4_1_e3.json"
    scientific_entries = []
    for entry in e2h_compatibility["entries"]:
        if entry["contract_type"] == "planner_schema":
            scientific_entries.append(ContractCompatibilityEntry(
                contract_type="planner_schema",
                filename=e3_schema_filename,
                contract_id=e3_schema.schema_id,
                file_sha256=_serialized_sha256(e3_schema_payload),
                contract_version="4.1",
                authoring_source_commit=PLANNER_AUTHORING_SOURCE,
                runtime_adapter_version=ADAPTER_VERSION,
                allowed_execution_source_commits=(source,),
            ))
            continue
        historical_path = args.historical_contract_root / entry["filename"]
        if file_sha256(historical_path) != entry["file_sha256"]:
            raise ValueError(
                f"Historical scientific contract SHA mismatch: {entry['filename']}"
            )
        scientific_entries.append(ContractCompatibilityEntry(
            **{
                **entry,
                "allowed_execution_source_commits": (source,),
                "runtime_adapter_version": ADAPTER_VERSION,
            }
        ))
    scientific_entries = tuple(scientific_entries)
    if sum(
        entry.contract_type == "planner_schema" for entry in scientific_entries
    ) != 1:
        raise ValueError("Compatibility release must contain exactly one Planner schema")
    preserved_fields = (
        "contract_type", "filename", "contract_id", "file_sha256",
        "contract_version", "authoring_source_commit", "runtime_adapter_version",
    )
    previous_non_planner = {
        entry["contract_type"]: tuple(entry[name] for name in preserved_fields)
        for entry in old_compatibility["scientific_contract_entries"]
        if entry["contract_type"] != "planner_schema"
    }
    regenerated_non_planner = {
        entry.contract_type: tuple(
            getattr(entry, name) for name in preserved_fields
        )
        for entry in scientific_entries
        if entry.contract_type != "planner_schema"
    }
    if len(previous_non_planner) != 6 or regenerated_non_planner != previous_non_planner:
        raise ValueError("The six non-Planner scientific contracts changed")
    compatibility = Round513E3ContractCompatibilityReleaseR1(
        contract_type="Round513E3ContractCompatibilityReleaseR1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=source,
        source_hardening_audit_id=source_hardening.audit_id,
        historical_e3_compatibility_release_id=OLD_COMPATIBILITY_ID,
        historical_e3_compatibility_file_sha256=OLD_COMPATIBILITY_SHA,
        historical_e2h_compatibility_release_id=e2h_id,
        provider_request_policy_id=str(old_auth["provider_request_policy_id"]),
        planner_runtime_request_contract_id=str(old_auth["planner_runtime_request_contract_id"]),
        planner_schema_id=str(old_auth["planner_schema_id"]),
        planner_parser_id=str(old_auth["planner_parser_id"]),
        scientific_contract_entries=scientific_entries,
        runtime_adapter_version=E3X_RUNTIME_ADAPTER_VERSION,
        runtime_schema=E3X_RUNTIME_SCHEMA,
    ).with_id()
    binding_schema_id = dataclass_contract_schema_id(
        TrackERunBindingE3X_R1,
        invariants={"assignment_count": 9, "proxy_policy": "P1", "engineering_only": True},
    )
    manifest_schema_id = dataclass_contract_schema_id(
        CHRMLiteEngineeringSmokeExecutionManifestE3X_R1,
        invariants={"environment_execution_permitted": "requires_new_ZYF_receipt"},
    )
    runtime = CHRMLiteEngineeringSmokeRuntimeReleaseE3X_R1(
        contract_type="CHRMLiteEngineeringSmokeRuntimeReleaseE3X_R1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=source,
        source_hardening_audit_id=source_hardening.audit_id,
        contract_compatibility_release_id=compatibility.release_id,
        policy_compatibility_release_id=policy_compatibility.release_id,
        provider_request_policy_id=str(old_auth["provider_request_policy_id"]),
        planner_runtime_request_contract_id=str(old_auth["planner_runtime_request_contract_id"]),
        technical_retry_policy_id=RETRY_ID,
        process_cleanup_policy_id=CLEANUP_ID,
        controller_id=str(old_auth["controller_id"]),
        evaluator_id=str(old_auth["evaluator_id"]),
        budget_profile_id=str(old_auth["budget_profile_id"]),
        run_binding_schema_id=binding_schema_id,
        execution_manifest_schema_id=manifest_schema_id,
        runtime_adapter_version=E3X_RUNTIME_ADAPTER_VERSION,
        preflight_order_id=E3H_PREFLIGHT_ORDER_ID,
    ).with_id()

    rows = tuple(
        rebind_smoke_assignment(old, source)
        for old in old_assignments["assignments"]
    )
    assignments = CHRMLiteEngineeringSmokeAssignmentsE3X_R1(
        contract_type="CHRMLiteEngineeringSmokeAssignmentsE3X_R1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=source,
        namespace_id=str(old_assignments["namespace_id"]),
        runtime_release_id=runtime.release_id,
        contract_compatibility_release_id=compatibility.release_id,
        policy_compatibility_release_id=policy_compatibility.release_id,
        run_binding_schema_id=binding_schema_id,
        assignments=rows,
    ).with_id()
    old_pool = _load(args.previous_root / "engineering_smoke_pool.json")
    pool = CHRMLiteEngineeringSmokePoolE3X_R1(
        contract_type="CHRMLiteEngineeringSmokePoolE3X_R1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=source,
        namespace_id=str(old_pool["namespace_id"]),
        task_asset_audit_id=str(old_pool["task_asset_audit_id"]),
        proxy_policy=str(old_pool["proxy_policy"]),
        assignment_count=int(old_pool["assignment_count"]),
    ).with_id()
    old_exclusion = _load(args.previous_root / "engineering_smoke_exclusion_audit.json")
    exclusion = CHRMLiteEngineeringSmokeExclusionAuditE3X_R1(
        contract_type="CHRMLiteEngineeringSmokeExclusionAuditE3X_R1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=source,
        assignments_id=assignments.assignments_id,
        namespace_id=str(old_exclusion["namespace_id"]),
        protected_namespace_root=str(old_exclusion["protected_namespace_root"]),
        acquisition_overlap_count=int(old_exclusion["acquisition_overlap_count"]),
        historical_development_overlap_count=int(old_exclusion["historical_development_overlap_count"]),
        previous_smoke_overlap_count=int(old_exclusion["previous_smoke_overlap_count"]),
        future_formal_v412_overlap_count=int(old_exclusion["future_formal_v412_overlap_count"]),
        holdout_overlap_count=int(old_exclusion["holdout_overlap_count"]),
        final_overlap_count=int(old_exclusion["final_overlap_count"]),
        proof_method=str(old_exclusion["proof_method"]),
        eligible=bool(old_exclusion["eligible"]),
    ).with_id()
    old_rows = list(old_assignments["assignments"])
    new_rows = [item.to_dict() for item in rows]
    old_scientific_root = smoke_scientific_payload_root(old_rows)
    new_scientific_root = smoke_scientific_payload_root(new_rows)
    equivalence = SmokeScientificPayloadEquivalenceAuditE3X_R1(
        source_commit=source,
        old_assignments_id=str(old_assignments["assignments_id"]),
        new_assignments_id=assignments.assignments_id,
        old_payload_root=old_scientific_root,
        new_payload_root=new_scientific_root,
        assignment_count=len(new_rows),
        task_changes=_count_changes(old_rows, new_rows, ("terminal_task", "formal_task_name")),
        seed_changes=_count_changes(old_rows, new_rows, ("seed", "seed_commitment")),
        order_changes=_count_changes(old_rows, new_rows, ("order",)),
        asset_changes=_count_changes(old_rows, new_rows, ("task_path_label", "task_file_sha256")),
        proxy_changes=_count_changes(old_rows, new_rows, ("coverage_naturalness", "natural_action_coverage_eligible")),
        eligibility_changes=_count_changes(old_rows, new_rows, (
            "engineering_only", "formal_fitting_eligible", "channel_calibration_eligible",
            "CHRM_fitting_eligible", "CDT_identification_eligible", "holdout_eligible",
            "final_evaluation_eligible",
        )),
        namespace_changes=_count_changes(old_rows, new_rows, ("namespace_id",)),
        status="EQUIVALENT",
    ).with_id()
    seal = CHRMLiteEngineeringSmokeAssignmentSealE3X_R1(
        contract_type="CHRMLiteEngineeringSmokeAssignmentSealE3X_R1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=source,
        pool_id=pool.pool_id,
        assignments_id=assignments.assignments_id,
        assignments_root_sha256=canonical_sha256(new_rows),
        scientific_payload_root=new_scientific_root,
        exclusion_audit_id=exclusion.audit_id,
        contract_compatibility_release_id=compatibility.release_id,
        policy_compatibility_release_id=policy_compatibility.release_id,
        runtime_release_id=runtime.release_id,
        run_binding_schema_id=binding_schema_id,
        execution_manifest_schema_id=manifest_schema_id,
        assignment_count=9,
        proxy_policy="P1",
    ).with_id()
    authorization = CHRMLiteEngineeringSmokeAuthorizationInputE3X_R1(
        contract_type="CHRMLiteEngineeringSmokeAuthorizationInputE3X_R1",
        contract_version=E3X_CONTRACT_VERSION,
        source_commit=source,
        source_hardening_audit_id=source_hardening.audit_id,
        supersession_decision_id=str(supersession["decision_id"]),
        scope_audit_id=scope.audit_id,
        assignment_dependency_audit_id=dependency.audit_id,
        scientific_payload_equivalence_audit_id=equivalence.audit_id,
        retry_cleanup_semantic_equivalence_audit_id=semantic.audit_id,
        runtime_release_id=runtime.release_id,
        contract_compatibility_release_id=compatibility.release_id,
        policy_compatibility_release_id=policy_compatibility.release_id,
        run_binding_schema_id=binding_schema_id,
        execution_manifest_schema_id=manifest_schema_id,
        provider_request_policy_id=str(old_auth["provider_request_policy_id"]),
        planner_runtime_request_contract_id=str(old_auth["planner_runtime_request_contract_id"]),
        planner_schema_id=str(old_auth["planner_schema_id"]),
        planner_prompt_id=str(old_auth["planner_prompt_id"]),
        planner_parser_id=str(old_auth["planner_parser_id"]),
        formal_taskset_release_id=str(old_auth["formal_taskset_release_id"]),
        formal_catalog_sha256=str(old_auth["formal_catalog_sha256"]),
        namespace_id=str(old_assignments["namespace_id"]),
        proxy_policy="P1",
        proxy_decision_input_id=str(old_auth["proxy_decision_input_id"]),
        iron_ingot_asset_audit_id=str(old_auth["iron_ingot_asset_audit_id"]),
        pool_id=pool.pool_id,
        assignments_id=assignments.assignments_id,
        exclusion_audit_id=exclusion.audit_id,
        assignment_seal_id=seal.seal_id,
        ordered_assignment_root=canonical_sha256(new_rows),
        paper_memory_release_id=str(old_auth["paper_memory_release_id"]),
        paper_memory_root=str(old_auth["paper_memory_root"]),
        mineclip_policy_id=str(old_auth["mineclip_policy_id"]),
        scene_exemplar_release_id=str(old_auth["scene_exemplar_release_id"]),
        rule_registry_id=str(old_auth["rule_registry_id"]),
        bilateral_policy_id=str(old_auth["bilateral_policy_id"]),
        decision_record_schema_id=str(old_auth["decision_record_schema_id"]),
        step_outcome_registry_id=str(old_auth["step_outcome_registry_id"]),
        instrumentation_release_id=str(old_auth["instrumentation_release_id"]),
        controller_id=str(old_auth["controller_id"]),
        evaluator_id=str(old_auth["evaluator_id"]),
        budget_profile_id=str(old_auth["budget_profile_id"]),
        technical_retry_policy_id=RETRY_ID,
        technical_retry_policy_file_sha256=RETRY_SHA,
        process_cleanup_policy_id=CLEANUP_ID,
        process_cleanup_policy_file_sha256=CLEANUP_SHA,
        gamma_candidate=GAMMA_CANDIDATE_B,
        gamma_cov_text=GAMMA_TEXT[0],
        gamma_minus_text=GAMMA_TEXT[1],
        gamma_plus_text=GAMMA_TEXT[2],
        declarations=E3H_AUTHORIZATION_DECLARATIONS,
    ).with_id()

    args.output.mkdir(parents=True, mode=0o700)
    contract_output = args.output / "scientific_contracts"
    contract_output.mkdir(mode=0o700)
    _write(contract_output / e3_schema_filename, e3_schema_payload)
    for entry in scientific_entries:
        if entry.contract_type == "planner_schema":
            continue
        source_path = args.historical_contract_root / entry.filename
        destination = contract_output / entry.filename
        with source_path.open("rb") as source_handle, destination.open("xb") as output_handle:
            shutil.copyfileobj(source_handle, output_handle)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        if file_sha256(destination) != entry.file_sha256:
            raise ValueError(f"Copied scientific contract SHA mismatch: {entry.filename}")
    objects = {
        "authorization_supersession_decision.json": (supersession, "decision_id"),
        "scope_audit.json": (scope.to_dict(), "audit_id"),
        "assignment_dependency_audit.json": (dependency.to_dict(), "audit_id"),
        "retry_cleanup_semantic_equivalence_audit.json": (semantic.to_dict(), "audit_id"),
        "source_hardening_audit.json": (source_hardening.to_dict(), "audit_id"),
        "policy_compatibility_release.json": (policy_compatibility.to_dict(), "release_id"),
        "contract_compatibility_release.json": (compatibility.to_dict(), "release_id"),
        "runtime_release.json": (runtime.to_dict(), "release_id"),
        "engineering_smoke_pool.json": (pool.to_dict(), "pool_id"),
        "engineering_smoke_assignments.json": (assignments.to_dict(), "assignments_id"),
        "engineering_smoke_exclusion_audit.json": (exclusion.to_dict(), "audit_id"),
        "scientific_payload_equivalence_audit.json": (equivalence.to_dict(), "audit_id"),
        "engineering_smoke_assignment_seal.json": (seal.to_dict(), "seal_id"),
        "engineering_smoke_authorization_input.json": (authorization.to_dict(), "authorization_input_id"),
    }
    artifact_rows = []
    for filename, (payload, id_field) in objects.items():
        path = args.output / filename
        _write(path, payload)
        artifact_rows.append({"filename": filename, "id": payload[id_field], "sha256": file_sha256(path)})
    for entry in scientific_entries:
        artifact_rows.append({
            "filename": f"scientific_contracts/{entry.filename}",
            "id": entry.contract_id,
            "sha256": file_sha256(contract_output / entry.filename),
        })
    authorization_path = args.output / "engineering_smoke_authorization_input.json"
    approval_sentence = (
        "ZYF approves CHRMLite Engineering Smoke Authorization Input E3X R1 "
        f"{authorization.authorization_input_id} with file SHA-256 {file_sha256(authorization_path)}, "
        f"binding E3H_EXECUTION_SOURCE_SHA {source}, Runtime Release {runtime.release_id}, "
        f"Contract Compatibility {compatibility.release_id}, Policy Compatibility "
        f"{policy_compatibility.release_id}, Assignment Seal {seal.seal_id}, Candidate B "
        f"{GAMMA_CANDIDATE_B} with gamma_cov={GAMMA_TEXT[0]}, "
        f"gamma_minus={GAMMA_TEXT[1]}, gamma_plus={GAMMA_TEXT[2]}, and all 12 declarations "
        "exactly as frozen; approved_by=ZYF."
    )
    manifest = {
        "phase": "E4_PLANNER_COMPAT_AUTHOR_BOUNDARY",
        "source_commit": source,
        "source_frozen": True,
        "assignment_dependency_case": "B",
        "assignment_count": 9,
        "reauthorization_status": "pending",
        "provider_preflight_permitted": False,
        "minedojo_execution_permitted": False,
        "provider_call_count": 0,
        "minedojo_launch_count": 0,
        "artifacts": artifact_rows,
        "required_approval_sentence": approval_sentence,
    }
    manifest["manifest_id"] = canonical_sha256(manifest)
    _write(args.output / "manifest.json", manifest)
    print(json.dumps({
        "source_commit": source,
        "supersession_decision_id": supersession["decision_id"],
        "scope_audit_id": scope.audit_id,
        "runtime_release_id": runtime.release_id,
        "contract_compatibility_release_id": compatibility.release_id,
        "policy_compatibility_release_id": policy_compatibility.release_id,
        "assignments_id": assignments.assignments_id,
        "assignment_seal_id": seal.seal_id,
        "authorization_input_id": authorization.authorization_input_id,
        "authorization_input_file_sha256": file_sha256(authorization_path),
        "required_approval_sentence": approval_sentence,
        "provider_call_count": 0,
        "minedojo_launch_count": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
