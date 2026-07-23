"""Post-approval E0R/E1R contracts for a prospective V5 evidence baseline.

The objects here are metadata-only. They cannot mutate Memory, run MineDojo,
fit CHRM/CDT, or open formal/Holdout/final phases.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = 1
EVIDENCE_RELEASE_TYPES = {
    "PaperMemoryV5AuthoritativeEvidenceRelease",
    "SceneExemplarEvidenceReleaseV5R",
    "MineCLIPPolicyBindingReleaseV5R",
}
SMOKE_DECLARATIONS = (
    "Smoke rows are engineering-only and fitting-ineligible.",
    "Assignment selection used no outcomes.",
    "Gamma is selected before smoke outcomes.",
    "Smoke cannot tune gamma/rules/prompts/labels/retrieval.",
    "Evaluation is disabled before the original action.",
    "Confidence is same-generation with one Planner call.",
    "Memory/Acquisition remain no-write.",
    "Scientific failures are final and not rerun to success.",
    "Missing observed coverage cannot add assignments.",
    "Formal V4.1.2 Development remains closed.",
    "Holdout/final/Round 6 remain closed.",
)
GAMMA_CLASSIFICATION_SEMANTICS = (
    "if min(cov_positive,cov_negative) < gamma_cov: unknown; "
    "elif contrast >= gamma_plus: matched; "
    "elif contrast <= gamma_minus: mismatch; else: unknown"
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def expected_rebaseline_approval_statement(payload: Mapping[str, Any]) -> str:
    return (
        "ZYF approves Prospective Memory Re-baseline Authorization Input "
        f"{payload['authorization_input_id']} with file SHA-256 "
        f"{payload['authorization_input_file_sha256']}, binding actual MineCLIP "
        f"policy {payload['actual_mineclip_policy_id']}, actual snapshot manifest "
        f"{payload['actual_snapshot_manifest_id']}, actual acquisition manifest "
        f"{payload['actual_acquisition_manifest_id']}, candidate Scene release "
        f"{payload['scene_candidate_release_id']}, and all 10 declarations exactly "
        "as frozen; approved_by=ZYF."
    )


class _Hashed:
    _id_field: str

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop(self._id_field, None)
        return payload

    def compute_id(self) -> str:
        return canonical_sha256(self.payload_without_id())

    def with_id(self):
        return replace(self, **{self._id_field: self.compute_id()})

    def to_dict(self) -> dict[str, Any]:
        item = self if getattr(self, self._id_field) else self.with_id()
        return {**item.payload_without_id(), self._id_field: getattr(item, self._id_field)}


@dataclass(frozen=True)
class RebaselineAuthorizationReceipt(_Hashed):
    source_commit: str
    authorization_input_id: str
    authorization_input_file_sha256: str
    actual_mineclip_policy_id: str
    actual_snapshot_manifest_id: str
    actual_acquisition_manifest_id: str
    scene_candidate_release_id: str
    declarations_sha256: str
    approval_statement_sha256: str
    approved_by: str
    status: str = "approved"
    contract_regeneration_permitted: bool = True
    schema_version: int = SCHEMA_VERSION
    receipt_id: str = ""

    _id_field = "receipt_id"

    def __post_init__(self) -> None:
        if self.approved_by != "ZYF" or self.status != "approved":
            raise ValueError("Re-baseline approval is not an exact ZYF approval")
        if not self.contract_regeneration_permitted:
            raise ValueError("Approved re-baseline must permit contract regeneration")
        if self.receipt_id and self.receipt_id != self.compute_id():
            raise ValueError("Re-baseline approval receipt hash mismatch")


def verify_rebaseline_approval(
    *,
    source_commit: str,
    authorization_input: Mapping[str, Any],
    authorization_input_file_sha256: str,
    approval_statement: str,
) -> RebaselineAuthorizationReceipt:
    if authorization_input.get("rebaseline_authorization_status") != "pending":
        raise ValueError("Authorization input is not the frozen pending object")
    if authorization_input.get("contract_regeneration_permitted") is not False:
        raise ValueError("Authorization input was already modified")
    declarations = authorization_input.get("declarations", ())
    if len(declarations) != 10:
        raise ValueError("Authorization input does not contain 10 declarations")
    binding = {
        **dict(authorization_input),
        "authorization_input_file_sha256": authorization_input_file_sha256,
    }
    expected = expected_rebaseline_approval_statement(binding)
    if approval_statement.strip() != expected:
        raise ValueError("Author approval statement does not exactly bind the frozen input")
    return RebaselineAuthorizationReceipt(
        source_commit=source_commit,
        authorization_input_id=str(authorization_input["authorization_input_id"]),
        authorization_input_file_sha256=authorization_input_file_sha256,
        actual_mineclip_policy_id=str(authorization_input["actual_mineclip_policy_id"]),
        actual_snapshot_manifest_id=str(authorization_input["actual_snapshot_manifest_id"]),
        actual_acquisition_manifest_id=str(authorization_input["actual_acquisition_manifest_id"]),
        scene_candidate_release_id=str(authorization_input["scene_candidate_release_id"]),
        declarations_sha256=canonical_sha256(list(declarations)),
        approval_statement_sha256=hashlib.sha256(
            approval_statement.strip().encode("utf-8")
        ).hexdigest(),
        approved_by="ZYF",
    ).with_id()


@dataclass(frozen=True)
class AuthoritativeEvidenceRelease(_Hashed):
    release_type: str
    source_commit: str
    authorization_receipt_id: str
    authorization_input_id: str
    provenance_closure_audit_id: str
    retirement_registry_id: str
    impact_audit_id: str
    candidate_release_id: str
    mineclip_policy_id: str
    mineclip_checkpoint_manifest_id: str
    mineclip_checkpoint_sha256: str
    snapshot_manifest_id: str
    acquisition_manifest_id: str
    snapshot_root_sha256: str
    database_sha256: str
    asset_manifest_sha256: str
    accepted_episode_count: int
    scene_source_episode_count: int
    dependency_edge_count: int
    scene_exemplar_count: int
    scene_lineage_root: str
    release_scope: str = "prospective_evidence_baseline"
    snapshot_bytes_changed: bool = False
    database_bytes_changed: bool = False
    asset_bytes_changed: bool = False
    stored_embedding_bytes_changed: bool = False
    memory_rebuilt: bool = False
    historical_equivalence_claimed: bool = False
    usable: bool = True
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        if self.release_type not in EVIDENCE_RELEASE_TYPES:
            raise ValueError("Unknown authoritative evidence release type")
        if self.release_scope != "prospective_evidence_baseline" or not self.usable:
            raise ValueError("Authoritative evidence release scope is invalid")
        if any(
            (
                self.snapshot_bytes_changed,
                self.database_bytes_changed,
                self.asset_bytes_changed,
                self.stored_embedding_bytes_changed,
                self.memory_rebuilt,
                self.historical_equivalence_claimed,
            )
        ):
            raise ValueError("Authoritative evidence release mutated or equated history")
        if (
            self.accepted_episode_count,
            self.scene_source_episode_count,
            self.dependency_edge_count,
            self.scene_exemplar_count,
        ) != (40, 36, 27, 144):
            raise ValueError("Authoritative V5 aggregate identity changed")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("Authoritative evidence release hash mismatch")


def build_authoritative_releases(
    *,
    source_commit: str,
    approval: RebaselineAuthorizationReceipt,
    closure: Mapping[str, Any],
    retirement_registry_id: str,
    impact_audit_id: str,
    paper_candidate_id: str,
    scene_candidate_id: str,
) -> tuple[AuthoritativeEvidenceRelease, ...]:
    if closure.get("status") != "ACTUAL_PROVENANCE_CLOSED":
        raise ValueError("Actual V5 provenance is not closed")
    common = dict(
        source_commit=source_commit,
        authorization_receipt_id=approval.receipt_id,
        authorization_input_id=approval.authorization_input_id,
        provenance_closure_audit_id=str(closure["audit_id"]),
        retirement_registry_id=retirement_registry_id,
        impact_audit_id=impact_audit_id,
        mineclip_policy_id=str(closure["mineclip_policy_id"]),
        mineclip_checkpoint_manifest_id=str(closure["mineclip_checkpoint_manifest_id"]),
        mineclip_checkpoint_sha256=str(closure["mineclip_checkpoint_sha256"]),
        snapshot_manifest_id=str(closure["actual_snapshot_manifest_id"]),
        acquisition_manifest_id=str(closure["actual_acquisition_manifest_id"]),
        snapshot_root_sha256=str(closure["snapshot_root_sha256"]),
        database_sha256=str(closure["database_sha256"]),
        asset_manifest_sha256=str(closure["asset_manifest_sha256"]),
        accepted_episode_count=int(closure["accepted_episode_count"]),
        scene_source_episode_count=int(closure["scene_source_episode_count"]),
        dependency_edge_count=int(closure["dependency_edge_count"]),
        scene_exemplar_count=int(closure["scene_exemplar_count"]),
        scene_lineage_root=str(closure["scene_lineage_root"]),
    )
    return tuple(
        AuthoritativeEvidenceRelease(
            release_type=release_type,
            candidate_release_id=(
                scene_candidate_id
                if release_type == "SceneExemplarEvidenceReleaseV5R"
                else paper_candidate_id
            ),
            **common,
        ).with_id()
        for release_type in (
            "PaperMemoryV5AuthoritativeEvidenceRelease",
            "SceneExemplarEvidenceReleaseV5R",
            "MineCLIPPolicyBindingReleaseV5R",
        )
    )


@dataclass(frozen=True)
class DependencyDisposition:
    object_name: str
    old_object_id: str
    disposition: str
    reason: str
    new_object_id: str | None = None

    def __post_init__(self) -> None:
        if self.disposition not in {"regenerate", "reuse_immutable"}:
            raise ValueError("Unknown dependency disposition")
        if self.disposition == "regenerate" and not self.new_object_id:
            raise ValueError("Regenerated dependency lacks a new ID")
        if self.disposition == "reuse_immutable" and self.new_object_id is not None:
            raise ValueError("Reused dependency cannot claim a new ID")


@dataclass(frozen=True)
class Round513V412DependencyGraph(_Hashed):
    source_commit: str
    authoritative_paper_release_id: str
    authoritative_scene_release_id: str
    mineclip_binding_release_id: str
    dispositions: tuple[DependencyDisposition, ...]
    invalid_binding_count_after_regeneration: int
    schema_version: int = SCHEMA_VERSION
    graph_id: str = ""

    _id_field = "graph_id"

    def __post_init__(self) -> None:
        if self.invalid_binding_count_after_regeneration:
            raise ValueError("V4.1.2 dependency closure still binds invalid evidence")
        if self.graph_id and self.graph_id != self.compute_id():
            raise ValueError("V4.1.2 dependency graph hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["dispositions"] = [asdict(item) for item in self.dispositions]
        return payload


@dataclass(frozen=True)
class Round513V412RegenerationPlan(_Hashed):
    source_commit: str
    dependency_graph_id: str
    regenerated_object_names: tuple[str, ...]
    reused_object_names: tuple[str, ...]
    allowed_change_fields: tuple[str, ...]
    forbidden_scientific_change_fields: tuple[str, ...]
    old_objects_overwritten: bool = False
    schema_version: int = SCHEMA_VERSION
    plan_id: str = ""

    _id_field = "plan_id"

    def __post_init__(self) -> None:
        if self.old_objects_overwritten:
            raise ValueError("Historical V4.1 objects cannot be overwritten")
        if not self.regenerated_object_names or not self.forbidden_scientific_change_fields:
            raise ValueError("V4.1.2 regeneration plan is incomplete")
        if self.plan_id and self.plan_id != self.compute_id():
            raise ValueError("V4.1.2 regeneration plan hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        for key in (
            "regenerated_object_names",
            "reused_object_names",
            "allowed_change_fields",
            "forbidden_scientific_change_fields",
        ):
            payload[key] = list(payload[key])
        return payload


PRIMARY_ID_FIELDS = {
    "Bilateral Retrieval Policy": "policy_id",
    "Decision Record Schema": "schema_id",
    "Collection Blueprint": "blueprint_id",
    "Instrumentation Release": "release_id",
    "Data Readiness Report": "report_id",
    "Readiness Decision": "decision_id",
}


def rehash_contract(payload: Mapping[str, Any], id_field: str) -> dict[str, Any]:
    result = dict(payload)
    result.pop(id_field, None)
    result[id_field] = canonical_sha256(result)
    return result


def regenerate_v412_contracts(
    *,
    source_commit: str,
    old_objects: Mapping[str, Mapping[str, Any]],
    authoritative_paper_release_id: str,
    authoritative_scene_release_id: str,
    actual_mineclip_policy_id: str,
    algorithmic_audit_id: str,
) -> dict[str, dict[str, Any]]:
    """Regenerate only the exact evidence-dependent closure."""

    result: dict[str, dict[str, Any]] = {}
    retrieval = dict(old_objects["Bilateral Retrieval Policy"])
    retrieval.update(
        source_commit=source_commit,
        paper_memory_v5_release_id=authoritative_paper_release_id,
        scene_exemplar_release_id=authoritative_scene_release_id,
        mineclip_policy_id=actual_mineclip_policy_id,
        contract_version="4.1.2",
    )
    result["Bilateral Retrieval Policy"] = rehash_contract(retrieval, "policy_id")

    record = dict(old_objects["Decision Record Schema"])
    record.update(
        source_commit=source_commit,
        retrieval_policy_id=result["Bilateral Retrieval Policy"]["policy_id"],
        contract_version="4.1.2",
    )
    result["Decision Record Schema"] = rehash_contract(record, "schema_id")

    blueprint = dict(old_objects["Collection Blueprint"])
    blueprint.update(
        source_commit=source_commit,
        retrieval_policy_id=result["Bilateral Retrieval Policy"]["policy_id"],
        record_schema_id=result["Decision Record Schema"]["schema_id"],
        contract_version="4.1.2",
    )
    result["Collection Blueprint"] = rehash_contract(blueprint, "blueprint_id")

    instrumentation = dict(old_objects["Instrumentation Release"])
    instrumentation.update(
        source_commit=source_commit,
        record_schema_id=result["Decision Record Schema"]["schema_id"],
        behavior_equivalence_audit_id=algorithmic_audit_id,
        contract_version="4.1.2",
    )
    result["Instrumentation Release"] = rehash_contract(instrumentation, "release_id")

    readiness = dict(old_objects["Data Readiness Report"])
    readiness.update(
        source_commit=source_commit,
        instrumentation_release_id=result["Instrumentation Release"]["release_id"],
        reason="engineering_smoke_authorization_pending",
        contract_version="4.1.2",
    )
    result["Data Readiness Report"] = rehash_contract(readiness, "report_id")

    decision = dict(old_objects["Readiness Decision"])
    decision.update(
        source_commit=source_commit,
        instrumentation_release_id=result["Instrumentation Release"]["release_id"],
        data_readiness_report_id=result["Data Readiness Report"]["report_id"],
        exact_reason="engineering_smoke_authorization_pending",
        contract_version="4.1.2",
    )
    result["Readiness Decision"] = rehash_contract(decision, "decision_id")
    return result


EVIDENCE_FIELDS = {
    "source_commit",
    "contract_version",
    "paper_memory_v5_release_id",
    "scene_exemplar_release_id",
    "mineclip_policy_id",
    "retrieval_policy_id",
    "record_schema_id",
    "instrumentation_release_id",
    "data_readiness_report_id",
    "behavior_equivalence_audit_id",
    "reason",
    "exact_reason",
}


def algorithmic_payload(payload: Mapping[str, Any], id_field: str) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in EVIDENCE_FIELDS and key != id_field
    }


@dataclass(frozen=True)
class Round513V412AlgorithmicEquivalenceAudit(_Hashed):
    source_commit: str
    compared_object_count: int
    non_evidence_field_mismatch_count: int
    deterministic_fixture_count: int
    deterministic_fixture_mismatch_count: int
    planner_call_semantics_unchanged: bool
    controller_call_semantics_unchanged: bool
    label_join_semantics_unchanged: bool
    decision_record_fields_unchanged_except_release_ids: bool
    no_write_behavior_unchanged: bool
    result: str = "algorithmic_semantics_unchanged_evidence_baseline_prospectively_replaced"
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.non_evidence_field_mismatch_count or self.deterministic_fixture_mismatch_count:
            raise ValueError("V4.1.2 algorithmic equivalence failed")
        if not all(
            (
                self.planner_call_semantics_unchanged,
                self.controller_call_semantics_unchanged,
                self.label_join_semantics_unchanged,
                self.decision_record_fields_unchanged_except_release_ids,
                self.no_write_behavior_unchanged,
            )
        ):
            raise ValueError("V4.1.2 algorithmic semantics changed")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Algorithmic-equivalence audit hash mismatch")


@dataclass(frozen=True)
class Round513V412InstrumentationRevalidationAudit(_Hashed):
    source_commit: str
    algorithmic_equivalence_audit_id: str
    instrumentation_release_id: str
    planner_controller_call_count_fixture_passed: bool
    label_join_fixture_passed: bool
    decision_record_fixture_passed: bool
    memory_no_write_passed: bool
    acquisition_no_write_passed: bool
    formal_fitting_rows_created: int
    result: str = "PASS"
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.result != "PASS" or self.formal_fitting_rows_created:
            raise ValueError("Instrumentation revalidation did not pass")
        if not all(
            (
                self.planner_controller_call_count_fixture_passed,
                self.label_join_fixture_passed,
                self.decision_record_fixture_passed,
                self.memory_no_write_passed,
                self.acquisition_no_write_passed,
            )
        ):
            raise ValueError("Instrumentation revalidation is incomplete")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Instrumentation-revalidation audit hash mismatch")


@dataclass(frozen=True)
class Round513EPreSmokeIntegrityAuditV3(_Hashed):
    source_commit: str
    prior_v1_audit_id: str
    prior_v2_audit_id: str
    provenance_closure_audit_id: str
    authorization_receipt_id: str
    authoritative_paper_release_id: str
    authoritative_scene_release_id: str
    mineclip_binding_release_id: str
    dependency_graph_id: str
    regeneration_plan_id: str
    algorithmic_equivalence_audit_id: str
    instrumentation_revalidation_audit_id: str
    full_test_passed: int
    full_test_failed: int
    minedojo_marker_passed: int
    minedojo_marker_skipped: int
    snapshot_guard_passed: bool
    write_probe_rejected: bool
    actual_mineclip_strict_probe_passed: bool
    actions_green: bool
    actions_url: str
    historical_gate_count: int
    worktree_clean: bool
    accepted_episode_count: int
    scene_source_episode_count: int
    dependency_edge_count: int
    scene_exemplar_count: int
    status: str
    eligible_for_smoke_preparation: bool
    minedojo_smoke_started: bool = False
    formal_development_started: bool = False
    holdout_final_round6_accessed: bool = False
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if any(
            value in {self.prior_v1_audit_id, self.prior_v2_audit_id}
            for value in (
                self.provenance_closure_audit_id,
                self.authoritative_paper_release_id,
                self.authoritative_scene_release_id,
                self.mineclip_binding_release_id,
            )
        ):
            raise ValueError("V3 cannot reuse V1/V2 evidence identities")
        eligible = all(
            (
                self.full_test_passed > 0,
                self.full_test_failed == 0,
                self.minedojo_marker_passed > 0,
                self.minedojo_marker_skipped == 0,
                self.snapshot_guard_passed,
                self.write_probe_rejected,
                self.actual_mineclip_strict_probe_passed,
                self.actions_green,
                bool(self.actions_url),
                self.historical_gate_count > 0,
                self.worktree_clean,
                (self.accepted_episode_count, self.scene_source_episode_count,
                 self.dependency_edge_count, self.scene_exemplar_count)
                == (40, 36, 27, 144),
            )
        )
        if self.eligible_for_smoke_preparation != eligible:
            raise ValueError("V3 eligibility does not match required gates")
        if self.status != (
            "ELIGIBLE_FOR_SMOKE_PREPARATION"
            if eligible
            else "BLOCKED_INSTRUMENTATION_REVALIDATION"
        ):
            raise ValueError("V3 status does not match eligibility")
        if any(
            (
                self.minedojo_smoke_started,
                self.formal_development_started,
                self.holdout_final_round6_accessed,
            )
        ):
            raise ValueError("V3 crossed a prohibited experiment boundary")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("V3 PreSmoke audit hash mismatch")


@dataclass(frozen=True)
class SmokeAssignment:
    assignment_id: str
    terminal_task: str
    task_path_label: str
    task_file_sha256: str
    difficulty: str
    target_action_family: str
    coverage_feasibility: str
    feasibility_reason: str
    rule_case: str
    knowledge_case: str
    bilateral_case: str
    seed_commitment: str
    seed: int
    engineering_only: bool = True
    formal_fitting_eligible: bool = False

    def __post_init__(self) -> None:
        if self.coverage_feasibility not in {"feasible", "proxy_only"}:
            raise ValueError("Unknown smoke coverage feasibility")
        if not self.feasibility_reason:
            raise ValueError("Smoke feasibility requires an explanation")
        if not self.engineering_only or self.formal_fitting_eligible:
            raise ValueError("Smoke assignment entered formal fitting")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokePoolV4_1_2(_Hashed):
    source_commit: str
    v3_audit_id: str
    v3_status: str
    namespace_id: str
    assignments: tuple[SmokeAssignment, ...]
    outcome_selected: bool = False
    engineering_only: bool = True
    fitting_eligible: bool = False
    schema_version: int = SCHEMA_VERSION
    pool_id: str = ""

    _id_field = "pool_id"

    def __post_init__(self) -> None:
        if self.v3_status != "ELIGIBLE_FOR_SMOKE_PREPARATION":
            raise ValueError("Smoke preparation requires eligible V3 evidence")
        if self.outcome_selected or not self.engineering_only or self.fitting_eligible:
            raise ValueError("Smoke pool violates engineering isolation")
        ids = [item.assignment_id for item in self.assignments]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Smoke pool assignment IDs are empty or duplicated")
        if any(not item.engineering_only or item.formal_fitting_eligible for item in self.assignments):
            raise ValueError("Smoke assignment entered formal fitting")
        if self.pool_id and self.pool_id != self.compute_id():
            raise ValueError("Smoke pool hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["assignments"] = [asdict(item) for item in self.assignments]
        return payload


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeAssignmentsV4_1_2(_Hashed):
    source_commit: str
    pool_id: str
    assignments: tuple[SmokeAssignment, ...]
    fixed_before_outcomes: bool = True
    observed_coverage_can_expand_set: bool = False
    schema_version: int = SCHEMA_VERSION
    assignments_id: str = ""

    _id_field = "assignments_id"

    def __post_init__(self) -> None:
        if not self.fixed_before_outcomes or self.observed_coverage_can_expand_set:
            raise ValueError("Smoke assignments are adaptive")
        if self.assignments_id and self.assignments_id != self.compute_id():
            raise ValueError("Smoke assignments hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["assignments"] = [asdict(item) for item in self.assignments]
        return payload


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeExclusionAuditV4_1_2(_Hashed):
    source_commit: str
    assignments_id: str
    acquisition_overlap_count: int
    historical_development_overlap_count: int
    previous_smoke_overlap_count: int
    holdout_overlap_count: int
    final_overlap_count: int
    future_formal_v412_overlap_count: int
    proof_method: str = "cryptographic_seed_namespace_domain_separation"
    eligible: bool = True
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        counts = (
            self.acquisition_overlap_count,
            self.historical_development_overlap_count,
            self.previous_smoke_overlap_count,
            self.holdout_overlap_count,
            self.final_overlap_count,
            self.future_formal_v412_overlap_count,
        )
        if self.eligible != all(value == 0 for value in counts):
            raise ValueError("Smoke exclusion conclusion does not match overlaps")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Smoke exclusion audit hash mismatch")


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeSealV4_1_2(_Hashed):
    source_commit: str
    pool_id: str
    assignments_id: str
    exclusion_audit_id: str
    assignment_count: int
    assignments_root_sha256: str
    permanently_engineering_only: bool = True
    fitting_ineligible: bool = True
    sealed: bool = True
    schema_version: int = SCHEMA_VERSION
    seal_id: str = ""

    _id_field = "seal_id"

    def __post_init__(self) -> None:
        if not all((self.permanently_engineering_only, self.fitting_ineligible, self.sealed)):
            raise ValueError("Smoke seal is incomplete")
        if self.assignment_count < 1:
            raise ValueError("Smoke seal has no assignments")
        if self.seal_id and self.seal_id != self.compute_id():
            raise ValueError("Smoke seal hash mismatch")


@dataclass(frozen=True)
class GammaCandidate:
    candidate_id: str
    gamma_cov: float
    gamma_minus: float
    gamma_plus: float
    derivation: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.gamma_cov <= 1.0 or not self.gamma_minus < self.gamma_plus:
            raise ValueError("Invalid gamma candidate")


@dataclass(frozen=True)
class BilateralGammaProvenanceReport(_Hashed):
    source_commit: str
    authoritative_scene_release_id: str
    mineclip_policy_id: str
    query_corpus_root: str
    query_count: int
    action_signature_count: int
    full_coverage_query_count: int
    undercovered_query_count: int
    contrast_count: int
    contrast_quantiles: Mapping[str, float]
    gamma_case: str
    candidates: tuple[GammaCandidate, ...]
    classification_semantics: str = GAMMA_CLASSIFICATION_SEMANTICS
    outcome_labels_used: bool = False
    candidate_selected: bool = False
    schema_version: int = SCHEMA_VERSION
    report_id: str = ""

    _id_field = "report_id"

    def __post_init__(self) -> None:
        if self.classification_semantics != GAMMA_CLASSIFICATION_SEMANTICS:
            raise ValueError("Bilateral gamma classification semantics changed")
        if self.gamma_case != "G3" or self.outcome_labels_used or self.candidate_selected:
            raise ValueError("Gamma report selected or tuned an unapproved value")
        if not self.candidates or self.query_count != self.full_coverage_query_count + self.undercovered_query_count:
            raise ValueError("Gamma provenance report is incomplete")
        if self.report_id and self.report_id != self.compute_id():
            raise ValueError("Gamma provenance report hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["contrast_quantiles"] = dict(sorted(self.contrast_quantiles.items()))
        payload["candidates"] = [asdict(item) for item in self.candidates]
        return payload


@dataclass(frozen=True)
class CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2(_Hashed):
    source_commit: str
    v3_audit_id: str
    smoke_pool_id: str
    smoke_assignments_id: str
    smoke_exclusion_audit_id: str
    smoke_assignment_seal_id: str
    gamma_report_id: str
    gamma_case: str
    gamma_candidates: tuple[GammaCandidate, ...]
    declarations: tuple[str, ...]
    approved_by: str | None = None
    smoke_authorization_status: str = "pending"
    minedojo_smoke_permitted: bool = False
    formal_development_permitted: bool = False
    schema_version: int = SCHEMA_VERSION
    authorization_input_id: str = ""

    _id_field = "authorization_input_id"

    def __post_init__(self) -> None:
        if self.declarations != SMOKE_DECLARATIONS:
            raise ValueError("Smoke authorization declarations changed")
        if self.gamma_case != "G3" or not self.gamma_candidates:
            raise ValueError("Smoke authorization lacks G3 candidates")
        if self.approved_by is not None or self.smoke_authorization_status != "pending":
            raise ValueError("Smoke author approval was fabricated")
        if self.minedojo_smoke_permitted or self.formal_development_permitted:
            raise ValueError("Pending smoke input opened execution")
        if self.authorization_input_id and self.authorization_input_id != self.compute_id():
            raise ValueError("Smoke authorization input hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["gamma_candidates"] = [asdict(item) for item in self.gamma_candidates]
        payload["declarations"] = list(self.declarations)
        return payload


def derive_smoke_assignments(
    *,
    source_commit: str,
    namespace_label: str,
    task_file_sha256_by_path: Mapping[str, str] | None = None,
) -> tuple[str, tuple[SmokeAssignment, ...]]:
    """Create a deterministic metadata-only set; no outcome input is accepted."""

    namespace_id = canonical_sha256({"namespace_label": namespace_label})
    specs = (
        ("log", "agent/tasks/creative/log.json", "basic", "find", "feasible", "terminal task naturally requires search", "soft", "known", "positive_support"),
        ("cobblestone", "agent/tasks/creative/cobblestone.json", "easy", "move_to", "feasible", "terminal task naturally requires approach", "hard", "known", "negative_support"),
        ("iron ore", "agent/tasks/creative/iron_ore.json", "medium", "mine", "feasible", "terminal task naturally requires mining", "hard", "known", "both_sides"),
        ("crafting table", "agent/tasks/creative/crafting_table.json", "basic", "craft", "feasible", "terminal task naturally requires crafting", "soft", "known", "positive_support"),
        ("creature", "agent/tasks/creative/creature.json", "hard", "fight", "proxy_only", "repository task locates a creature but does not require combat", "unknown", "unknown", "insufficient_side"),
        ("wooden pickaxe", "agent/tasks/creative/wooden_pickaxe.json", "easy", "equip", "proxy_only", "repository task crafts the tool but does not require equip", "hard", "known", "positive_support"),
        ("diamond", "agent/tasks/creative/diamond.json", "complex", "dig_down", "feasible", "deep-mining terminal task naturally requires descent", "hard", "known", "negative_support"),
        ("redstone", "agent/tasks/creative/redstone.json", "complex", "dig_up", "proxy_only", "deep-mining task does not guarantee ascent action", "unknown", "unknown", "insufficient_side"),
        ("sapling", "agent/tasks/creative/sapling.json", "medium", "apply", "proxy_only", "repository task obtains a sapling but does not require apply", "soft", "known", "both_sides"),
    )
    assignments = []
    for index, spec in enumerate(specs):
        (
            task, path, difficulty, action, feasibility, feasibility_reason,
            rule, knowledge, bilateral,
        ) = spec
        seed_digest = canonical_sha256(
            {"namespace_id": namespace_id, "terminal_task": task, "replicate_index": index}
        )
        seed = int(seed_digest[:8], 16) & 0x7FFFFFFF
        assignment_payload = {
            "namespace_id": namespace_id,
            "terminal_task": task,
            "difficulty": difficulty,
            "target_action_family": action,
            "coverage_feasibility": feasibility,
            "replicate_index": index,
            "seed_commitment": seed_digest,
            "task_file_sha256": (
                task_file_sha256_by_path[path]
                if task_file_sha256_by_path is not None
                else canonical_sha256({"task_path_label": path})
            ),
        }
        assignments.append(
            SmokeAssignment(
                assignment_id=canonical_sha256(assignment_payload),
                terminal_task=task,
                task_path_label=path,
                task_file_sha256=assignment_payload["task_file_sha256"],
                difficulty=difficulty,
                target_action_family=action,
                coverage_feasibility=feasibility,
                feasibility_reason=feasibility_reason,
                rule_case=rule,
                knowledge_case=knowledge,
                bilateral_case=bilateral,
                seed_commitment=seed_digest,
                seed=seed,
            )
        )
    return namespace_id, tuple(assignments)


def build_gamma_candidates(quantiles: Mapping[str, float]) -> tuple[GammaCandidate, ...]:
    pairs = (
        (quantiles["q25"], quantiles["q75"], "label_free_q25_q75"),
        (quantiles["q10"], quantiles["q90"], "label_free_q10_q90"),
        (
            -max(abs(quantiles["q10"]), abs(quantiles["q90"])),
            max(abs(quantiles["q10"]), abs(quantiles["q90"])),
            "label_free_symmetric_q10_envelope",
        ),
    )
    result = []
    for minus, plus, derivation in pairs:
        payload = {
            "gamma_cov": 1.0,
            "gamma_minus": round(float(minus), 8),
            "gamma_plus": round(float(plus), 8),
            "derivation": derivation,
        }
        result.append(GammaCandidate(candidate_id=canonical_sha256(payload), **payload))
    return tuple(result)


def formal_fitting_accepts_smoke_row(*, engineering_only: bool) -> bool:
    return not engineering_only
