"""Round 5.13E6-D2 prospective observability and label contracts.

These contracts close the immutable D1 diagnostic and prepare, but do not
authorize, a paired D2 instrumentation replay.  D1 records are inputs to an
audit only; no function in this module writes historical records or Memory.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..contracts import Action, AgentState, Plan
from .round513_instrumentation import (
    BilateralEvidenceV4_1,
    ControllerReceiptV4_1,
    StateEvidenceV4_1,
    _post_state_from_telemetry,
    _state_evidence_from_agent,
    bilateral_retrieve_v4_1,
    build_rule_evidence_from_frozen_state,
    deterministic_record_id,
    extract_knowledge_features_v4_1,
)
from .round513e5d1 import ScientificContractReferenceD1, seed_from_commitment


D1_EXECUTION_SOURCE_SHA = "4a6a6951838cdb9bfc43032d0febaef3d2be3f2d"
D1_REPORT_ID = "269648396b387aaf8859cc9972550ccb396545b2a5b99e20a9ed5402e9e0dc0d"
D1_REPORT_FILE_SHA256 = "a117e46d1b5f1bb6a6607b38c187bca3cccac65008b21d28a384858b0e43b5ce"
CANDIDATE_B_ID = "0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f"
GAMMA_TEXT = ("1.0", "-0.01040883", "0.00744657")
D1_TASK_ORDER = ("mine sapling", "mine iron ore", "mine log")
CONTRACT_VERSION = "E6-D2"
SCHEMA_VERSION = 2
RECORD_DISPOSITIONS = (
    "accepted_scientific_action",
    "audit_only_ambiguous",
    "technical_quarantine",
    "incomplete_pending",
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
class D1OutcomeRow:
    order: int
    task: str
    record_id: str
    record_hash: str
    record_file_sha256: str
    controller_success: bool
    y_action: int | None
    y_goal: int | None
    record_disposition: str
    termination_reason: str


@dataclass(frozen=True)
class Round513D1RawCompleteAudit(_Hashed):
    d1_source_sha: str
    report_id: str
    report_file_sha256: str
    execution_closure_manifest_id: str
    rows: tuple[D1OutcomeRow, ...]
    report_and_records_complete: bool
    historical_records_rewritten: bool = False
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        expected = (
            (0, "mine sapling", None, 1, "audit_only_ambiguous"),
            (1, "mine iron ore", None, None, "audit_only_ambiguous"),
            (2, "mine log", 1, 0, "accepted_scientific"),
        )
        actual = tuple(
            (row.order, row.task, row.y_action, row.y_goal, row.record_disposition)
            for row in self.rows
        )
        if self.d1_source_sha != D1_EXECUTION_SOURCE_SHA:
            raise ValueError("D1 source changed")
        if (self.report_id, self.report_file_sha256) != (
            D1_REPORT_ID,
            D1_REPORT_FILE_SHA256,
        ):
            raise ValueError("D1 report identity changed")
        if actual != expected or not self.report_and_records_complete:
            raise ValueError("D1 machine-readable outcome closure is incomplete")
        if self.historical_records_rewritten:
            raise ValueError("D1 records must remain immutable")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("D1 raw-complete audit ID mismatch")


@dataclass(frozen=True)
class Round513D1LabelGapAudit(_Hashed):
    raw_complete_audit_id: str
    accepted_action_labels: int = 1
    ambiguous_action_labels: int = 2
    action_goal_orthogonal: bool = True
    controller_status_is_not_action_label: bool = True
    goal_may_not_backfill_action: bool = True
    log_positive_control: tuple[int, int] = (1, 0)
    sapling_reverse_control: tuple[int | None, int] = (None, 1)
    safety_semantics_were_unresolved_in_d1: bool = True
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if (self.accepted_action_labels, self.ambiguous_action_labels) != (1, 2):
            raise ValueError("D1 label counts changed")
        if not all(
            (
                self.action_goal_orthogonal,
                self.controller_status_is_not_action_label,
                self.goal_may_not_backfill_action,
                self.safety_semantics_were_unresolved_in_d1,
            )
        ):
            raise ValueError("D1 label-gap boundary was weakened")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("D1 label-gap audit ID mismatch")


@dataclass(frozen=True)
class Round513D1TechnicalAttemptAudit(_Hashed):
    raw_complete_audit_id: str
    sapling_attempt_1_trace_sha256: str
    sapling_attempt_1_console_sha256: str
    sapling_attempt_2_trace_sha256: str
    sapling_attempt_2_console_sha256: str
    attempt_1_disposition: str = "technical_quarantine"
    attempt_1_failure: str = "readonly_memory_root_launch_argument_missing"
    attempt_1_environment_action_started: bool = False
    attempt_2_disposition: str = "diagnostic_final_attempt"
    scientific_sample_count: int = 1
    technical_retry_count: int = 1
    frozen_t1_maximum_attempts: int = 2
    technical_attempt_in_action_label_root: bool = False
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if any(len(value) != 64 for value in (
            self.sapling_attempt_1_trace_sha256,
            self.sapling_attempt_1_console_sha256,
            self.sapling_attempt_2_trace_sha256,
            self.sapling_attempt_2_console_sha256,
        )):
            raise ValueError("D1 technical attempt evidence SHA is incomplete")
        if self.attempt_1_disposition != "technical_quarantine":
            raise ValueError("D1 technical attempt was not quarantined")
        if self.attempt_1_environment_action_started:
            raise ValueError("D1 technical retry occurred after environment action")
        if (self.scientific_sample_count, self.technical_retry_count, self.frozen_t1_maximum_attempts) != (1, 1, 2):
            raise ValueError("D1 retry accounting changed")
        if self.technical_attempt_in_action_label_root:
            raise ValueError("D1 technical attempt leaked into labels")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("D1 technical-attempt audit ID mismatch")


@dataclass(frozen=True)
class Round513D1CloseoutRelease(_Hashed):
    raw_complete_audit_id: str
    label_gap_audit_id: str
    technical_attempt_audit_id: str
    d1_report_id: str = D1_REPORT_ID
    d1_records_immutable: bool = True
    d1_relabel_permitted: bool = False
    d1_engineering_diagnostic_only: bool = True
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        if not self.d1_records_immutable or self.d1_relabel_permitted:
            raise ValueError("D1 closeout permits historical mutation")
        if not self.d1_engineering_diagnostic_only:
            raise ValueError("D1 scientific-use boundary changed")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("D1 closeout release ID mismatch")


@dataclass(frozen=True)
class ActionGoalOutcomeSchemaV2(_Hashed):
    controller_fields: tuple[str, ...] = (
        "controller_status", "controller_terminal_reason"
    )
    action_fields: tuple[str, ...] = (
        "expected_action_postcondition",
        "observed_action_postcondition",
        "y_action",
        "y_action_evidence_status",
    )
    goal_fields: tuple[str, ...] = (
        "terminal_goal_status", "y_goal", "y_goal_evidence_status"
    )
    disposition_field: str = "record_disposition"
    chrm_primary_label: str = "y_action"
    controller_may_override_labels: bool = False
    goal_may_backfill_action: bool = False
    action_may_backfill_goal: bool = False
    postcondition_policy_version: str = "action_family_v1"
    target_identity_match_required: bool = True
    unobserved_action_families_fail_closed: bool = True
    action_pairing_interpretation: str = "stratify_by_normalized_action_signature"
    allowed_dispositions: tuple[str, ...] = RECORD_DISPOSITIONS
    schema_id: str = ""

    _id_field = "schema_id"

    def __post_init__(self) -> None:
        if any((self.controller_may_override_labels, self.goal_may_backfill_action, self.action_may_backfill_goal)):
            raise ValueError("V2 outcome layers are not orthogonal")
        if self.chrm_primary_label != "y_action":
            raise ValueError("CHRM-lite primary label changed")
        if self.postcondition_policy_version != "action_family_v1":
            raise ValueError("Unknown V2 action postcondition policy")
        if not self.target_identity_match_required or not self.unobserved_action_families_fail_closed:
            raise ValueError("V2 action evidence no longer fails closed")
        if self.action_pairing_interpretation != "stratify_by_normalized_action_signature":
            raise ValueError("V2 action pairing interpretation changed")
        if self.allowed_dispositions != RECORD_DISPOSITIONS:
            raise ValueError("V2 record lifecycle changed")
        if self.schema_id and self.schema_id != self.compute_id():
            raise ValueError("V2 outcome schema ID mismatch")


@dataclass(frozen=True)
class FindObservationStepEvidenceV2:
    observation_index: int
    observation_id: str
    observation_sha256: str
    image_sha256: str
    detector_sensor_status: str
    raw_detected_target_ids: tuple[str, ...]
    canonical_target_candidates: tuple[str, ...]
    target_position_evidence: Mapping[str, Any]
    visibility_flag: bool | None
    line_of_sight_flag: bool | None
    line_of_sight_available: bool
    distance_estimate: float | None
    distance_unit: str
    agent_position: tuple[float, ...]
    agent_yaw: float | None
    agent_pitch: float | None
    search_frontier_progress: Mapping[str, Any]
    controller_step_result: str
    sensor_missing: bool
    sensor_error: str
    missing_sensor_fields: tuple[str, ...]
    spatial_relation: str

    @property
    def required_sensor_complete(self) -> bool:
        return all(
            (
                self.detector_sensor_status == "ok",
                bool(self.observation_id),
                bool(self.observation_sha256),
                bool(self.image_sha256),
                len(self.agent_position) == 3,
                bool(self.controller_step_result),
                not self.sensor_missing,
                not self.sensor_error,
                not self.missing_sensor_fields,
            )
        )


@dataclass(frozen=True)
class FindObservationEvidenceV2:
    raw_requested_target: str
    raw_controller_target: str
    outcome_target_identity: str
    steps: tuple[FindObservationStepEvidenceV2, ...]
    search_trace_id: str
    search_steps_consumed: int
    search_seconds_consumed: float
    frozen_search_budget: int
    search_budget_exhausted: bool | None
    search_trace_complete: bool
    termination_reason: str
    technical_failure: str = ""

    @property
    def evidence_id(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class FindObservationEvidenceContractV2(_Hashed):
    per_step_fields: tuple[str, ...] = (
        "observation_index", "observation_id", "observation_sha256", "image_sha256",
        "detector_sensor_status", "raw_detected_target_ids", "canonical_target_candidates",
        "target_position_evidence", "visibility_flag", "line_of_sight_flag",
        "line_of_sight_available",
        "distance_estimate", "distance_unit", "agent_position", "agent_yaw", "agent_pitch",
        "search_frontier_progress", "controller_step_result", "sensor_missing", "sensor_error",
        "missing_sensor_fields", "spatial_relation",
    )
    success_requires_outcome_identity: bool = True
    success_requires_direct_visibility: bool = True
    success_requires_distance_contract: bool = True
    success_requires_complete_sensors: bool = True
    failure_requires_bounded_or_final_scientific_termination: bool = True
    failure_requires_all_sensors: bool = True
    absence_alone_is_failure: bool = False
    controller_boolean_sufficient: bool = False
    goal_result_sufficient: bool = False
    contract_id: str = ""

    _id_field = "contract_id"

    def __post_init__(self) -> None:
        if any((self.absence_alone_is_failure, self.controller_boolean_sufficient, self.goal_result_sufficient)):
            raise ValueError("V2 find contract permits evidence-free labels")
        if self.contract_id and self.contract_id != self.compute_id():
            raise ValueError("V2 find evidence contract ID mismatch")


@dataclass(frozen=True)
class SafetyTerminationSemanticsAudit(_Hashed):
    controller_source_sha256: str
    structured_actions_source_sha256: str
    termination_reason: str = "safety_clearance_stop"
    classification: str = "A_final_expected_safety_termination"
    fresh_voxel_sensor_used: bool = True
    current_high_level_action_returns_false: bool = True
    controller_returns_failure: bool = True
    recoverable_replan_signal: bool = False
    infrastructure_or_sensor_exception: bool = False
    historical_d1_trace_complete: bool = False
    historical_d1_label_must_remain_null: bool = True
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.classification != "A_final_expected_safety_termination":
            raise ValueError("Safety semantics are not closed as category A")
        if not all((self.fresh_voxel_sensor_used, self.current_high_level_action_returns_false, self.controller_returns_failure)):
            raise ValueError("Safety category A lacks code-path evidence")
        if self.recoverable_replan_signal or self.infrastructure_or_sensor_exception:
            raise ValueError("Safety termination was conflated with replan/technical failure")
        if self.historical_d1_trace_complete or not self.historical_d1_label_must_remain_null:
            raise ValueError("Safety audit relabels the incomplete D1 iron record")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Safety semantics audit ID mismatch")


@dataclass(frozen=True)
class SafetyTerminationPolicyV2(_Hashed):
    semantics_audit_id: str
    selected_candidate: str = "S1"
    applies_prospectively_from: str = "D2"
    final_safety_stop_with_absent_postcondition_y_action: int = 0
    requires_complete_step_sensors: bool = True
    requires_no_target_match: bool = True
    requires_no_technical_failure: bool = True
    requires_final_controller_termination: bool = True
    historical_relabel_permitted: bool = False
    failure_type: str = "controller_safety_termination"
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        if self.selected_candidate != "S1" or self.final_safety_stop_with_absent_postcondition_y_action != 0:
            raise ValueError("Unknown safety termination policy")
        if not all((self.requires_complete_step_sensors, self.requires_no_target_match, self.requires_no_technical_failure, self.requires_final_controller_termination)):
            raise ValueError("Safety failure label lacks required evidence")
        if self.historical_relabel_permitted:
            raise ValueError("Safety policy may not relabel D1")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("Safety policy ID mismatch")


def _token(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", " ").replace("_", " ").split())


@dataclass(frozen=True)
class ActionObjectSignatureEntryV2:
    raw_object: str
    controller_canonical_object: str
    retrieval_canonical_family: str
    outcome_target_canonical_identity: str
    mapping_rationale: str
    mapping_source: str


SIGNATURE_ROWS = (
    ActionObjectSignatureEntryV2("sapling", "sapling", "minecraft:family/sapling", "minecraft:block/sapling", "direct block observation", "MineDojo voxel vocabulary"),
    ActionObjectSignatureEntryV2("iron_ore", "iron ore", "minecraft:family/iron_ore_source", "minecraft:block/iron_ore", "underscore normalization only", "Controller object vocabulary"),
    ActionObjectSignatureEntryV2("iron ore", "iron ore", "minecraft:family/iron_ore_source", "minecraft:block/iron_ore", "direct ore block observation", "MineDojo voxel vocabulary"),
    ActionObjectSignatureEntryV2("log", "wood", "minecraft:family/log_source", "minecraft:item/log", "Controller searches a source block but task identity remains an item", "Controller and task registry"),
    ActionObjectSignatureEntryV2("tree", "wood", "minecraft:family/log_source", "minecraft:concept/tree", "planner concept maps to Controller wood search only", "Planner and Controller vocabulary"),
    ActionObjectSignatureEntryV2("wood", "wood", "minecraft:family/log_source", "minecraft:block/wood", "direct MineDojo source-block observation", "MineDojo voxel vocabulary"),
    ActionObjectSignatureEntryV2("oak_log", "wood", "minecraft:family/log_source", "minecraft:block/oak_log", "variant shares retrieval family but not outcome identity", "Minecraft registry"),
    ActionObjectSignatureEntryV2("redstone", "redstone ore", "minecraft:family/redstone_source", "minecraft:item/redstone", "Controller searches source ore for item task", "Controller and task registry"),
    ActionObjectSignatureEntryV2("redstone_ore", "redstone ore", "minecraft:family/redstone_source", "minecraft:block/redstone_ore", "ore block is distinct from product", "MineDojo voxel vocabulary"),
    ActionObjectSignatureEntryV2("redstone ore", "redstone ore", "minecraft:family/redstone_source", "minecraft:block/redstone_ore", "direct ore block observation", "MineDojo voxel vocabulary"),
    ActionObjectSignatureEntryV2("iron_ingot", "iron ingot", "minecraft:family/iron_product", "minecraft:item/iron_ingot", "smelted product is not source ore", "Minecraft item registry"),
)


@dataclass(frozen=True)
class ActionObjectSignatureRegistryV2(_Hashed):
    rows: tuple[ActionObjectSignatureEntryV2, ...] = SIGNATURE_ROWS
    controller_retrieval_outcome_maps_independent: bool = True
    labels_used_to_select_aliases: bool = False
    unknown_policy: str = "fail_closed"
    registry_id: str = ""

    _id_field = "registry_id"

    def __post_init__(self) -> None:
        if not self.controller_retrieval_outcome_maps_independent:
            raise ValueError("Signature layers were conflated")
        if self.labels_used_to_select_aliases or self.unknown_policy != "fail_closed":
            raise ValueError("Signature aliases leak labels or fail open")
        by_raw = {_token(row.raw_object): row for row in self.rows}
        forbidden = (
            ("wood", "oak_log"),
            ("redstone", "redstone_ore"),
            ("iron_ingot", "iron_ore"),
            ("tree", "log"),
        )
        for left, right in forbidden:
            if by_raw[left].outcome_target_canonical_identity == by_raw[right].outcome_target_canonical_identity:
                raise ValueError(f"Forbidden outcome alias: {left} == {right}")
        if self.registry_id and self.registry_id != self.compute_id():
            raise ValueError("Signature registry ID mismatch")

    def lookup(self, raw: Any) -> ActionObjectSignatureEntryV2 | None:
        normalized = _token(raw)
        return next((row for row in self.rows if _token(row.raw_object) == normalized), None)


def _unknown(layer: str, raw: Any) -> str:
    return f"unknown:{layer}:{_token(raw)}"


def controller_canonical_object_v2(raw: Any, registry: ActionObjectSignatureRegistryV2) -> str:
    row = registry.lookup(raw)
    return row.controller_canonical_object if row else _unknown("controller", raw)


def retrieval_canonical_object_v2(raw: Any, registry: ActionObjectSignatureRegistryV2) -> str:
    row = registry.lookup(raw)
    return row.retrieval_canonical_family if row else _unknown("retrieval", raw)


def outcome_target_canonical_object_v2(raw: Any, registry: ActionObjectSignatureRegistryV2) -> str:
    row = registry.lookup(raw)
    return row.outcome_target_canonical_identity if row else _unknown("outcome", raw)


def _find_raw_telemetry(execution_telemetry: Sequence[Any]) -> Mapping[str, Any] | None:
    for event in reversed(tuple(execution_telemetry)):
        event_type = event.get("event_type", event.get("type", "")) if isinstance(event, Mapping) else getattr(event, "event_type", "")
        if event_type != "action_finished":
            continue
        payload = event.get("payload", event) if isinstance(event, Mapping) else getattr(event, "payload", {})
        result = payload.get("result", {}) if isinstance(payload, Mapping) else {}
        post = result.get("post_state_evidence", {}) if isinstance(result, Mapping) else {}
        raw = post.get("find_observation") if isinstance(post, Mapping) else None
        return raw if isinstance(raw, Mapping) else None
    return None


def find_evidence_from_telemetry_v2(
    action: Action,
    execution_telemetry: Sequence[Any],
    registry: ActionObjectSignatureRegistryV2,
) -> FindObservationEvidenceV2 | None:
    raw = _find_raw_telemetry(execution_telemetry)
    if raw is None:
        return None
    raw_controller = str(raw.get("raw_controller_target") or action.args.get("obj", ""))
    controller_target = controller_canonical_object_v2(raw_controller, registry)
    outcome_target = outcome_target_canonical_object_v2(controller_target, registry)
    steps = []
    for item in raw.get("observation_steps_v2", ()):
        if not isinstance(item, Mapping):
            continue
        pose = item.get("agent_pose", {})
        pose = pose if isinstance(pose, Mapping) else {}
        raw_candidates = tuple(str(value) for value in item.get("raw_detected_target_ids", ()))
        steps.append(
            FindObservationStepEvidenceV2(
                observation_index=int(item.get("observation_index", len(steps))),
                observation_id=str(item.get("observation_id", "")),
                observation_sha256=str(item.get("observation_sha256", "")),
                image_sha256=str(item.get("image_sha256", "")),
                detector_sensor_status=str(item.get("detector_sensor_status", "missing")),
                raw_detected_target_ids=raw_candidates,
                canonical_target_candidates=tuple(
                    outcome_target_canonical_object_v2(value, registry)
                    for value in raw_candidates
                ),
                target_position_evidence=dict(item.get("target_position_evidence", {})),
                visibility_flag=item.get("visibility_flag") if isinstance(item.get("visibility_flag"), bool) else None,
                line_of_sight_flag=item.get("line_of_sight_flag") if isinstance(item.get("line_of_sight_flag"), bool) else None,
                line_of_sight_available=bool(item.get("line_of_sight_available", False)),
                distance_estimate=float(item["distance_estimate"]) if item.get("distance_estimate") is not None else None,
                distance_unit=str(item.get("distance_unit", "")),
                agent_position=tuple(float(value) for value in pose.get("position", ())),
                agent_yaw=float(pose["yaw"]) if pose.get("yaw") is not None else None,
                agent_pitch=float(pose["pitch"]) if pose.get("pitch") is not None else None,
                search_frontier_progress=dict(item.get("search_frontier_progress", {})),
                controller_step_result=str(item.get("controller_step_result", "")),
                sensor_missing=bool(item.get("sensor_missing", False)),
                sensor_error=str(item.get("sensor_error", "")),
                missing_sensor_fields=tuple(str(value) for value in item.get("missing_sensor_fields", ())),
                spatial_relation=str(item.get("spatial_relation", "")),
            )
        )
    return FindObservationEvidenceV2(
        raw_requested_target=str(raw.get("raw_requested_target") or action.args.get("obj", "")),
        raw_controller_target=raw_controller,
        outcome_target_identity=outcome_target,
        steps=tuple(steps),
        search_trace_id=str(raw.get("search_trace_id", "")),
        search_steps_consumed=int(raw.get("search_steps_consumed", 0)),
        search_seconds_consumed=float(raw.get("search_seconds_consumed", 0.0)),
        frozen_search_budget=max(1, int(raw.get("frozen_search_budget", 1))),
        search_budget_exhausted=raw.get("search_budget_exhausted") if isinstance(raw.get("search_budget_exhausted"), bool) else None,
        search_trace_complete=bool(raw.get("search_trace_complete", False)),
        termination_reason=str(raw.get("termination_reason", "")),
        technical_failure=str(raw.get("technical_failure", "")),
    )


@dataclass(frozen=True)
class ActionGoalOutcomeV2:
    controller_status: str
    controller_terminal_reason: str
    expected_action_postcondition: str
    observed_action_postcondition: str
    y_action: int | None
    y_action_evidence_status: str
    terminal_goal_status: str
    y_goal: int | None
    y_goal_evidence_status: str
    record_disposition: str
    failure_type: str = ""
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.y_action not in (0, 1, None) or self.y_goal not in (0, 1, None):
            raise ValueError("V2 outcomes are not ternary labels")
        if self.record_disposition not in RECORD_DISPOSITIONS:
            raise ValueError("Unknown V2 record disposition")
        expected = "accepted_scientific_action" if self.y_action in (0, 1) else (
            "technical_quarantine" if self.y_action_evidence_status == "technical_failure" else "audit_only_ambiguous"
        )
        if self.record_disposition != expected:
            raise ValueError("V2 disposition is not driven exclusively by y_action evidence")


def expected_action_postcondition_v2(
    action: Action, outcome_target_identity: str
) -> str:
    """Describe the action-family postcondition without inferring its label."""

    target = str(outcome_target_identity or "unknown:outcome:")
    if action.name == "find":
        return target
    if action.name == "dig_down":
        return f"agent_y_position_lte:{int(action.args['y_level'])}"
    if action.name == "dig_up":
        return "agent_y_position_increased_or_not_underground"
    if action.name in {"mine", "craft"}:
        return f"inventory_increase:{target}"
    if action.name == "equip":
        return f"held_item_equals:{target}"
    if action.name == "move_to":
        return f"target_within_interaction_distance:{target}"
    if action.name == "fight":
        return f"target_entity_inactive:{target}"
    if action.name == "apply":
        return f"object_state_changed:{target}"
    return f"unsupported_action_family:{_token(action.name)}"


def classify_action_pair_v2(reference_signature: str, candidate_signature: str) -> str:
    """Classify action comparability without declaring different targets equivalent."""

    reference = str(reference_signature).strip()
    candidate = str(candidate_signature).strip()
    reference_family, separator, reference_arguments = reference.partition(":")
    candidate_family, candidate_separator, candidate_arguments = candidate.partition(":")
    if separator and candidate_separator and _token(reference_family) == _token(
        candidate_family
    ):
        if _token(reference_arguments) == _token(candidate_arguments):
            return "exact_action_signature"
        return "same_action_family_different_arguments"
    if reference == candidate:
        return "exact_action_signature"
    return "different_action_family"


def _distance_contract_satisfied(step: FindObservationStepEvidenceV2) -> bool:
    if step.distance_estimate is None or step.distance_unit != "voxel_blocks":
        return False
    limits = {
        "within_frozen_voxel_observation_volume": math.sqrt(75.0),
        "within_frozen_adjacent_voxel_set": math.sqrt(3.0),
    }
    return step.spatial_relation in limits and 0.0 <= step.distance_estimate <= limits[step.spatial_relation]


def action_goal_outcome_v2(
    *,
    action: Action,
    expected_outcome_target: str,
    controller_called: bool,
    controller_success: bool,
    controller_exception: str,
    find_evidence: FindObservationEvidenceV2 | None,
    task_completed: bool,
    evaluator_called: bool,
    evaluator_error: str,
    safety_policy: SafetyTerminationPolicyV2,
) -> ActionGoalOutcomeV2:
    if controller_exception or not controller_called:
        controller_status = "technical_failure"
    else:
        controller_status = "success" if controller_success else "failure"
    terminal_reason = find_evidence.termination_reason if find_evidence else ""
    expected = expected_action_postcondition_v2(action, expected_outcome_target)
    action_value: int | None = None
    action_status = "evidence_missing"
    observed = ""
    failure_type = ""
    evidence_ids: tuple[str, ...] = ()
    if controller_status == "technical_failure":
        action_status = "technical_failure"
    elif action.name != "find":
        action_status = "action_family_evidence_not_collected"
    elif find_evidence is not None:
        evidence_ids = (find_evidence.evidence_id,)
        if find_evidence.technical_failure:
            action_status = "technical_failure"
        else:
            identity_resolved = (
                not expected_outcome_target.startswith("unknown:")
                and find_evidence.outcome_target_identity == expected_outcome_target
            )
            trace_counts_complete = (
                find_evidence.search_steps_consumed == len(find_evidence.steps)
            )
            matching = tuple(
                step
                for step in find_evidence.steps
                if identity_resolved
                and trace_counts_complete
                and find_evidence.search_trace_complete
                and step.required_sensor_complete
                and step.visibility_flag is True
                and expected_outcome_target in step.canonical_target_candidates
                and _distance_contract_satisfied(step)
                and (not step.line_of_sight_available or step.line_of_sight_flag is True)
            )
            if matching:
                action_value = 1
                action_status = "complete_success_evidence"
                observed = expected_outcome_target
            else:
                all_sensors = bool(find_evidence.steps) and all(
                    step.required_sensor_complete for step in find_evidence.steps
                )
                no_match = all(
                    expected_outcome_target not in step.canonical_target_candidates
                    or step.visibility_flag is not True
                    for step in find_evidence.steps
                )
                bounded = all((
                    find_evidence.search_budget_exhausted is True,
                    find_evidence.termination_reason == "bounded_search_budget_exhausted",
                ))
                safety = all((
                    safety_policy.selected_candidate == "S1",
                    find_evidence.termination_reason == "safety_clearance_stop",
                ))
                if identity_resolved and trace_counts_complete and find_evidence.search_trace_complete and all_sensors and no_match and (bounded or safety):
                    action_value = 0
                    action_status = "complete_bounded_failure_evidence" if bounded else "complete_safety_failure_evidence"
                    failure_type = "bounded_search_exhausted" if bounded else safety_policy.failure_type
                else:
                    action_status = "incomplete_or_ambiguous_evidence"
    if evaluator_error:
        goal_status, goal_value, goal_evidence = "technical_failure", None, "evaluator_error"
    elif not evaluator_called:
        goal_status, goal_value, goal_evidence = "unresolved", None, "evaluator_not_called"
    elif task_completed:
        goal_status, goal_value, goal_evidence = "success", 1, "evaluator_complete"
    else:
        goal_status, goal_value, goal_evidence = "failure", 0, "evaluator_complete"
    disposition = "accepted_scientific_action" if action_value in (0, 1) else (
        "technical_quarantine" if action_status == "technical_failure" else "audit_only_ambiguous"
    )
    return ActionGoalOutcomeV2(
        controller_status=controller_status,
        controller_terminal_reason=terminal_reason,
        expected_action_postcondition=expected,
        observed_action_postcondition=observed,
        y_action=action_value,
        y_action_evidence_status=action_status,
        terminal_goal_status=goal_status,
        y_goal=goal_value,
        y_goal_evidence_status=goal_evidence,
        record_disposition=disposition,
        failure_type=failure_type,
        evidence_ids=evidence_ids,
    )


@dataclass(frozen=True)
class D1SceneCompatibilityRowV2:
    task: str
    raw_action_object_signature: str
    controller_canonical_signature: str
    retrieval_canonical_signature: str
    compatible_pool_size: int
    incompatible_pool_size: int
    top_3: tuple[Mapping[str, Any], ...]
    coverage_positive: float
    coverage_negative: float
    margin_c: float | None
    raw_state: str
    conclusion: str


@dataclass(frozen=True)
class D1LabelFreeSceneCompatibilityAudit(_Hashed):
    d1_closeout_release_id: str
    signature_registry_id: str
    rows: tuple[D1SceneCompatibilityRowV2, ...]
    candidate_b_id: str = CANDIDATE_B_ID
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    y_action_used: bool = False
    y_goal_used: bool = False
    controller_success_used: bool = False
    task_success_used: bool = False
    memory_written: bool = False
    gamma_changed: bool = False
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if any((self.y_action_used, self.y_goal_used, self.controller_success_used, self.task_success_used, self.memory_written, self.gamma_changed)):
            raise ValueError("Scene compatibility audit used labels or changed frozen state")
        if self.candidate_b_id != CANDIDATE_B_ID or self.gamma_text != GAMMA_TEXT:
            raise ValueError("Scene audit changed Candidate B or Gamma")
        if tuple(row.task for row in self.rows) != D1_TASK_ORDER:
            raise ValueError("Scene audit task order changed")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Scene compatibility audit ID mismatch")


def build_label_free_scene_audit(
    records: Sequence[Mapping[str, Any]],
    *,
    closeout_id: str,
    registry: ActionObjectSignatureRegistryV2,
) -> D1LabelFreeSceneCompatibilityAudit:
    rows = []
    for record in records:
        pre = record["pre"]
        action = pre["action"]
        raw_object = str(action.get("args", {}).get("obj", ""))
        family = str(action.get("name", ""))
        controller_object = controller_canonical_object_v2(raw_object, registry)
        retrieval_object = retrieval_canonical_object_v2(raw_object, registry)
        environment = pre["environment"]
        all_items = tuple(environment.get("compatible_pool", ())) + tuple(environment.get("incompatible_pool", ()))
        compatible = []
        incompatible = []
        for item in all_items:
            signature = str(item.get("action_signature", ""))
            item_family, item_retrieval = _retrieval_family_from_signature_v2(
                signature, registry
            )
            (compatible if item_family == family and item_retrieval == retrieval_object else incompatible).append(item)
        ranked = sorted(all_items, key=lambda item: float(item.get("score", 0.0)), reverse=True)[:3]
        rows.append(D1SceneCompatibilityRowV2(
            task=str(pre["binding"]["task"] if str(pre["binding"]["task"]).startswith("mine ") else f"mine {pre['binding']['task']}"),
            raw_action_object_signature=f"{family}:{raw_object}",
            controller_canonical_signature=f"{family}:{controller_object}",
            retrieval_canonical_signature=f"{family}:{retrieval_object}",
            compatible_pool_size=len(compatible),
            incompatible_pool_size=len(incompatible),
            top_3=tuple({"exemplar_id": str(item.get("exemplar_id", "")), "score": float(item.get("score", 0.0))} for item in ranked),
            coverage_positive=float(environment.get("coverage_positive", 0.0)),
            coverage_negative=float(environment.get("coverage_negative", 0.0)),
            margin_c=float(environment["contrast"]) if environment.get("contrast") is not None else None,
            raw_state=str(environment.get("raw_state", "unknown")),
            conclusion="compatible_support_present" if compatible else "memory_support_gap",
        ))
    return D1LabelFreeSceneCompatibilityAudit(
        d1_closeout_release_id=closeout_id,
        signature_registry_id=registry.with_id().registry_id,
        rows=tuple(rows),
    ).with_id()


def _retrieval_family_from_signature_v2(
    signature: str, registry: ActionObjectSignatureRegistryV2
) -> tuple[str, str]:
    action_family, separator, raw_object = str(signature).partition(":")
    if not separator:
        return "", _unknown("retrieval", signature)
    aliases = {
        "minecraft:block/log_source": "minecraft:family/log_source",
        "minecraft:block/wood": "minecraft:family/log_source",
        "minecraft:block/sapling": "minecraft:family/sapling",
        "minecraft:item/sapling": "minecraft:family/sapling",
        "minecraft:block/iron_ore": "minecraft:family/iron_ore_source",
        "minecraft:block/redstone_ore": "minecraft:family/redstone_source",
        "minecraft:item/redstone": "minecraft:family/redstone_source",
    }
    retrieval = aliases.get(raw_object)
    if retrieval is None:
        retrieval = retrieval_canonical_object_v2(raw_object.split("/")[-1], registry)
    return _token(action_family), retrieval


def canonicalize_bilateral_evidence_v2(
    evidence: BilateralEvidenceV4_1,
    *,
    action: Action,
    registry: ActionObjectSignatureRegistryV2,
    top_k: int,
    minimum_count: int,
    gamma_minus: float,
    gamma_plus: float,
) -> BilateralEvidenceV4_1:
    target_family = _token(action.name)
    target_retrieval = retrieval_canonical_object_v2(action.args.get("obj", ""), registry)
    items = tuple(evidence.compatible_pool) + tuple(evidence.incompatible_pool)
    compatible = []
    incompatible = []
    for item in items:
        item_family, item_retrieval = _retrieval_family_from_signature_v2(
            item.action_signature, registry
        )
        (compatible if (item_family, item_retrieval) == (target_family, target_retrieval) else incompatible).append(item)
    compatible.sort(key=lambda item: (-item.score, item.exemplar_id))
    incompatible.sort(key=lambda item: (-item.score, item.exemplar_id))
    positive = tuple(compatible[:top_k])
    negative = tuple(incompatible[:top_k])
    coverage_positive = min(1.0, len(positive) / max(1, minimum_count))
    coverage_negative = min(1.0, len(negative) / max(1, minimum_count))
    contrast = None
    if positive and negative:
        contrast = sum(item.score for item in positive) / len(positive) - sum(
            item.score for item in negative
        ) / len(negative)
    if coverage_positive < 1.0 or coverage_negative < 1.0 or contrast is None:
        raw_state = "unknown"
    elif contrast <= gamma_minus:
        raw_state = "likely_failure"
    elif contrast >= gamma_plus:
        raw_state = "likely_success"
    else:
        raw_state = "unknown"
    return BilateralEvidenceV4_1(
        query_observation_id=evidence.query_observation_id,
        query_observation_hash=evidence.query_observation_hash,
        action_signature=f"{target_family}:{target_retrieval}",
        compatible_pool=tuple(compatible),
        incompatible_pool=tuple(incompatible),
        positive=positive,
        negative=negative,
        coverage_positive=coverage_positive,
        coverage_negative=coverage_negative,
        contrast=contrast,
        raw_state=raw_state,
    )


@dataclass(frozen=True)
class PreExecutionRecordV2:
    record_id: str
    binding: Any
    decision_index: int
    action: Mapping[str, Any]
    subgoal: str
    raw_object_signature: str
    controller_canonical_signature: str
    retrieval_canonical_signature: str
    outcome_target_canonical_identity: str
    confidence: str
    failure_mode: str
    same_generation_confidence: bool
    planner_call_count: int
    pre_state: StateEvidenceV4_1
    knowledge: Any
    raw_environment: BilateralEvidenceV4_1
    environment: BilateralEvidenceV4_1
    evaluation_before_action_calls: int = 0
    memory_write_count: int = 0
    acquisition_write_count: int = 0

    def __post_init__(self) -> None:
        if not self.same_generation_confidence or self.planner_call_count != 1:
            raise ValueError("D2 requires one-call same-generation Planner evidence")
        if any((self.evaluation_before_action_calls, self.memory_write_count, self.acquisition_write_count)):
            raise ValueError("D2 pre-action isolation changed")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionRecordV2:
    pre: PreExecutionRecordV2
    post_state: StateEvidenceV4_1
    controller: ControllerReceiptV4_1
    outcome: ActionGoalOutcomeV2
    engineering_diagnostic_only: bool = True
    formal_fitting_eligible: bool = False
    record_hash: str = ""

    def __post_init__(self) -> None:
        action = Action.from_dict(self.pre.action)
        expected = expected_action_postcondition_v2(
            action, self.pre.outcome_target_canonical_identity
        )
        if self.outcome.expected_action_postcondition != expected:
            raise ValueError("D2 outcome postcondition does not match pre-action family")
        if action.name != "find" and self.outcome.y_action is not None:
            raise ValueError("D2 non-find action lacks a dedicated binary evidence contract")

    def with_hash(self):
        payload = asdict(self)
        payload.pop("record_hash", None)
        return replace(self, record_hash=canonical_sha256(payload))

    def to_dict(self) -> dict[str, Any]:
        item = self if self.record_hash else self.with_hash()
        return asdict(item)


class AtomicDecisionStoreV2:
    """Exclusive D2 store routed only by the action-evidence disposition."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        for disposition in RECORD_DISPOSITIONS:
            (self.root / disposition).mkdir(parents=True, exist_ok=True)

    def _path(self, disposition: str, record_id: str) -> Path:
        return self.root / disposition / f"{record_id}.json"

    @staticmethod
    def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def should_execute(self, record_id: str) -> bool:
        return not any(
            self._path(name, record_id).exists()
            for name in RECORD_DISPOSITIONS
            if name != "incomplete_pending"
        )

    def persist_pre(self, record: PreExecutionRecordV2) -> str:
        if not self.should_execute(record.record_id):
            return "completed_do_not_relaunch"
        path = self._path("incomplete_pending", record.record_id)
        payload = record.to_dict()
        if path.exists():
            if canonical_json(json.loads(path.read_text(encoding="utf-8"))) != canonical_json(payload):
                raise ValueError("D2 pending record collision")
            return "pending_resume"
        self._write_exclusive(path, payload)
        return "created"

    def join_post(self, record: DecisionRecordV2) -> Path:
        item = record.with_hash()
        pending = self._path("incomplete_pending", item.pre.record_id)
        if not pending.exists():
            raise ValueError("D2 post receipt has no persisted pre-record")
        target = self._path(item.outcome.record_disposition, item.pre.record_id)
        payload = item.to_dict()
        if target.exists():
            if canonical_json(json.loads(target.read_text(encoding="utf-8"))) != canonical_json(payload):
                raise ValueError("D2 final record collision")
        else:
            temporary = target.with_suffix(".tmp")
            self._write_exclusive(temporary, payload)
            os.replace(temporary, target)
        pending.unlink(missing_ok=True)
        return target


class TrackECollectorV2:
    """Prospective D2 collector; not executable without a later receipt."""

    supports_dual_level_outcomes = True

    def __init__(
        self,
        *,
        memory: Any,
        binding: Any,
        rule_registry: Any,
        retrieval_policy: Any,
        store: AtomicDecisionStoreV2,
        dependency_support_threshold: int,
        gamma_minus: float,
        gamma_plus: float,
        signature_registry: ActionObjectSignatureRegistryV2,
        safety_policy: SafetyTerminationPolicyV2,
    ) -> None:
        if not memory.readonly:
            raise ValueError("D2 requires read-only Paper Memory")
        binding.require_execution_authorized()
        if (str(gamma_minus), str(gamma_plus)) != GAMMA_TEXT[1:]:
            raise ValueError("D2 requires frozen Candidate-B Gamma")
        self.memory = memory
        self.binding = binding
        self.rule_registry = rule_registry
        self.retrieval_policy = retrieval_policy
        self.store = store
        self.dependency_support_threshold = int(dependency_support_threshold)
        self.gamma_minus = float(gamma_minus)
        self.gamma_plus = float(gamma_plus)
        self.signature_registry = signature_registry
        self.safety_policy = safety_policy
        self.errors: list[str] = []
        self._pending: dict[tuple[str, int, str], PreExecutionRecordV2] = {}
        self.materialized_paths: list[str] = []

    def prepare_attempt(
        self, *, plan: Plan, state: AgentState, context: Any, episode_id: str, attempt: int
    ) -> bool:
        if episode_id != self.binding.episode_id:
            raise ValueError("D2 episode differs from binding")
        if len(plan.steps) != 1 or len(plan.steps[0].actions) != 1:
            raise ValueError("D2 executes one original high-level action")
        step = plan.steps[0]
        action = step.actions[0]
        metadata = dict(step.metadata)
        if not metadata.get("v4_1_same_generation") or metadata.get("v4_1_planner_call_count") != 1:
            raise ValueError("D2 Planner evidence is not one-call")
        if metadata.get("v4_1_prompt_id") != self.binding.planner_prompt_id or metadata.get("v4_1_parser_id") != self.binding.planner_parser_id:
            raise ValueError("D2 Planner lineage mismatch")
        raw_object = str(action.args.get("obj", ""))
        controller_object = controller_canonical_object_v2(raw_object, self.signature_registry)
        retrieval_object = retrieval_canonical_object_v2(raw_object, self.signature_registry)
        outcome_object = outcome_target_canonical_object_v2(controller_object, self.signature_registry)
        retrieval_signature = f"{_token(action.name)}:{retrieval_object}"
        decision_index = int(attempt) - 1
        record_id = deterministic_record_id(self.binding, decision_index, retrieval_signature)
        if not self.store.should_execute(record_id):
            return False
        rule_evidence = build_rule_evidence_from_frozen_state(
            action=action,
            state=state,
            memory=self.memory,
            dependency_support_threshold=self.dependency_support_threshold,
        )
        knowledge = extract_knowledge_features_v4_1(
            self.rule_registry, action.name, rule_evidence
        )
        image_vector = getattr(context, "image_vector", None)
        if image_vector is None:
            raise ValueError("D2 requires a pre-action MineCLIP vector")
        raw_environment = bilateral_retrieve_v4_1(
            memory=self.memory,
            state=state,
            image_vector=image_vector,
            action=action,
            policy=self.retrieval_policy,
            gamma_minus=self.gamma_minus,
            gamma_plus=self.gamma_plus,
        )
        environment = canonicalize_bilateral_evidence_v2(
            raw_environment,
            action=action,
            registry=self.signature_registry,
            top_k=self.retrieval_policy.top_k_per_side,
            minimum_count=self.retrieval_policy.minimum_count_per_side,
            gamma_minus=self.gamma_minus,
            gamma_plus=self.gamma_plus,
        )
        pre = PreExecutionRecordV2(
            record_id=record_id,
            binding=self.binding,
            decision_index=decision_index,
            action=action.to_dict(),
            subgoal=str(metadata.get("local_subgoal", "")).strip(),
            raw_object_signature=f"{action.name}:{raw_object}",
            controller_canonical_signature=f"{action.name}:{controller_object}",
            retrieval_canonical_signature=retrieval_signature,
            outcome_target_canonical_identity=outcome_object,
            confidence=str(metadata.get("v4_1_confidence", "")),
            failure_mode=str(metadata.get("v4_1_failure_mode", "")),
            same_generation_confidence=True,
            planner_call_count=1,
            pre_state=_state_evidence_from_agent(state),
            knowledge=knowledge,
            raw_environment=raw_environment,
            environment=environment,
        )
        if self.store.persist_pre(pre) == "completed_do_not_relaunch":
            return False
        self._pending[(plan.plan_id, plan.version, step.step_id)] = pre
        return True

    def finalize_attempt(
        self,
        *,
        plan: Plan,
        episode_id: str,
        execution_telemetry: Sequence[Any],
        confidence_observations: Sequence[Mapping[str, Any]],
        task_completed: bool,
        attempt: int,
        evaluator_called: bool,
        evaluator_error: str,
    ) -> None:
        del attempt
        if episode_id != self.binding.episode_id or confidence_observations:
            raise ValueError("D2 finalize lineage/confidence isolation mismatch")
        step = plan.steps[0]
        pre = self._pending.get((plan.plan_id, plan.version, step.step_id))
        if pre is None:
            raise ValueError("D2 finalization has no persisted pre-record")
        post, controller = _post_state_from_telemetry(pre.pre_state, execution_telemetry)
        evidence = find_evidence_from_telemetry_v2(
            step.actions[0], execution_telemetry, self.signature_registry
        )
        outcome = action_goal_outcome_v2(
            action=step.actions[0],
            expected_outcome_target=pre.outcome_target_canonical_identity,
            controller_called=controller.called,
            controller_success=controller.success,
            controller_exception=controller.exception_type,
            find_evidence=evidence,
            task_completed=task_completed,
            evaluator_called=evaluator_called,
            evaluator_error=evaluator_error,
            safety_policy=self.safety_policy,
        )
        record = DecisionRecordV2(
            pre=pre,
            post_state=post,
            controller=controller,
            outcome=outcome,
        )
        self.materialized_paths.append(str(self.store.join_post(record)))


@dataclass(frozen=True)
class D2PairedAssignment:
    order: int
    formal_task: str
    runtime_task: str
    terminal_task: str
    task_asset: str
    task_asset_sha256: str
    seed_commitment: str
    d1_origin_assignment_id: str
    paired_replay: bool = True
    independent_sample: bool = False
    engineering_diagnostic_only: bool = True
    fitting_eligible: bool = False
    calibration_eligible: bool = False
    holdout_eligible: bool = False
    final_evaluation_eligible: bool = False
    assignment_id: str = ""

    def with_id(self):
        payload = asdict(self)
        payload.pop("assignment_id", None)
        return replace(self, assignment_id=canonical_sha256(payload))


@dataclass(frozen=True)
class D2PairedDiagnosticAssignments(_Hashed):
    source_commit: str
    d1_assignments_id: str
    rows: tuple[D2PairedAssignment, ...]
    task_seed_order_identical_to_d1: bool = True
    plaintext_seeds_stored: bool = False
    minedojo_execution_permitted: bool = False
    assignments_id: str = ""

    _id_field = "assignments_id"

    def __post_init__(self) -> None:
        if tuple(row.formal_task for row in self.rows) != D1_TASK_ORDER:
            raise ValueError("D2 paired task order differs from D1")
        if not self.task_seed_order_identical_to_d1 or self.plaintext_seeds_stored:
            raise ValueError("D2 is not a commitment-preserving paired replay")
        if self.minedojo_execution_permitted:
            raise ValueError("D2 assignments cannot authorize execution")
        if any((not row.paired_replay or row.independent_sample or not row.engineering_diagnostic_only) for row in self.rows):
            raise ValueError("D2 paired scientific exclusion changed")
        if self.assignments_id and self.assignments_id != self.compute_id():
            raise ValueError("D2 assignments ID mismatch")


@dataclass(frozen=True)
class D2PairedDiagnosticSeal(_Hashed):
    source_commit: str
    assignments_id: str
    ordered_assignment_root: str
    d1_ordered_assignment_root: str
    task_seed_order_identical_to_d1: bool = True
    paired_replay: bool = True
    independent_sample: bool = False
    minedojo_execution_permitted: bool = False
    seal_id: str = ""

    _id_field = "seal_id"

    def __post_init__(self) -> None:
        if not self.task_seed_order_identical_to_d1 or not self.paired_replay or self.independent_sample:
            raise ValueError("D2 seal is not paired to D1")
        if self.minedojo_execution_permitted:
            raise ValueError("D2 seal cannot authorize execution")
        if self.seal_id and self.seal_id != self.compute_id():
            raise ValueError("D2 seal ID mismatch")


@dataclass(frozen=True)
class D2PairedDiagnosticExclusionAudit(_Hashed):
    assignments_id: str
    fitting_eligible: bool = False
    calibration_eligible: bool = False
    cdt_identification_eligible: bool = False
    holdout_eligible: bool = False
    final_evaluation_eligible: bool = False
    d1_d2_independent_sample_count: int = 0
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if any((self.fitting_eligible, self.calibration_eligible, self.cdt_identification_eligible, self.holdout_eligible, self.final_evaluation_eligible, self.d1_d2_independent_sample_count)):
            raise ValueError("D2 exclusion audit opened scientific use")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("D2 exclusion audit ID mismatch")


@dataclass(frozen=True)
class D1D2ScientificPayloadEquivalenceAudit(_Hashed):
    d1_assignments_id: str
    d2_assignments_id: str
    same_tasks: bool
    same_task_assets: bool
    same_seed_commitments: bool
    same_order: bool
    only_instrumentation_changed: bool
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if not all((self.same_tasks, self.same_task_assets, self.same_seed_commitments, self.same_order, self.only_instrumentation_changed)):
            raise ValueError("D1/D2 paired scientific payload differs")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("D1/D2 equivalence audit ID mismatch")


@dataclass(frozen=True)
class Round513E6D2SourceHardeningAudit(_Hashed):
    source_commit: str
    d1_closeout_release_id: str
    outcome_schema_id: str
    find_contract_id: str
    safety_policy_id: str
    signature_registry_id: str
    tests_dc3pa_passed: int
    minedojo_marked_passed: int
    relevant_skips: int
    snapshot_guard_passed: bool
    memory_write_probe_rejected: bool
    historical_gates_passed: bool
    github_actions_conclusion: str
    controller_action_behavior_changed: bool = False
    controller_env_step_count_changed: bool = False
    evaluator_behavior_changed: bool = False
    memory_changed: bool = False
    candidate_or_gamma_changed: bool = False
    minedojo_launch_count: int = 0
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.relevant_skips or not all((self.snapshot_guard_passed, self.memory_write_probe_rejected, self.historical_gates_passed)):
            raise ValueError("D2 source hardening gate is incomplete")
        if self.github_actions_conclusion != "success":
            raise ValueError("D2 source does not have green Actions")
        if any((self.controller_action_behavior_changed, self.controller_env_step_count_changed, self.evaluator_behavior_changed, self.memory_changed, self.candidate_or_gamma_changed, self.minedojo_launch_count)):
            raise ValueError("D2 source hardening crossed a frozen boundary")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("D2 source hardening audit ID mismatch")


@dataclass(frozen=True)
class Round513E6D2RuntimeRelease(_Hashed):
    source_commit: str
    source_hardening_audit_id: str
    d1_closeout_release_id: str
    outcome_schema_id: str
    find_contract_id: str
    safety_semantics_audit_id: str
    safety_policy_id: str
    signature_registry_id: str
    scene_compatibility_audit_id: str
    planner_schema_id: str
    planner_prompt_id: str
    planner_parser_id: str
    rule_registry_id: str
    dependency_schema_id: str
    budget_profile_id: str
    technical_retry_policy_id: str
    technical_retry_policy_file_sha256: str
    process_cleanup_policy_id: str
    process_cleanup_policy_file_sha256: str
    paper_memory_release_id: str
    scene_exemplar_release_id: str
    mineclip_policy_id: str
    controller_id: str
    evaluator_id: str
    scientific_contracts: tuple[ScientificContractReferenceD1, ...]
    candidate_b_id: str = CANDIDATE_B_ID
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    memory_readonly: bool = True
    acquisition_writes: int = 0
    evaluation_before_action_calls: int = 0
    minedojo_execution_permitted: bool = False
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        if self.candidate_b_id != CANDIDATE_B_ID or self.gamma_text != GAMMA_TEXT:
            raise ValueError("D2 runtime changed Candidate B or Gamma")
        if not self.memory_readonly or self.acquisition_writes or self.evaluation_before_action_calls:
            raise ValueError("D2 runtime changed Memory/Evaluation isolation")
        if len(self.technical_retry_policy_file_sha256) != 64 or len(self.process_cleanup_policy_file_sha256) != 64:
            raise ValueError("D2 runtime policy raw SHA binding is incomplete")
        required = {"planner_schema", "rule_registry", "bilateral_retrieval_policy", "support_policy"}
        if not required.issubset({item.contract_type for item in self.scientific_contracts}):
            raise ValueError("D2 runtime scientific contract inventory is incomplete")
        if self.minedojo_execution_permitted:
            raise ValueError("D2 runtime cannot authorize execution")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("D2 runtime release ID mismatch")


D2_AUTH_DECLARATIONS = (
    "D1 original records remain immutable and are not relabelled.",
    "D2 is a paired instrumentation replay of the same three D1 assignments.",
    "D1 and D2 are not independent performance samples.",
    "D2 records are ineligible for fitting and calibration.",
    "y_action and y_goal are recorded independently.",
    "y_goal never backfills y_action.",
    "Scientific failures are not retried.",
    "Technical retry is limited to the frozen policy.",
    "Candidate B and Gamma remain unchanged and will not be adjusted from D2.",
    "Paper Memory remains read-only and Acquisition writes remain zero.",
    "Evaluation before the original action remains disabled.",
    "The formal nine-assignment and Development campaigns remain closed.",
    "Holdout, Final Evaluation, and Round 6 remain closed.",
)


@dataclass(frozen=True)
class Round513E6D2DiagnosticAuthorizationInput(_Hashed):
    source_commit: str
    runtime_release_id: str
    d1_closeout_release_id: str
    action_goal_outcome_schema_id: str
    find_observation_contract_id: str
    safety_termination_policy_id: str
    signature_registry_id: str
    scene_compatibility_audit_id: str
    assignments_id: str
    assignment_seal_id: str
    ordered_assignment_root: str
    pending_binding_root: str
    pending_execution_manifest_root: str
    exclusion_audit_id: str
    equivalence_audit_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    planner_schema_id: str
    planner_prompt_id: str
    planner_parser_id: str
    controller_id: str
    evaluator_id: str
    paper_memory_release_id: str
    scene_exemplar_release_id: str
    mineclip_policy_id: str
    primary_gate: str = "accepted_y_action_labels>=2/3_and_log_positive_control_not_ambiguous"
    secondary_diagnostics: tuple[str, ...] = (
        "compatible_pool_coverage", "environment_state_distribution", "provider_controller_technical_stability"
    )
    declarations: tuple[str, ...] = D2_AUTH_DECLARATIONS
    candidate_b_id: str = CANDIDATE_B_ID
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    authorization_status: str = "pending_exact_zyf_authorization"
    d2_execution_permitted: bool = False
    minedojo_launch_count: int = 0
    authorization_input_id: str = ""

    _id_field = "authorization_input_id"

    def __post_init__(self) -> None:
        if self.declarations != D2_AUTH_DECLARATIONS:
            raise ValueError("D2 authorization declarations changed")
        if self.candidate_b_id != CANDIDATE_B_ID or self.gamma_text != GAMMA_TEXT:
            raise ValueError("D2 authorization changed Candidate B or Gamma")
        if self.authorization_status != "pending_exact_zyf_authorization":
            raise ValueError("D2 authorization input is not pending")
        if self.d2_execution_permitted or self.minedojo_launch_count:
            raise ValueError("D2 authorization input self-authorized execution")
        if self.authorization_input_id and self.authorization_input_id != self.compute_id():
            raise ValueError("D2 authorization input ID mismatch")


@dataclass(frozen=True)
class Round513E6D2DiagnosticAuthorizationReceiptR1(_Hashed):
    source_commit: str
    authorization_input_id: str
    authorization_input_file_sha256: str
    runtime_release_id: str
    assignment_seal_id: str
    authorized_task_order: tuple[str, ...]
    approved_by: str
    approval_statement_sha256: str
    contract_kind: str = "Round513E6D2DiagnosticAuthorizationReceiptR1"
    diagnostic_only: bool = True
    paired_replay_only: bool = True
    independent_sample: bool = False
    minedojo_execution_authorized: bool = True
    full_nine_assignment_rerun_permitted: bool = False
    development_or_holdout_permitted: bool = False
    source_change_permitted: bool = False
    receipt_id: str = ""

    _id_field = "receipt_id"

    def __post_init__(self) -> None:
        if self.contract_kind != "Round513E6D2DiagnosticAuthorizationReceiptR1":
            raise ValueError("Unknown D2 authorization receipt contract")
        if self.approved_by != "ZYF" or not self.diagnostic_only:
            raise PermissionError("D2 receipt lacks exact author approval")
        if not self.paired_replay_only or self.independent_sample:
            raise PermissionError("D2 receipt does not authorize only the paired replay")
        if not self.minedojo_execution_authorized:
            raise PermissionError("D2 receipt does not authorize MineDojo")
        if any((self.full_nine_assignment_rerun_permitted, self.development_or_holdout_permitted, self.source_change_permitted)):
            raise PermissionError("D2 receipt opened a frozen boundary")
        if self.authorized_task_order != D1_TASK_ORDER:
            raise ValueError("D2 receipt task order changed")
        if any(len(value) != 64 for value in (self.authorization_input_file_sha256, self.approval_statement_sha256)):
            raise ValueError("D2 receipt raw SHA binding is incomplete")
        if self.receipt_id and self.receipt_id != self.compute_id():
            raise ValueError("D2 receipt ID mismatch")


@dataclass(frozen=True)
class Round513E6D2DiagnosticRunBindingR1(_Hashed):
    execution_source_commit: str
    campaign_id: str
    run_id: str
    episode_id: str
    assignment_id: str
    assignment_order: int
    task: str
    terminal_task: str
    task_asset_sha256: str
    seed: int
    seed_commitment: str
    authorization_input_id: str
    authorization_receipt_id: str
    authorization_receipt_file_sha256: str
    runtime_release_id: str
    assignment_seal_id: str
    outcome_schema_id: str
    find_contract_id: str
    safety_policy_id: str
    signature_registry_id: str
    scene_compatibility_audit_id: str
    planner_schema_id: str
    planner_prompt_id: str
    planner_parser_id: str
    rule_registry_id: str
    dependency_schema_id: str
    paper_memory_release_id: str
    scene_exemplar_release_id: str
    mineclip_policy_id: str
    controller_id: str
    evaluator_id: str
    budget_profile_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    output_root: str
    contract_kind: str = "Round513E6D2DiagnosticRunBindingR1"
    candidate_b_id: str = CANDIDATE_B_ID
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    diagnostic_only: bool = True
    paired_replay_only: bool = True
    independent_sample: bool = False
    execution_authorized: bool = True
    binding_id: str = ""

    _id_field = "binding_id"

    @property
    def gamma_minus_text(self) -> str:
        return self.gamma_text[1]

    @property
    def gamma_plus_text(self) -> str:
        return self.gamma_text[2]

    def __post_init__(self) -> None:
        if self.contract_kind != "Round513E6D2DiagnosticRunBindingR1":
            raise ValueError("Unknown D2 run binding contract")
        if not self.diagnostic_only or not self.paired_replay_only or self.independent_sample or not self.execution_authorized:
            raise PermissionError("D2 run binding is not paired-diagnostic authorized")
        if self.seed != seed_from_commitment(self.seed_commitment):
            raise ValueError("D2 run seed does not match its frozen commitment")
        if self.candidate_b_id != CANDIDATE_B_ID or self.gamma_text != GAMMA_TEXT:
            raise ValueError("D2 run binding changed Candidate B or Gamma")
        if len(self.authorization_receipt_file_sha256) != 64:
            raise ValueError("D2 run binding lacks the receipt raw SHA")
        if self.binding_id and self.binding_id != self.compute_id():
            raise ValueError("D2 run binding ID mismatch")


@dataclass(frozen=True)
class Round513E6D2DiagnosticExecutionManifestR1(_Hashed):
    execution_source_commit: str
    binding_id: str
    authorization_receipt_id: str
    runtime_release_id: str
    assignment_seal_id: str
    assignment_id: str
    assignment_order: int
    task: str
    task_asset_sha256: str
    seed_commitment: str
    output_root: str
    contract_kind: str = "Round513E6D2DiagnosticExecutionManifestR1"
    diagnostic_only: bool = True
    paired_replay_only: bool = True
    independent_sample: bool = False
    minedojo_execution_permitted: bool = True
    scientific_success_retries: int = 0
    scientific_failure_retries: int = 0
    manifest_id: str = ""

    _id_field = "manifest_id"

    def __post_init__(self) -> None:
        if self.contract_kind != "Round513E6D2DiagnosticExecutionManifestR1":
            raise ValueError("Unknown D2 execution manifest contract")
        if not self.diagnostic_only or not self.paired_replay_only or self.independent_sample:
            raise PermissionError("D2 manifest is not paired-diagnostic only")
        if not self.minedojo_execution_permitted:
            raise PermissionError("D2 manifest does not authorize MineDojo")
        if self.scientific_success_retries or self.scientific_failure_retries:
            raise ValueError("D2 manifest permits scientific retries")
        if self.manifest_id and self.manifest_id != self.compute_id():
            raise ValueError("D2 execution manifest ID mismatch")


_D2_CONTRACT_TYPES: dict[str, tuple[type[_Hashed], str]] = {
    "assignments": (D2PairedDiagnosticAssignments, "assignments_id"),
    "assignment_seal": (D2PairedDiagnosticSeal, "seal_id"),
    "runtime": (Round513E6D2RuntimeRelease, "release_id"),
    "authorization_input": (Round513E6D2DiagnosticAuthorizationInput, "authorization_input_id"),
    "authorization_receipt": (Round513E6D2DiagnosticAuthorizationReceiptR1, "receipt_id"),
    "binding": (Round513E6D2DiagnosticRunBindingR1, "binding_id"),
    "execution_manifest": (Round513E6D2DiagnosticExecutionManifestR1, "manifest_id"),
}


def d2_contract_from_mapping(contract_kind: str, payload: Mapping[str, Any]) -> _Hashed:
    if contract_kind not in _D2_CONTRACT_TYPES:
        raise ValueError("Unknown D2 contract kind")
    item = dict(payload)
    if contract_kind == "assignments":
        item["rows"] = tuple(D2PairedAssignment(**row) for row in item["rows"])
    elif contract_kind == "runtime":
        item["scientific_contracts"] = tuple(
            ScientificContractReferenceD1(**entry) for entry in item["scientific_contracts"]
        )
        item["gamma_text"] = tuple(item["gamma_text"])
    elif contract_kind in {"authorization_input", "binding"}:
        item["gamma_text"] = tuple(item["gamma_text"])
        if contract_kind == "authorization_input":
            item["secondary_diagnostics"] = tuple(item["secondary_diagnostics"])
            item["declarations"] = tuple(item["declarations"])
    elif contract_kind == "authorization_receipt":
        item["authorized_task_order"] = tuple(item["authorized_task_order"])
    cls, _ = _D2_CONTRACT_TYPES[contract_kind]
    return cls(**item)


def load_d2_contract(
    path: Path,
    *,
    contract_kind: str,
    expected_file_sha256: str,
    expected_contract_id: str,
) -> _Hashed:
    if file_sha256(path) != expected_file_sha256:
        raise ValueError("D2 raw file SHA-256 mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("D2 contract payload must be an object")
    contract = d2_contract_from_mapping(contract_kind, payload)
    _, id_field = _D2_CONTRACT_TYPES[contract_kind]
    if getattr(contract, id_field) != expected_contract_id:
        raise ValueError("D2 expected contract ID mismatch")
    return contract


def validate_d2_execution_closure(
    *,
    current_source: str,
    task_path: Path,
    output_root: Path,
    binding: Round513E6D2DiagnosticRunBindingR1,
    authorization: Round513E6D2DiagnosticAuthorizationInput,
    receipt: Round513E6D2DiagnosticAuthorizationReceiptR1,
    assignments: D2PairedDiagnosticAssignments,
    seal: D2PairedDiagnosticSeal,
    runtime: Round513E6D2RuntimeRelease,
    manifest: Round513E6D2DiagnosticExecutionManifestR1,
    authorization_input_file_sha256: str,
    authorization_receipt_file_sha256: str,
) -> D2PairedAssignment:
    sources = {
        binding.execution_source_commit, authorization.source_commit, receipt.source_commit,
        assignments.source_commit, seal.source_commit, runtime.source_commit,
        manifest.execution_source_commit,
    }
    if sources != {current_source}:
        raise ValueError("D2 source closure mismatch")
    ordered_root = canonical_sha256([row.assignment_id for row in assignments.rows])
    if seal.assignments_id != assignments.assignments_id or seal.ordered_assignment_root != ordered_root:
        raise ValueError("D2 assignments/seal closure mismatch")
    if (authorization.assignments_id, authorization.assignment_seal_id, authorization.ordered_assignment_root) != (
        assignments.assignments_id, seal.seal_id, ordered_root
    ):
        raise ValueError("D2 authorization assignment closure mismatch")
    if authorization.runtime_release_id != runtime.release_id:
        raise ValueError("D2 authorization/runtime release mismatch")
    if authorization.d1_closeout_release_id != runtime.d1_closeout_release_id:
        raise ValueError("D2 authorization/D1 closeout lineage mismatch")
    if receipt.authorization_input_id != authorization.authorization_input_id:
        raise ValueError("D2 authorization input/receipt mismatch")
    if receipt.authorization_input_file_sha256 != authorization_input_file_sha256:
        raise ValueError("D2 authorization raw file SHA mismatch")
    if binding.authorization_receipt_file_sha256 != authorization_receipt_file_sha256:
        raise ValueError("D2 authorization receipt raw file SHA mismatch")
    if (receipt.runtime_release_id, receipt.assignment_seal_id) != (runtime.release_id, seal.seal_id):
        raise ValueError("D2 receipt runtime/seal mismatch")
    if (binding.authorization_input_id, binding.authorization_receipt_id,
        binding.runtime_release_id, binding.assignment_seal_id) != (
        authorization.authorization_input_id, receipt.receipt_id, runtime.release_id, seal.seal_id
    ):
        raise ValueError("D2 binding authorization/runtime closure mismatch")
    if (manifest.binding_id, manifest.authorization_receipt_id,
        manifest.runtime_release_id, manifest.assignment_seal_id) != (
        binding.binding_id, receipt.receipt_id, runtime.release_id, seal.seal_id
    ):
        raise ValueError("D2 manifest binding/authorization closure mismatch")
    if Path(binding.output_root).resolve() != output_root.resolve() or Path(manifest.output_root).resolve() != output_root.resolve():
        raise ValueError("D2 output root mismatch")
    selected = tuple(row for row in assignments.rows if row.assignment_id == binding.assignment_id)
    if len(selected) != 1:
        raise ValueError("D2 binding does not select exactly one assignment")
    assignment = selected[0]
    expected = (assignment.order, assignment.runtime_task, assignment.terminal_task,
                assignment.seed_commitment, assignment.task_asset_sha256)
    if (binding.assignment_order, binding.task, binding.terminal_task,
        binding.seed_commitment, binding.task_asset_sha256) != expected:
        raise ValueError("D2 selected assignment binding mismatch")
    if (manifest.assignment_id, manifest.assignment_order, manifest.task,
        manifest.seed_commitment, manifest.task_asset_sha256) != (
        assignment.assignment_id, assignment.order, assignment.runtime_task,
        assignment.seed_commitment, assignment.task_asset_sha256
    ):
        raise ValueError("D2 selected assignment manifest mismatch")
    if file_sha256(task_path) != assignment.task_asset_sha256:
        raise ValueError("D2 task asset SHA-256 mismatch")
    runtime_ids = (
        runtime.outcome_schema_id, runtime.find_contract_id, runtime.safety_policy_id,
        runtime.signature_registry_id, runtime.scene_compatibility_audit_id,
        runtime.planner_schema_id, runtime.planner_prompt_id, runtime.planner_parser_id,
        runtime.rule_registry_id, runtime.dependency_schema_id, runtime.paper_memory_release_id,
        runtime.scene_exemplar_release_id, runtime.mineclip_policy_id, runtime.controller_id,
        runtime.evaluator_id, runtime.budget_profile_id, runtime.technical_retry_policy_id,
        runtime.process_cleanup_policy_id,
    )
    binding_ids = (
        binding.outcome_schema_id, binding.find_contract_id, binding.safety_policy_id,
        binding.signature_registry_id, binding.scene_compatibility_audit_id,
        binding.planner_schema_id, binding.planner_prompt_id, binding.planner_parser_id,
        binding.rule_registry_id, binding.dependency_schema_id, binding.paper_memory_release_id,
        binding.scene_exemplar_release_id, binding.mineclip_policy_id, binding.controller_id,
        binding.evaluator_id, binding.budget_profile_id, binding.technical_retry_policy_id,
        binding.process_cleanup_policy_id,
    )
    if runtime_ids != binding_ids:
        raise ValueError("D2 runtime/binding scientific lineage mismatch")
    if (authorization.action_goal_outcome_schema_id, authorization.find_observation_contract_id,
        authorization.safety_termination_policy_id, authorization.signature_registry_id,
        authorization.scene_compatibility_audit_id) != runtime_ids[:5]:
        raise ValueError("D2 authorization/runtime instrumentation mismatch")
    authorization_ids = (
        authorization.planner_schema_id, authorization.planner_prompt_id,
        authorization.planner_parser_id, authorization.paper_memory_release_id,
        authorization.scene_exemplar_release_id, authorization.mineclip_policy_id,
        authorization.controller_id, authorization.evaluator_id,
        authorization.technical_retry_policy_id, authorization.process_cleanup_policy_id,
    )
    expected_authorization_ids = (
        runtime.planner_schema_id, runtime.planner_prompt_id,
        runtime.planner_parser_id, runtime.paper_memory_release_id,
        runtime.scene_exemplar_release_id, runtime.mineclip_policy_id,
        runtime.controller_id, runtime.evaluator_id,
        runtime.technical_retry_policy_id, runtime.process_cleanup_policy_id,
    )
    if authorization_ids != expected_authorization_ids:
        raise ValueError("D2 authorization/runtime scientific lineage mismatch")
    return assignment


def load_d1_closeout(d1_root: Path) -> tuple[
    Round513D1RawCompleteAudit,
    Round513D1LabelGapAudit,
    Round513D1TechnicalAttemptAudit,
    Round513D1CloseoutRelease,
    tuple[Mapping[str, Any], ...],
    Mapping[str, Any],
]:
    closure = d1_root / "source-hardening" / "execution-closure"
    report_path = closure / "d1_diagnostic_result_summary.json"
    if file_sha256(report_path) != D1_REPORT_FILE_SHA256:
        raise ValueError("D1 report raw SHA-256 mismatch")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("report_id") != D1_REPORT_ID or report.get("source_commit") != D1_EXECUTION_SOURCE_SHA:
        raise ValueError("D1 report lineage mismatch")
    if tuple(report.get("task_order", ())) != D1_TASK_ORDER:
        raise ValueError("D1 report task order changed")
    if (report.get("memory_writes"), report.get("acquisition_writes")) != (0, 0):
        raise ValueError("D1 report contains forbidden writes")
    record_paths = sorted((d1_root / "diagnostic-outputs").glob("*/*/*.json"))
    if len(record_paths) != 3:
        raise ValueError("D1 does not contain exactly three final diagnostic records")
    records = tuple(json.loads(path.read_text(encoding="utf-8")) for path in record_paths)
    rows = tuple(
        D1OutcomeRow(
            order=int(summary["order"]),
            task=str(summary["task"]),
            record_id=str(summary["record_id"]),
            record_hash=str(summary["record_hash"]),
            record_file_sha256=file_sha256(path),
            controller_success=bool(summary["controller_success"]),
            y_action=summary["y_action"],
            y_goal=summary["y_goal"],
            record_disposition=str(summary["record_disposition"]),
            termination_reason=str(summary["termination_reason"]),
        )
        for summary, path in zip(report["rows"], record_paths)
    )
    closure_manifest = json.loads((closure / "execution_closure_manifest.json").read_text(encoding="utf-8"))
    first_attempt_events = tuple(
        json.loads(line)
        for line in (closure / "traces" / "00-sapling.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if any(event.get("event_type") in {"action_started", "controller_completed"} for event in first_attempt_events):
        raise ValueError("D1 quarantined attempt reached an environment action")
    raw_audit = Round513D1RawCompleteAudit(
        d1_source_sha=D1_EXECUTION_SOURCE_SHA,
        report_id=D1_REPORT_ID,
        report_file_sha256=D1_REPORT_FILE_SHA256,
        execution_closure_manifest_id=str(closure_manifest["manifest_id"]),
        rows=rows,
        report_and_records_complete=True,
    ).with_id()
    gap = Round513D1LabelGapAudit(raw_complete_audit_id=raw_audit.audit_id).with_id()
    technical = Round513D1TechnicalAttemptAudit(
        raw_complete_audit_id=raw_audit.audit_id,
        sapling_attempt_1_trace_sha256=file_sha256(closure / "traces" / "00-sapling.jsonl"),
        sapling_attempt_1_console_sha256=file_sha256(closure / "console" / "00-sapling.log"),
        sapling_attempt_2_trace_sha256=file_sha256(closure / "traces" / "00-sapling-attempt2.jsonl"),
        sapling_attempt_2_console_sha256=file_sha256(closure / "console" / "00-sapling-attempt2.log"),
    ).with_id()
    closeout = Round513D1CloseoutRelease(
        raw_complete_audit_id=raw_audit.audit_id,
        label_gap_audit_id=gap.audit_id,
        technical_attempt_audit_id=technical.audit_id,
    ).with_id()
    assignments = json.loads(
        (d1_root / "source-hardening" / "freeze" / "d1_assignments_r1.json").read_text(encoding="utf-8")
    )
    return raw_audit, gap, technical, closeout, records, assignments
