"""Round 5.13E5 prospective observation, label, and signature contracts.

The V4.1.3 contracts are additive. Historical V4.1 records remain immutable
and are never re-labelled by this module.
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
from ..memory.multimodal_memory import MultimodalMemory
from .round513_collection import (
    CHRMLiteBilateralRetrievalPolicyV4_1,
    CHRMLiteRuleTypeRegistryV4_1,
)
from .round513_instrumentation import (
    BilateralEvidenceV4_1,
    BilateralMatchV4_1,
    ControllerReceiptV4_1,
    DecisionRecordV4_1,
    KnowledgeFeaturesV4_1,
    StateEvidenceV4_1,
    StepLabelV4_1,
    TrackERunBindingV4_1,
    _post_state_from_telemetry,
    _state_evidence_from_agent,
    bilateral_retrieve_v4_1,
    build_rule_evidence_from_frozen_state,
    deterministic_record_id,
    extract_knowledge_features_v4_1,
    join_step_outcome_v4_1,
)


SCHEMA_VERSION = 1
ACTION_OUTCOMES = (
    "success",
    "scientific_failure",
    "ambiguous_unobservable",
    "technical_failure",
)
GOAL_OUTCOMES = ("success", "failure", "unresolved", "technical_failure")
RECORD_DISPOSITIONS = (
    "accepted_scientific",
    "audit_only_ambiguous",
    "technical_quarantine",
    "incomplete_pending",
)
FROZEN_FIND_SPATIAL_RELATIONS = (
    "within_frozen_voxel_observation_volume",
    "within_frozen_adjacent_voxel_set",
)
BOUNDED_FIND_TERMINATIONS = ("bounded_search_budget_exhausted",)
GAMMA_CANDIDATE_B = "0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f"
GAMMA_TEXT = ("1.0", "-0.01040883", "0.00744657")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


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
class Round513E4ObservationGapCloseout(_Hashed):
    source_closeout_id: str
    assignments_closed: int = 9
    accepted_action_labels: int = 0
    ambiguous_action_labels: int = 9
    controller_success_signals: int = 7
    terminal_goal_successes: int = 1
    provider_transport_attempts: int = 4
    memory_writes: int = 0
    acquisition_writes: int = 0
    historical_records_relabelled: bool = False
    closeout_id: str = ""

    _id_field = "closeout_id"

    def __post_init__(self) -> None:
        observed = (
            self.assignments_closed,
            self.accepted_action_labels,
            self.ambiguous_action_labels,
            self.controller_success_signals,
            self.terminal_goal_successes,
            self.provider_transport_attempts,
            self.memory_writes,
            self.acquisition_writes,
        )
        if observed != (9, 0, 9, 7, 1, 4, 0, 0):
            raise ValueError("E4 closeout facts differ from the frozen public closeout")
        if self.historical_records_relabelled:
            raise ValueError("Historical E4 records must remain immutable")
        if self.closeout_id and self.closeout_id != self.compute_id():
            raise ValueError("E4 observation closeout hash mismatch")


@dataclass(frozen=True)
class Round513E4ScientificUseRestriction(_Hashed):
    observation_gap_closeout_id: str
    permitted_uses: tuple[str, ...] = (
        "instrumentation_failure_diagnosis",
        "label_free_signature_retrieval_audit",
        "source_hardening_regression_fixture",
    )
    prohibited_uses: tuple[str, ...] = (
        "chrm_fitting",
        "model_environment_calibration",
        "gamma_selection",
        "cdt_estimation",
        "scientific_task_performance_comparison",
    )
    restriction_id: str = ""

    _id_field = "restriction_id"

    def __post_init__(self) -> None:
        if not self.observation_gap_closeout_id:
            raise ValueError("E4 use restriction lacks closeout lineage")
        if set(self.permitted_uses) & set(self.prohibited_uses):
            raise ValueError("E4 use restrictions overlap")
        if self.restriction_id and self.restriction_id != self.compute_id():
            raise ValueError("E4 use restriction hash mismatch")


@dataclass(frozen=True)
class Round513E4FailureAttributionAudit(_Hashed):
    observation_gap_closeout_id: str
    action_family: str = "find"
    missing_postcondition_records: int = 9
    controller_success_is_action_label: bool = False
    terminal_goal_success_is_action_label: bool = False
    primary_attribution: str = "find_postcondition_evidence_not_emitted"
    status: str = "OBSERVATION_CHAIN_GAP"
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.action_family != "find" or self.missing_postcondition_records != 9:
            raise ValueError("E4 attribution facts changed")
        if self.controller_success_is_action_label or self.terminal_goal_success_is_action_label:
            raise ValueError("E4 attribution conflates independent evidence layers")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("E4 attribution hash mismatch")


@dataclass(frozen=True)
class DualLevelOutcomeContractV4_1_3(_Hashed):
    action_label: str = "y_action"
    goal_label: str = "y_goal"
    chrm_primary_label: str = "y_action"
    controller_action_goal_independent: bool = True
    goal_may_override_action: bool = False
    controller_may_override_action: bool = False
    contract_id: str = ""

    _id_field = "contract_id"

    def __post_init__(self) -> None:
        if not self.controller_action_goal_independent:
            raise ValueError("Outcome evidence layers must remain independent")
        if self.goal_may_override_action or self.controller_may_override_action:
            raise ValueError("Outcome contract permits label override")
        if self.chrm_primary_label != "y_action":
            raise ValueError("CHRM-lite primary label changed")
        if self.contract_id and self.contract_id != self.compute_id():
            raise ValueError("Dual-level outcome contract hash mismatch")


@dataclass(frozen=True)
class FindObservationEvidenceV4_1_3:
    raw_requested_target: str
    canonical_requested_target: str
    observation_frame_ids: tuple[str, ...]
    visible_candidate_ids: tuple[str, ...]
    canonical_candidate_ids: tuple[str, ...]
    target_identity_matched: bool | None
    target_visible: bool | None
    target_distance: float | None
    spatial_relation: str
    search_trace_id: str
    search_steps_consumed: int
    search_seconds_consumed: float
    frozen_search_budget: int
    search_budget_exhausted: bool | None
    search_trace_complete: bool
    termination_reason: str
    technical_failure: str = ""

    def __post_init__(self) -> None:
        if self.search_steps_consumed < 0 or self.search_seconds_consumed < 0:
            raise ValueError("Find search consumption cannot be negative")
        if self.frozen_search_budget < 1:
            raise ValueError("Find search budget must be positive")
        if len(self.visible_candidate_ids) != len(self.canonical_candidate_ids):
            raise ValueError("Find candidate raw/canonical lineage is incomplete")

    @property
    def evidence_id(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class ActionTransitionOutcomeV4_1_3:
    action_outcome_status: str
    y_action: int | None
    postcondition_id: str
    evidence_ids: tuple[str, ...]
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.action_outcome_status not in ACTION_OUTCOMES:
            raise ValueError("Unknown action outcome")
        expected = {"success": 1, "scientific_failure": 0}.get(self.action_outcome_status)
        if self.y_action != expected:
            raise ValueError("Action binary label is inconsistent with its status")


@dataclass(frozen=True)
class TerminalGoalOutcomeV4_1_3:
    goal_outcome_status: str
    y_goal: int | None
    evaluator_evidence_ids: tuple[str, ...]
    terminal_state_hash: str
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.goal_outcome_status not in GOAL_OUTCOMES:
            raise ValueError("Unknown terminal goal outcome")
        expected = {"success": 1, "failure": 0}.get(self.goal_outcome_status)
        if self.y_goal != expected:
            raise ValueError("Goal binary label is inconsistent with its status")


@dataclass(frozen=True)
class FindObservationEvidenceContractV4_1_3(_Hashed):
    success_spatial_relations: tuple[str, ...] = FROZEN_FIND_SPATIAL_RELATIONS
    success_requires_identity_match: bool = True
    success_requires_visibility: bool = True
    success_requires_complete_trace: bool = True
    controller_boolean_sufficient: bool = False
    contract_id: str = ""

    _id_field = "contract_id"

    def __post_init__(self) -> None:
        if self.success_spatial_relations != FROZEN_FIND_SPATIAL_RELATIONS:
            raise ValueError("Find spatial relation changed")
        if self.controller_boolean_sufficient:
            raise ValueError("Controller status cannot label a find transition")
        if self.contract_id and self.contract_id != self.compute_id():
            raise ValueError("Find evidence contract hash mismatch")


@dataclass(frozen=True)
class FindBoundedFailurePolicyV4_1_3(_Hashed):
    allowed_termination_reasons: tuple[str, ...] = BOUNDED_FIND_TERMINATIONS
    requires_budget_exhausted: bool = True
    requires_complete_trace: bool = True
    requires_no_identity_match: bool = True
    requires_no_technical_failure: bool = True
    missing_visibility_is_failure: bool = False
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        if self.allowed_termination_reasons != BOUNDED_FIND_TERMINATIONS:
            raise ValueError("Bounded find termination enumeration changed")
        if self.missing_visibility_is_failure:
            raise ValueError("Missing find evidence cannot become a failure")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("Find bounded-failure policy hash mismatch")


@dataclass(frozen=True)
class ActionTransitionLabelPolicyV4_1_3(_Hashed):
    accepted_statuses: tuple[str, ...] = ("success", "scientific_failure")
    excluded_statuses: tuple[str, ...] = (
        "ambiguous_unobservable",
        "technical_failure",
    )
    controller_status_is_evidence_only: bool = True
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        if self.controller_status_is_evidence_only is not True:
            raise ValueError("Controller status became an action label")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("Action label policy hash mismatch")


@dataclass(frozen=True)
class TerminalGoalLabelPolicyV4_1_3(_Hashed):
    evaluator_called_required_for_binary_label: bool = True
    evaluator_error_is_technical: bool = True
    action_label_override_permitted: bool = False
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        if not self.evaluator_called_required_for_binary_label:
            raise ValueError("Goal policy permits an unobserved binary label")
        if self.action_label_override_permitted:
            raise ValueError("Goal policy permits action-label override")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("Goal label policy hash mismatch")


@dataclass(frozen=True)
class OutcomeEvidenceRegistryV4_1_3(_Hashed):
    dual_level_contract_id: str
    action_label_policy_id: str
    goal_label_policy_id: str
    find_evidence_contract_id: str
    find_bounded_failure_policy_id: str
    registry_id: str = ""

    _id_field = "registry_id"

    def __post_init__(self) -> None:
        if not all(
            (
                self.dual_level_contract_id,
                self.action_label_policy_id,
                self.goal_label_policy_id,
                self.find_evidence_contract_id,
                self.find_bounded_failure_policy_id,
            )
        ):
            raise ValueError("Outcome evidence registry lineage is incomplete")
        if self.registry_id and self.registry_id != self.compute_id():
            raise ValueError("Outcome evidence registry hash mismatch")


def action_outcome_v4_1_3(
    *,
    action: Action,
    pre: StateEvidenceV4_1,
    post: StateEvidenceV4_1,
    controller: ControllerReceiptV4_1,
    find_evidence: FindObservationEvidenceV4_1_3 | None = None,
) -> ActionTransitionOutcomeV4_1_3:
    """Create an action label from deterministic postcondition evidence only."""

    if action.name != "find":
        legacy = join_step_outcome_v4_1(
            action=action,
            pre=pre,
            post=post,
            controller=controller,
        )
        return ActionTransitionOutcomeV4_1_3(
            action_outcome_status=legacy.state,
            y_action=legacy.value,
            postcondition_id=legacy.postcondition_id.replace("v4.1:", "v4.1.3:"),
            evidence_ids=(canonical_sha256(legacy.evidence),),
            evidence=legacy.evidence,
        )

    base = {
        "controller_success": controller.success,
        "controller_return_hash": canonical_sha256(controller.return_payload),
    }
    if controller.exception_type or not controller.called:
        reason = controller.exception_type or "controller_not_called"
        return ActionTransitionOutcomeV4_1_3(
            "technical_failure",
            None,
            "v4.1.3:find:postcondition",
            (canonical_sha256({**base, "reason": reason}),),
            {**base, "reason": reason},
        )
    if find_evidence is None:
        return ActionTransitionOutcomeV4_1_3(
            "ambiguous_unobservable",
            None,
            "v4.1.3:find:postcondition",
            (canonical_sha256(base),),
            {**base, "reason": "find_observation_evidence_missing"},
        )
    evidence = {**base, **asdict(find_evidence)}
    evidence_ids = (find_evidence.evidence_id,)
    if find_evidence.technical_failure:
        return ActionTransitionOutcomeV4_1_3(
            "technical_failure",
            None,
            "v4.1.3:find:postcondition",
            evidence_ids,
            evidence,
        )
    success = all(
        (
            find_evidence.search_trace_complete,
            find_evidence.target_visible is True,
            find_evidence.target_identity_matched is True,
            bool(find_evidence.observation_frame_ids),
            find_evidence.spatial_relation in FROZEN_FIND_SPATIAL_RELATIONS,
            find_evidence.canonical_requested_target
            in find_evidence.canonical_candidate_ids,
        )
    )
    if success:
        return ActionTransitionOutcomeV4_1_3(
            "success", 1, "v4.1.3:find:postcondition", evidence_ids, evidence
        )
    bounded_failure = all(
        (
            find_evidence.search_budget_exhausted is True,
            find_evidence.search_trace_complete,
            find_evidence.target_identity_matched is False,
            find_evidence.target_visible is False,
            find_evidence.termination_reason in BOUNDED_FIND_TERMINATIONS,
            bool(find_evidence.observation_frame_ids),
        )
    )
    if bounded_failure:
        return ActionTransitionOutcomeV4_1_3(
            "scientific_failure",
            0,
            "v4.1.3:find:postcondition",
            evidence_ids,
            evidence,
        )
    return ActionTransitionOutcomeV4_1_3(
        "ambiguous_unobservable",
        None,
        "v4.1.3:find:postcondition",
        evidence_ids,
        {**evidence, "reason": "required_find_postcondition_evidence_missing"},
    )


def terminal_goal_outcome_v4_1_3(
    *,
    task_completed: bool,
    evaluator_called: bool,
    evaluator_error: str,
    terminal_state_hash: str,
) -> TerminalGoalOutcomeV4_1_3:
    evidence = {
        "evaluator_called": bool(evaluator_called),
        "task_completed": bool(task_completed),
        "evaluator_error": str(evaluator_error),
    }
    evidence_id = canonical_sha256(evidence)
    if evaluator_error:
        status, value = "technical_failure", None
    elif not evaluator_called:
        status, value = "unresolved", None
    elif task_completed:
        status, value = "success", 1
    else:
        status, value = "failure", 0
    return TerminalGoalOutcomeV4_1_3(
        status,
        value,
        (evidence_id,),
        terminal_state_hash,
        evidence,
    )


def _event_payload(event: Any) -> Mapping[str, Any]:
    if isinstance(event, Mapping):
        payload = event.get("payload", event)
    else:
        payload = getattr(event, "payload", {})
    return payload if isinstance(payload, Mapping) else {}


def _event_type(event: Any) -> str:
    if isinstance(event, Mapping):
        return str(event.get("event_type", event.get("type", "")))
    return str(getattr(event, "event_type", ""))


def find_evidence_from_telemetry_v4_1_3(
    action: Action,
    execution_telemetry: Sequence[Any],
) -> FindObservationEvidenceV4_1_3 | None:
    finished = [
        event
        for event in execution_telemetry
        if _event_type(event) == "action_finished"
    ]
    if not finished:
        return None
    payload = _event_payload(finished[-1])
    result = payload.get("result", {})
    result = result if isinstance(result, Mapping) else {}
    post = result.get("post_state_evidence", {})
    post = post if isinstance(post, Mapping) else {}
    raw = post.get("find_observation")
    if not isinstance(raw, Mapping):
        return None
    family, planner_target = _action_parts(action)
    controller_target = str(
        raw.get("raw_controller_target") or controller_target_v4_1_3(action)
    )
    requested = canonicalize_object_v4_1_3(
        controller_target,
        source_role="controller_target",
        action_family=family,
    )
    candidates = tuple(str(item) for item in raw.get("visible_candidate_ids", ()))
    canonical_candidates = tuple(
        canonicalize_object_v4_1_3(
            item,
            source_role="controller_target",
            action_family=family,
        ).canonical_signature
        for item in candidates
    )
    identity = raw.get("target_identity_matched")
    visible = raw.get("target_visible")
    return FindObservationEvidenceV4_1_3(
        raw_requested_target=str(raw.get("raw_requested_target") or planner_target),
        canonical_requested_target=requested.canonical_signature,
        observation_frame_ids=tuple(str(item) for item in raw.get("observation_frame_ids", ())),
        visible_candidate_ids=candidates,
        canonical_candidate_ids=canonical_candidates,
        target_identity_matched=identity if isinstance(identity, bool) else None,
        target_visible=visible if isinstance(visible, bool) else None,
        target_distance=(
            float(raw["target_distance"])
            if raw.get("target_distance") is not None
            else None
        ),
        spatial_relation=str(raw.get("spatial_relation", "")),
        search_trace_id=str(raw.get("search_trace_id", "")),
        search_steps_consumed=int(raw.get("search_steps_consumed", 0)),
        search_seconds_consumed=float(raw.get("search_seconds_consumed", 0.0)),
        frozen_search_budget=max(1, int(raw.get("frozen_search_budget", 1))),
        search_budget_exhausted=(
            raw.get("search_budget_exhausted")
            if isinstance(raw.get("search_budget_exhausted"), bool)
            else None
        ),
        search_trace_complete=bool(raw.get("search_trace_complete", False)),
        termination_reason=str(raw.get("termination_reason", "")),
        technical_failure=str(raw.get("technical_failure", "")),
    )


def _token(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", " ").replace("_", " ").split())


@dataclass(frozen=True)
class CanonicalObjectV4_1_3:
    raw: str
    normalized: str
    canonical_signature: str
    normalization_rule_id: str
    relation: str


_ACTION_OBJECT_RULES: dict[str, tuple[str, str, str]] = {
    "tree": ("minecraft:block/log_source", "controller.find.tree_to_wood", "controller_observation_alias"),
    "wood": ("minecraft:block/log_source", "minedojo.block.wood", "observation_identifier"),
    "log": ("minecraft:block/log_source", "controller.find.log_to_wood", "controller_observation_alias"),
    "oak_log": ("minecraft:block/log_source", "controller.find.oak_log_to_wood", "variant_alias"),
    "stone": ("minecraft:block/stone", "minedojo.block.stone", "observation_identifier"),
    "cobblestone": ("minecraft:block/stone", "controller.find.cobblestone_to_stone", "source_product_relation"),
    "redstone": ("minecraft:block/redstone_ore", "controller.find.redstone_to_ore", "source_product_relation"),
    "redstone_ore": ("minecraft:block/redstone_ore", "minedojo.block.redstone_ore", "observation_identifier"),
    "iron_ore": ("minecraft:block/iron_ore", "minedojo.block.iron_ore", "observation_identifier"),
    "sapling": ("minecraft:block/sapling", "minedojo.block.sapling", "observation_identifier"),
    "crafting_table": ("minecraft:item/crafting_table", "registry.item.crafting_table", "exact"),
    "wooden_pickaxe": ("minecraft:item/wooden_pickaxe", "registry.item.wooden_pickaxe", "exact"),
}

_GOAL_OBJECT_RULES: dict[str, tuple[str, str, str]] = {
    "log": ("minecraft:item/log", "catalog.goal.log", "exact"),
    "oak_log": ("minecraft:item/log", "catalog.goal.oak_log", "variant_alias"),
    "cobblestone": ("minecraft:item/cobblestone", "catalog.goal.cobblestone", "exact"),
    "redstone": ("minecraft:item/redstone", "catalog.goal.redstone", "exact"),
    "redstone_ore": ("minecraft:block/redstone_ore", "catalog.goal.redstone_ore", "exact"),
    "iron_ore": ("minecraft:block/iron_ore", "catalog.goal.iron_ore", "exact"),
    "iron_ingot": ("minecraft:item/iron_ingot", "catalog.goal.iron_ingot", "exact"),
    "sapling": ("minecraft:item/sapling", "catalog.goal.sapling", "exact"),
    "crafting_table": ("minecraft:item/crafting_table", "catalog.goal.crafting_table", "exact"),
    "wooden_pickaxe": ("minecraft:item/wooden_pickaxe", "catalog.goal.wooden_pickaxe", "exact"),
}


def canonicalize_object_v4_1_3(
    raw: Any,
    *,
    source_role: str,
    action_family: str = "",
) -> CanonicalObjectV4_1_3:
    normalized = _token(raw)
    rules = _GOAL_OBJECT_RULES if source_role == "task_target" else _ACTION_OBJECT_RULES
    rule = rules.get(normalized)
    if rule is None:
        return CanonicalObjectV4_1_3(
            str(raw or ""),
            normalized,
            f"unknown:{normalized}" if normalized else "unknown:",
            "unknown.fail_closed",
            "unknown",
        )
    canonical, rule_id, relation = rule
    if source_role != "task_target" and action_family not in {"find", "move_to", "mine", "fight", "equip", "craft", "apply"}:
        return CanonicalObjectV4_1_3(
            str(raw or ""), normalized, f"unknown:{normalized}", "unknown.action_family", "unknown"
        )
    return CanonicalObjectV4_1_3(str(raw or ""), normalized, canonical, rule_id, relation)


def _action_parts(action: Any) -> tuple[str, str]:
    if isinstance(action, Action):
        name, args = action.name, action.args
    elif isinstance(action, Mapping):
        name = str(action.get("name") or action.get("type") or "")
        args = action.get("args", action.get("arguments", {}))
    elif isinstance(action, str) and ":" in action:
        name, target = action.split(":", 1)
        return _token(name), target
    else:
        return "", ""
    args = args if isinstance(args, Mapping) else {}
    target = args.get("obj", "")
    if isinstance(target, Mapping):
        target = next(iter(target), "")
    return _token(name), str(target or "")


def controller_target_v4_1_3(action: Any) -> str:
    family, target = _action_parts(action)
    normalized = _token(target)
    if family == "find":
        return {
            "tree": "wood",
            "log": "wood",
            "oak_log": "wood",
            "cobblestone": "stone",
            "diamond": "diamond_ore",
            "redstone": "redstone_ore",
            "gold": "gold_ore",
        }.get(normalized, normalized)
    return normalized


@dataclass(frozen=True)
class ActionSignatureLineageV4_1_3:
    raw_task_target: str
    raw_planner_target: str
    raw_controller_target: str
    raw_scene_target: str
    canonical_object_signature: str
    canonical_action_signature: str
    normalization_rule_ids: tuple[str, ...]


def canonical_action_signature_v4_1_3(
    action: Any,
    *,
    raw_task_target: str = "",
    raw_controller_target: str = "",
    raw_scene_target: str = "",
) -> ActionSignatureLineageV4_1_3:
    family, planner_target = _action_parts(action)
    raw_controller_target = raw_controller_target or controller_target_v4_1_3(action)
    selected_target = raw_controller_target or planner_target or raw_scene_target
    canonical = canonicalize_object_v4_1_3(
        selected_target,
        source_role="controller_target" if raw_controller_target else "planner_target",
        action_family=family,
    )
    signature = f"{family}:{canonical.canonical_signature}" if family else ""
    return ActionSignatureLineageV4_1_3(
        raw_task_target=str(raw_task_target),
        raw_planner_target=planner_target,
        raw_controller_target=str(raw_controller_target),
        raw_scene_target=str(raw_scene_target),
        canonical_object_signature=canonical.canonical_signature,
        canonical_action_signature=signature,
        normalization_rule_ids=(canonical.normalization_rule_id,),
    )


@dataclass(frozen=True)
class ActionSignatureCanonicalizationRegistryV4_1_3(_Hashed):
    source_families: tuple[str, ...] = (
        "formal_50_task_catalog",
        "frozen_task_assets",
        "planner_schema",
        "controller_object_vocabulary",
        "minedojo_identifiers",
        "scene_exemplar_metadata",
    )
    outcome_labels_used: bool = False
    unknown_alias_policy: str = "fail_closed"
    ore_product_conflation_permitted: bool = False
    registry_id: str = ""

    _id_field = "registry_id"

    def __post_init__(self) -> None:
        if self.outcome_labels_used or self.ore_product_conflation_permitted:
            raise ValueError("Signature registry permits outcome leakage or ore/product conflation")
        if self.unknown_alias_policy != "fail_closed":
            raise ValueError("Unknown signature aliases must fail closed")
        if self.registry_id and self.registry_id != self.compute_id():
            raise ValueError("Signature registry hash mismatch")


@dataclass(frozen=True)
class ActionSignatureProvenanceAuditV4_1_3(_Hashed):
    registry_id: str
    audited_tokens: tuple[str, ...]
    required_forbidden_pairs: tuple[tuple[str, str], ...]
    raw_lineage_preserved: bool
    outcome_labels_used: bool
    status: str
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        required = {"tree", "wood", "log", "oak_log", "redstone", "redstone_ore", "iron", "iron_ore", "iron_ingot", "sapling", "cobblestone", "stone", "crafting_table", "wooden_pickaxe"}
        valid = required <= set(self.audited_tokens) and self.raw_lineage_preserved and not self.outcome_labels_used
        if self.status != ("PASS" if valid else "BLOCKED"):
            raise ValueError("Signature provenance conclusion is inconsistent")
        for left, right in self.required_forbidden_pairs:
            left_sig = canonicalize_object_v4_1_3(left, source_role="task_target").canonical_signature
            right_sig = canonicalize_object_v4_1_3(right, source_role="task_target").canonical_signature
            if left_sig == right_sig:
                raise ValueError("A forbidden ore/product mapping was conflated")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Signature provenance audit hash mismatch")


@dataclass(frozen=True)
class SceneCompatibilityNormalizationPolicyV4_1_3(_Hashed):
    registry_id: str
    metadata_matching_only: bool = True
    visual_embedding_changed: bool = False
    scene_rows_changed: bool = False
    top_k_changed: bool = False
    tie_break_changed: bool = False
    gamma_candidate: str = GAMMA_CANDIDATE_B
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    policy_id: str = ""

    _id_field = "policy_id"

    def __post_init__(self) -> None:
        if not self.metadata_matching_only or any((self.visual_embedding_changed, self.scene_rows_changed, self.top_k_changed, self.tie_break_changed)):
            raise ValueError("Signature normalization changed retrieval science")
        if self.gamma_candidate != GAMMA_CANDIDATE_B or self.gamma_text != GAMMA_TEXT:
            raise ValueError("Candidate B or Gamma changed")
        if self.policy_id and self.policy_id != self.compute_id():
            raise ValueError("Scene compatibility policy hash mismatch")


@dataclass(frozen=True)
class SceneSignatureLineageV4_1_3:
    exemplar_id: str
    raw_scene_signature: str
    canonical_scene_signature: str
    normalization_rule_ids: tuple[str, ...]


def canonicalize_bilateral_evidence_v4_1_3(
    evidence: BilateralEvidenceV4_1,
    *,
    action: Any,
    top_k: int = 3,
    minimum_count: int = 1,
    gamma_minus: float = float(GAMMA_TEXT[1]),
    gamma_plus: float = float(GAMMA_TEXT[2]),
) -> BilateralEvidenceV4_1:
    """Repartition frozen scores by canonical metadata without changing scores."""

    query_signature = canonical_action_signature_v4_1_3(action).canonical_action_signature
    all_items = tuple(evidence.compatible_pool) + tuple(evidence.incompatible_pool)
    compatible: list[BilateralMatchV4_1] = []
    incompatible: list[BilateralMatchV4_1] = []
    for item in all_items:
        canonical = canonical_action_signature_v4_1_3(item.action_signature).canonical_action_signature
        normalized = BilateralMatchV4_1(item.exemplar_id, canonical, item.score)
        (compatible if canonical == query_signature else incompatible).append(normalized)
    order = lambda item: (-item.score, item.exemplar_id)
    compatible.sort(key=order)
    incompatible.sort(key=order)
    positive = tuple(compatible[:top_k])
    negative = tuple(incompatible[:top_k])
    contrast = None
    state = "unknown"
    if len(positive) >= minimum_count and len(negative) >= minimum_count:
        contrast = sum(item.score for item in positive) / len(positive) - sum(item.score for item in negative) / len(negative)
        if contrast >= gamma_plus:
            state = "matched"
        elif contrast <= gamma_minus:
            state = "mismatch"
    return BilateralEvidenceV4_1(
        query_observation_id=evidence.query_observation_id,
        query_observation_hash=evidence.query_observation_hash,
        action_signature=query_signature,
        compatible_pool=tuple(compatible),
        incompatible_pool=tuple(incompatible),
        positive=positive,
        negative=negative,
        coverage_positive=min(len(positive), top_k) / top_k,
        coverage_negative=min(len(negative), top_k) / top_k,
        contrast=contrast,
        raw_state=state,
    )


@dataclass(frozen=True)
class PreExecutionRecordV4_1_3:
    record_id: str
    binding: TrackERunBindingV4_1
    decision_index: int
    action: Mapping[str, Any]
    subgoal: str
    signature_lineage: ActionSignatureLineageV4_1_3
    scene_signature_lineage: tuple[SceneSignatureLineageV4_1_3, ...]
    confidence: str
    failure_mode: str
    same_generation_confidence: bool
    planner_call_count: int
    pre_state: StateEvidenceV4_1
    knowledge: KnowledgeFeaturesV4_1
    raw_environment: BilateralEvidenceV4_1
    environment: BilateralEvidenceV4_1
    evaluation_before_action_calls: int = 0
    memory_write_count: int = 0
    acquisition_write_count: int = 0

    def __post_init__(self) -> None:
        if not self.record_id or not self.subgoal:
            raise ValueError("V4.1.3 pre-execution record is incomplete")
        if not self.same_generation_confidence or self.planner_call_count != 1:
            raise ValueError("V4.1.3 requires one-call same-generation confidence")
        if any(
            (
                self.evaluation_before_action_calls,
                self.memory_write_count,
                self.acquisition_write_count,
            )
        ):
            raise ValueError("V4.1.3 pre-execution isolation changed")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrackECollectorV4_1_3:
    """Prospective diagnostic collector with orthogonal action/goal outcomes."""

    supports_dual_level_outcomes = True

    def __init__(
        self,
        *,
        memory: MultimodalMemory,
        binding: TrackERunBindingV4_1,
        rule_registry: CHRMLiteRuleTypeRegistryV4_1,
        retrieval_policy: CHRMLiteBilateralRetrievalPolicyV4_1,
        store: "AtomicDecisionStoreV4_1_3",
        dependency_support_threshold: int,
        gamma_minus: float,
        gamma_plus: float,
    ) -> None:
        if not memory.readonly:
            raise ValueError("Track E V4.1.3 requires read-only Paper Memory V5")
        binding.require_execution_authorized()
        if binding.rule_registry_id != rule_registry.registry_id:
            raise ValueError("Track E V4.1.3 binding/rule registry mismatch")
        if binding.memory_release_id != retrieval_policy.paper_memory_v5_release_id:
            raise ValueError("Track E V4.1.3 binding/Memory release mismatch")
        if binding.scene_release_id != retrieval_policy.scene_exemplar_release_id:
            raise ValueError("Track E V4.1.3 binding/Scene release mismatch")
        if binding.mineclip_policy_id != retrieval_policy.mineclip_policy_id:
            raise ValueError("Track E V4.1.3 binding/MineCLIP policy mismatch")
        if (str(gamma_minus), str(gamma_plus)) != GAMMA_TEXT[1:]:
            raise ValueError("Track E V4.1.3 requires frozen Candidate-B Gamma")
        self.memory = memory
        self.binding = binding
        self.rule_registry = rule_registry
        self.retrieval_policy = retrieval_policy
        self.store = store
        self.dependency_support_threshold = int(dependency_support_threshold)
        self.gamma_minus = float(gamma_minus)
        self.gamma_plus = float(gamma_plus)
        self.errors: list[str] = []
        self._pending: dict[tuple[str, int, str], PreExecutionRecordV4_1_3] = {}
        self.materialized_paths: list[str] = []

    def prepare_attempt(
        self,
        *,
        plan: Plan,
        state: AgentState,
        context: Any,
        episode_id: str,
        attempt: int,
    ) -> bool:
        if episode_id != self.binding.episode_id:
            raise ValueError("Track E V4.1.3 episode ID differs from binding")
        if len(plan.steps) != 1 or len(plan.steps[0].actions) != 1:
            raise ValueError("Track E V4.1.3 executes one original high-level action")
        step = plan.steps[0]
        action = step.actions[0]
        metadata = dict(step.metadata)
        if not metadata.get("v4_1_same_generation") or metadata.get("v4_1_planner_call_count") != 1:
            raise ValueError("Track E V4.1.3 Planner evidence is not one-call")
        if metadata.get("v4_1_prompt_id") != self.binding.planner_prompt_id:
            raise ValueError("Track E V4.1.3 Planner prompt mismatch")
        if metadata.get("v4_1_parser_id") != self.binding.planner_parser_id:
            raise ValueError("Track E V4.1.3 Planner parser mismatch")
        lineage = canonical_action_signature_v4_1_3(
            action,
            raw_task_target=self.binding.task,
        )
        decision_index = int(attempt) - 1
        record_id = deterministic_record_id(
            self.binding,
            decision_index,
            lineage.canonical_action_signature,
        )
        if not self.store.should_execute(record_id):
            return False
        rule_evidence = build_rule_evidence_from_frozen_state(
            action=action,
            state=state,
            memory=self.memory,
            dependency_support_threshold=self.dependency_support_threshold,
        )
        knowledge = extract_knowledge_features_v4_1(
            self.rule_registry,
            action.name,
            rule_evidence,
        )
        image_vector = getattr(context, "image_vector", None)
        if image_vector is None:
            raise ValueError("Track E V4.1.3 requires a pre-action MineCLIP vector")
        raw_environment = bilateral_retrieve_v4_1(
            memory=self.memory,
            state=state,
            image_vector=image_vector,
            action=action,
            policy=self.retrieval_policy,
            gamma_minus=self.gamma_minus,
            gamma_plus=self.gamma_plus,
        )
        environment = canonicalize_bilateral_evidence_v4_1_3(
            raw_environment,
            action=action,
            top_k=self.retrieval_policy.top_k_per_side,
            minimum_count=self.retrieval_policy.minimum_count_per_side,
            gamma_minus=self.gamma_minus,
            gamma_plus=self.gamma_plus,
        )
        raw_items = tuple(raw_environment.compatible_pool) + tuple(raw_environment.incompatible_pool)
        scene_lineage = tuple(
            SceneSignatureLineageV4_1_3(
                item.exemplar_id,
                item.action_signature,
                canonical_action_signature_v4_1_3(item.action_signature).canonical_action_signature,
                canonical_action_signature_v4_1_3(item.action_signature).normalization_rule_ids,
            )
            for item in raw_items
        )
        pre = PreExecutionRecordV4_1_3(
            record_id=record_id,
            binding=self.binding,
            decision_index=decision_index,
            action=action.to_dict(),
            subgoal=str(metadata.get("local_subgoal", "")).strip(),
            signature_lineage=lineage,
            scene_signature_lineage=scene_lineage,
            confidence=str(metadata.get("v4_1_confidence", "")),
            failure_mode=str(metadata.get("v4_1_failure_mode", "")),
            same_generation_confidence=True,
            planner_call_count=1,
            pre_state=_state_evidence_from_agent(state),
            knowledge=knowledge,
            raw_environment=raw_environment,
            environment=environment,
        )
        disposition = self.store.persist_pre(pre)
        if disposition == "completed_do_not_relaunch":
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
        if episode_id != self.binding.episode_id:
            raise ValueError("Track E V4.1.3 finalize episode mismatch")
        if confidence_observations:
            raise ValueError("Track E V4.1.3 forbids a confidence-provider call")
        step = plan.steps[0]
        pre = self._pending.get((plan.plan_id, plan.version, step.step_id))
        if pre is None:
            raise ValueError("Track E V4.1.3 finalization has no persisted pre-record")
        post, controller = _post_state_from_telemetry(
            pre.pre_state,
            execution_telemetry,
        )
        find_evidence = (
            find_evidence_from_telemetry_v4_1_3(step.actions[0], execution_telemetry)
            if step.actions[0].name == "find"
            else None
        )
        action_outcome = action_outcome_v4_1_3(
            action=step.actions[0],
            pre=pre.pre_state,
            post=post,
            controller=controller,
            find_evidence=find_evidence,
        )
        goal_outcome = terminal_goal_outcome_v4_1_3(
            task_completed=task_completed,
            evaluator_called=evaluator_called,
            evaluator_error=evaluator_error,
            terminal_state_hash=post.state_hash,
        )
        controller_evidence_ids = (
            canonical_sha256(
                {
                    "called": controller.called,
                    "success": controller.success,
                    "return_payload": controller.return_payload,
                    "exception_type": controller.exception_type,
                }
            ),
        )
        record = DecisionRecordV4_1_3(
            pre=pre,
            post_state=post,
            controller=controller,
            controller_evidence_ids=controller_evidence_ids,
            action_outcome=action_outcome,
            goal_outcome=goal_outcome,
            engineering_only=True,
            formal_fitting_eligible=False,
        )
        self.materialized_paths.append(str(self.store.join_post(record)))


@dataclass(frozen=True)
class DecisionRecordSchemaV4_1_3(_Hashed):
    controller_layer: tuple[str, ...] = ("status", "evidence_ids")
    action_layer: tuple[str, ...] = ("action_outcome_status", "y_action", "evidence_ids")
    goal_layer: tuple[str, ...] = ("goal_outcome_status", "y_goal", "evaluator_evidence_ids", "terminal_state_hash")
    merged_success_field_permitted: bool = False
    schema_id: str = ""

    _id_field = "schema_id"

    def __post_init__(self) -> None:
        if self.merged_success_field_permitted:
            raise ValueError("Decision schema merged independent evidence layers")
        if self.schema_id and self.schema_id != self.compute_id():
            raise ValueError("Decision schema hash mismatch")


@dataclass(frozen=True)
class DecisionRecordV4_1_3:
    pre: Any
    post_state: StateEvidenceV4_1
    controller: ControllerReceiptV4_1
    controller_evidence_ids: tuple[str, ...]
    action_outcome: ActionTransitionOutcomeV4_1_3
    goal_outcome: TerminalGoalOutcomeV4_1_3
    engineering_only: bool
    formal_fitting_eligible: bool
    record_hash: str = ""

    def __post_init__(self) -> None:
        if self.engineering_only and self.formal_fitting_eligible:
            raise ValueError("Diagnostic records cannot enter formal fitting")
        if self.record_hash and self.record_hash != self.compute_hash():
            raise ValueError("V4.1.3 decision record hash mismatch")

    def payload_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("record_hash", None)
        return payload

    def compute_hash(self) -> str:
        return canonical_sha256(self.payload_without_hash())

    def with_hash(self) -> "DecisionRecordV4_1_3":
        return replace(self, record_hash=self.compute_hash())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.record_hash else self.with_hash()
        return {**item.payload_without_hash(), "record_hash": item.record_hash}


class AtomicDecisionStoreV4_1_3:
    """Atomic four-disposition store keyed only by action-level status."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.paths = {name: self.root / name for name in RECORD_DISPOSITIONS}
        for path in self.paths.values():
            path.mkdir(parents=True, exist_ok=True)

    def _record_paths(self, record_id: str) -> dict[str, Path]:
        if not record_id or any(ch not in "0123456789abcdef" for ch in record_id):
            raise ValueError("record_id must be a lowercase hexadecimal digest")
        return {name: path / f"{record_id}.json" for name, path in self.paths.items()}

    def should_execute(self, record_id: str) -> bool:
        paths = self._record_paths(record_id)
        return not any(
            paths[name].exists()
            for name in RECORD_DISPOSITIONS
            if name != "incomplete_pending"
        )

    @staticmethod
    def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def persist_pre(self, record: Any) -> str:
        paths = self._record_paths(record.record_id)
        finals = [name for name in RECORD_DISPOSITIONS if name != "incomplete_pending" and paths[name].exists()]
        if finals:
            return "completed_do_not_relaunch"
        pending = paths["incomplete_pending"]
        payload = record.to_dict()
        if pending.exists():
            if canonical_json(json.loads(pending.read_text(encoding="utf-8"))) != canonical_json(payload):
                raise ValueError("Pending record ID collision")
            return "pending_resume"
        self._write_exclusive(pending, payload)
        return "created"

    def join_post(self, record: DecisionRecordV4_1_3) -> Path:
        item = record.with_hash()
        paths = self._record_paths(item.pre.record_id)
        disposition = {
            "success": "accepted_scientific",
            "scientific_failure": "accepted_scientific",
            "ambiguous_unobservable": "audit_only_ambiguous",
            "technical_failure": "technical_quarantine",
        }[item.action_outcome.action_outcome_status]
        existing = [name for name in RECORD_DISPOSITIONS if name != "incomplete_pending" and paths[name].exists()]
        if existing and existing != [disposition]:
            raise ValueError("Record ID already finalized in another disposition")
        payload = {**item.to_dict(), "record_disposition": disposition}
        target = paths[disposition]
        if target.exists():
            if canonical_json(json.loads(target.read_text(encoding="utf-8"))) != canonical_json(payload):
                raise ValueError("Final record ID collision")
            paths["incomplete_pending"].unlink(missing_ok=True)
            return target
        if not paths["incomplete_pending"].exists():
            raise ValueError("Post receipt has no persisted pre-record")
        temporary = target.with_suffix(".tmp")
        self._write_exclusive(temporary, payload)
        os.replace(temporary, target)
        paths["incomplete_pending"].unlink()
        return target


@dataclass(frozen=True)
class Round513E5LabelFreeCompatibilityAudit(_Hashed):
    source_closeout_id: str
    signature_policy_id: str
    rows: tuple[Mapping[str, Any], ...]
    outcome_labels_used: bool
    gamma_changed: bool
    conclusion: str
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.outcome_labels_used or self.gamma_changed:
            raise ValueError("Compatibility audit leaked labels or changed Gamma")
        coverage = any(int(row["canonical_compatible_pool_size"]) > 0 for row in self.rows)
        expected = "canonical_compatible_coverage_present" if coverage else "memory_compatible_coverage_still_absent"
        if self.conclusion != expected:
            raise ValueError("Compatibility audit conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Compatibility audit hash mismatch")


@dataclass(frozen=True)
class Round513E5ObservationLabelHardeningAudit(_Hashed):
    observation_closeout_id: str
    outcome_registry_id: str
    find_evidence_contract_id: str
    bounded_failure_policy_id: str
    synthetic_test_count: int
    minedojo_import_test_count: int
    relevant_minedojo_skips: int
    controller_behavior_changed: bool = False
    evaluator_behavior_changed: bool = False
    environment_step_count_changed: bool = False
    historical_records_relabelled: bool = False
    status: str = "PASS"
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        blocked = any(
            (
                self.controller_behavior_changed,
                self.evaluator_behavior_changed,
                self.environment_step_count_changed,
                self.historical_records_relabelled,
                self.relevant_minedojo_skips,
            )
        )
        if self.synthetic_test_count < 1 or self.minedojo_import_test_count < 1:
            blocked = True
        if self.status != ("BLOCKED" if blocked else "PASS"):
            raise ValueError("Observation hardening conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Observation hardening audit hash mismatch")


@dataclass(frozen=True)
class Round513E5SignatureNormalizationAudit(_Hashed):
    signature_registry_id: str
    provenance_audit_id: str
    normalization_policy_id: str
    compatibility_audit_id: str
    visual_score_hash_unchanged: bool
    candidate_b_unchanged: bool
    gamma_unchanged: bool
    outcome_labels_used: bool
    status: str
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        passed = all(
            (
                self.visual_score_hash_unchanged,
                self.candidate_b_unchanged,
                self.gamma_unchanged,
                not self.outcome_labels_used,
            )
        )
        if self.status != ("PASS" if passed else "BLOCKED"):
            raise ValueError("Signature normalization conclusion is inconsistent")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Signature normalization audit hash mismatch")


@dataclass(frozen=True)
class CHRMLiteInstrumentationRuntimeReleaseV4_1_3(_Hashed):
    source_commit: str
    observation_hardening_audit_id: str
    signature_normalization_audit_id: str
    outcome_registry_id: str
    signature_registry_id: str
    decision_record_schema_id: str
    paper_memory_release_id: str
    mineclip_policy_id: str
    scene_exemplar_release_id: str
    controller_contract_id: str
    evaluator_contract_id: str
    technical_retry_policy_id: str
    process_cleanup_policy_id: str
    candidate_b_id: str = GAMMA_CANDIDATE_B
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    memory_readonly: bool = True
    acquisition_writes: int = 0
    evaluation_before_action_calls: int = 0
    hidden_retries: int = 0
    full_9_assignment_rerun_permitted: bool = False
    minedojo_execution_permitted: bool = False
    release_id: str = ""

    _id_field = "release_id"

    def __post_init__(self) -> None:
        if self.candidate_b_id != GAMMA_CANDIDATE_B or self.gamma_text != GAMMA_TEXT:
            raise ValueError("Runtime release changed Candidate B or Gamma")
        if not self.memory_readonly or any(
            (
                self.acquisition_writes,
                self.evaluation_before_action_calls,
                self.hidden_retries,
                self.full_9_assignment_rerun_permitted,
                self.minedojo_execution_permitted,
            )
        ):
            raise ValueError("Runtime release opened an unapproved behavior")
        if self.release_id and self.release_id != self.compute_id():
            raise ValueError("Runtime release hash mismatch")


@dataclass(frozen=True)
class DiagnosticSeedStrategyDecisionInput(_Hashed):
    source_commit: str
    diagnostic_tasks: tuple[str, ...] = ("mine sapling", "mine iron ore", "mine log")
    candidates: tuple[str, ...] = (
        "D1_reuse_corresponding_e4_task_seed_for_bug_regression",
        "D2_new_diagnostic_namespace_and_seed_for_independent_engineering_validation",
    )
    selected_candidate: str = "PENDING_ZYF"
    diagnostic_only: bool = True
    formal_fitting_eligible: bool = False
    channel_calibration_eligible: bool = False
    chrm_fitting_eligible: bool = False
    cdt_identification_eligible: bool = False
    holdout_eligible: bool = False
    final_evaluation_eligible: bool = False
    decision_input_id: str = ""

    _id_field = "decision_input_id"

    def __post_init__(self) -> None:
        if self.selected_candidate != "PENDING_ZYF":
            raise ValueError("Codex cannot choose the diagnostic seed strategy")
        eligibility = (
            self.formal_fitting_eligible,
            self.channel_calibration_eligible,
            self.chrm_fitting_eligible,
            self.cdt_identification_eligible,
            self.holdout_eligible,
            self.final_evaluation_eligible,
        )
        if not self.diagnostic_only or any(eligibility):
            raise ValueError("Diagnostic candidates opened a scientific phase")
        if self.decision_input_id and self.decision_input_id != self.compute_id():
            raise ValueError("Diagnostic decision input hash mismatch")


@dataclass(frozen=True)
class Round513E5DiagnosticAuthorizationInput(_Hashed):
    source_commit: str
    runtime_release_id: str
    outcome_registry_id: str
    signature_registry_id: str
    signature_audit_id: str
    compatibility_audit_id: str
    decision_record_schema_id: str
    diagnostic_seed_decision_input_id: str
    diagnostic_design_id: str
    assignment_seal_id: str = "PENDING_ZYF_SEED_DECISION"
    authorization_status: str = "pending"
    minedojo_execution_permitted: bool = False
    full_9_assignment_rerun_permitted: bool = False
    candidate_b_id: str = GAMMA_CANDIDATE_B
    gamma_text: tuple[str, str, str] = GAMMA_TEXT
    authorization_input_id: str = ""

    _id_field = "authorization_input_id"

    def __post_init__(self) -> None:
        if self.authorization_status != "pending" or self.minedojo_execution_permitted:
            raise ValueError("E5 diagnostic execution was not author-authorized")
        if self.full_9_assignment_rerun_permitted:
            raise ValueError("Full E4 rerun remains closed")
        if self.candidate_b_id != GAMMA_CANDIDATE_B or self.gamma_text != GAMMA_TEXT:
            raise ValueError("Candidate B or Gamma changed")
        if self.authorization_input_id and self.authorization_input_id != self.compute_id():
            raise ValueError("Diagnostic authorization input hash mismatch")


def convert_legacy_label(label: StepLabelV4_1) -> ActionTransitionOutcomeV4_1_3:
    """Compatibility helper for non-find synthetic fixtures, not E4 relabelling."""

    return ActionTransitionOutcomeV4_1_3(
        label.state,
        label.value,
        label.postcondition_id.replace("v4.1:", "v4.1.3:"),
        (canonical_sha256(label.evidence),),
        label.evidence,
    )


def legacy_record_is_unchanged(record: DecisionRecordV4_1) -> bool:
    before = record.to_dict()
    _ = canonical_json(before)
    return before == record.to_dict()
