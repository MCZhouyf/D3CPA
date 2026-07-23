"""Round 5.13D prospective Track E instrumentation.

This module is deliberately independent from CHRM fitting and CDT triggering.
It records the original action, immutable pre-execution features, and a
deterministic post-execution label.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import numpy as np

from ..contracts import Action, AgentState, Plan, PlanStep, normalize_item_name
from ..memory.exemplar_store import normalized_cosine
from ..memory.multimodal_memory import MultimodalMemory
from ..reliability.environment_v2 import canonical_action_key, exemplar_action_key
from .round513_collection import (
    CONFIDENCE_LEVELS,
    FAILURE_MODES,
    LABEL_STATES,
    CHRMLiteBilateralRetrievalPolicyV4_1,
    CHRMLitePlannerOutputSchemaV4_1,
    CHRMLiteRuleTypeRegistryV4_1,
    PLANNER_OUTPUT_SCHEMA,
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _nonempty(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


class TextCompletionProvider(Protocol):
    def complete(self, prompt: str) -> str:
        ...


class PlannerOutputError(ValueError):
    def __init__(self, reason: str, *, response_hash: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.response_hash = response_hash

    def audit(self) -> dict[str, Any]:
        return {
            "status": "malformed_planner_output",
            "reason": self.reason,
            "response_hash": self.response_hash,
            "retry_performed": False,
        }


@dataclass(frozen=True)
class BehaviorReceiptV4_1:
    planner_calls: int
    subgoal: str
    action: Mapping[str, Any]
    controller_calls: int
    evaluation_before_action_calls: int
    budget_profile_id: str
    outcome: str


def compare_behavior_receipts_v4_1(
    normal: BehaviorReceiptV4_1,
    collection: BehaviorReceiptV4_1,
) -> tuple[bool, tuple[str, ...]]:
    mismatches = tuple(
        field_name
        for field_name in BehaviorReceiptV4_1.__dataclass_fields__
        if getattr(normal, field_name) != getattr(collection, field_name)
    )
    return not mismatches, mismatches


@dataclass(frozen=True)
class PlannerDecisionV4_1:
    subgoal: str
    action: Action
    confidence: str
    failure_mode: str
    prompt_id: str
    parser_id: str
    response_hash: str
    planner_call_index: int

    def __post_init__(self) -> None:
        _nonempty(self.subgoal, "subgoal")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError("Unknown five-level confidence")
        if self.failure_mode not in FAILURE_MODES:
            raise ValueError("Unknown failure_mode")
        if self.planner_call_index != 1:
            raise ValueError("Each V4.1 decision must come from exactly one call")

    def to_plan(self, task: str) -> Plan:
        return Plan(
            task=task,
            steps=[
                PlanStep(
                    actions=[self.action],
                    metadata={
                        "local_subgoal": self.subgoal,
                        "v4_1_confidence": self.confidence,
                        "v4_1_failure_mode": self.failure_mode,
                        "v4_1_prompt_id": self.prompt_id,
                        "v4_1_parser_id": self.parser_id,
                        "v4_1_response_hash": self.response_hash,
                        "v4_1_same_generation": True,
                        "v4_1_planner_call_count": 1,
                    },
                )
            ],
            source="chrmlite_v4_1_one_call",
            metadata={
                "planner_schema": "chrmlite_v4_1",
                "same_generation_confidence": True,
                "planner_call_count": 1,
            },
        )


def parse_planner_output_v4_1(
    raw: str,
    schema: CHRMLitePlannerOutputSchemaV4_1,
) -> PlannerDecisionV4_1:
    response_hash = hashlib.sha256(str(raw).encode("utf-8")).hexdigest()
    try:
        payload = json.loads(str(raw))
    except Exception as exc:
        raise PlannerOutputError("response_is_not_strict_json", response_hash=response_hash) from exc
    if not isinstance(payload, Mapping):
        raise PlannerOutputError("response_is_not_an_object", response_hash=response_hash)
    expected = {"subgoal", "action", "confidence", "failure_mode"}
    if set(payload) != expected:
        raise PlannerOutputError("top_level_fields_do_not_match_schema", response_hash=response_hash)
    action_payload = payload.get("action")
    if not isinstance(action_payload, Mapping) or set(action_payload) != {"name", "arguments"}:
        raise PlannerOutputError("action_fields_do_not_match_schema", response_hash=response_hash)
    arguments = action_payload.get("arguments")
    if not isinstance(arguments, Mapping):
        raise PlannerOutputError("action_arguments_are_not_an_object", response_hash=response_hash)
    confidence = payload.get("confidence")
    if not isinstance(confidence, str) or confidence not in CONFIDENCE_LEVELS:
        raise PlannerOutputError("confidence_is_missing_or_invalid", response_hash=response_hash)
    failure_mode = payload.get("failure_mode")
    if not isinstance(failure_mode, str) or failure_mode not in FAILURE_MODES:
        raise PlannerOutputError("failure_mode_is_missing_or_invalid", response_hash=response_hash)
    try:
        action = Action(name=str(action_payload.get("name", "")), args=dict(arguments))
    except Exception as exc:
        raise PlannerOutputError("action_is_not_controller_compatible", response_hash=response_hash) from exc
    return PlannerDecisionV4_1(
        subgoal=_nonempty(payload.get("subgoal"), "subgoal"),
        action=action,
        confidence=confidence,
        failure_mode=failure_mode,
        prompt_id=schema.prompt_id,
        parser_id=schema.parser_id,
        response_hash=response_hash,
        planner_call_index=1,
    )


class OneCallPlannerV4_1:
    """Generate one original action and confidence in the same model response."""

    def __init__(
        self,
        provider: TextCompletionProvider,
        schema: CHRMLitePlannerOutputSchemaV4_1,
    ) -> None:
        self.provider = provider
        self.schema = schema
        self.call_count = 0
        self.malformed_audits: list[dict[str, Any]] = []

    def plan(
        self,
        task: str,
        state: AgentState,
        context: Mapping[str, Any] | None = None,
    ) -> Plan:
        del context
        prompt = self.schema.prompt_template.format(
            task_json=json.dumps(task, ensure_ascii=False),
            state_json=json.dumps(state.to_dict(), sort_keys=True, ensure_ascii=False, default=str),
            schema_json=json.dumps(PLANNER_OUTPUT_SCHEMA, sort_keys=True, ensure_ascii=False),
        )
        self.call_count += 1
        if self.call_count < 1:
            raise AssertionError("unreachable")
        raw = self.provider.complete(prompt)
        try:
            decision = parse_planner_output_v4_1(raw, self.schema)
        except PlannerOutputError as exc:
            self.malformed_audits.append(exc.audit())
            raise
        return decision.to_plan(task)


@dataclass(frozen=True)
class RuleEvidenceV4_1:
    rule_id: str
    rule_type: str
    satisfied: bool | None
    eligible: bool
    source: str
    evidence_hash: str

    def __post_init__(self) -> None:
        if self.rule_type not in {"hard", "soft", "excluded_ambiguous"}:
            raise ValueError("Invalid rule evidence type")
        if self.rule_type == "excluded_ambiguous" and self.eligible:
            raise ValueError("Ambiguous rules cannot be eligible")
        if self.eligible and self.satisfied is None:
            raise ValueError("Eligible rule requires satisfaction evidence")


@dataclass(frozen=True)
class KnowledgeFeaturesV4_1:
    hard_rule_ids: tuple[str, ...]
    soft_rule_ids: tuple[str, ...]
    excluded_rule_ids: tuple[str, ...]
    evidence: tuple[RuleEvidenceV4_1, ...]
    h: int
    k: float
    u: int

    def __post_init__(self) -> None:
        if set(self.hard_rule_ids) & set(self.soft_rule_ids):
            raise ValueError("Hard rules cannot enter soft coverage")
        if self.h not in {0, 1} or self.u not in {0, 1} or not 0.0 <= self.k <= 1.0:
            raise ValueError("Invalid Knowledge feature")
        if not self.soft_rule_ids and (self.k, self.u) != (0.0, 0):
            raise ValueError("No-soft-rule semantics changed")


def extract_knowledge_features_v4_1(
    registry: CHRMLiteRuleTypeRegistryV4_1,
    action_family: str,
    evidence_by_rule: Mapping[str, tuple[bool | None, bool, Any]],
) -> KnowledgeFeaturesV4_1:
    hard: list[str] = []
    soft: list[str] = []
    excluded: list[str] = []
    evidence: list[RuleEvidenceV4_1] = []
    for rule in registry.rules:
        if action_family not in rule.action_families:
            continue
        satisfied, eligible, raw_evidence = evidence_by_rule.get(
            rule.rule_id, (None, False, {"reason": "not_observed"})
        )
        if rule.rule_type == "excluded_ambiguous":
            eligible = False
            satisfied = None
            excluded.append(rule.rule_id)
        elif not eligible:
            excluded.append(rule.rule_id)
        elif rule.rule_type == "hard":
            hard.append(rule.rule_id)
        else:
            soft.append(rule.rule_id)
        evidence.append(
            RuleEvidenceV4_1(
                rule_id=rule.rule_id,
                rule_type=rule.rule_type,
                satisfied=satisfied,
                eligible=bool(eligible),
                source=rule.source,
                evidence_hash=_sha(raw_evidence),
            )
        )
    h = int(all(item.satisfied is True for item in evidence if item.rule_id in hard))
    if soft:
        k = sum(item.satisfied is True for item in evidence if item.rule_id in soft) / len(soft)
        u = 1
    else:
        k, u = 0.0, 0
    return KnowledgeFeaturesV4_1(
        hard_rule_ids=tuple(hard),
        soft_rule_ids=tuple(soft),
        excluded_rule_ids=tuple(excluded),
        evidence=tuple(evidence),
        h=h,
        k=float(k),
        u=u,
    )


@dataclass(frozen=True)
class BilateralMatchV4_1:
    exemplar_id: str
    action_signature: str
    score: float


@dataclass(frozen=True)
class BilateralEvidenceV4_1:
    query_observation_id: str
    query_observation_hash: str
    action_signature: str
    compatible_pool: tuple[BilateralMatchV4_1, ...]
    incompatible_pool: tuple[BilateralMatchV4_1, ...]
    positive: tuple[BilateralMatchV4_1, ...]
    negative: tuple[BilateralMatchV4_1, ...]
    coverage_positive: float
    coverage_negative: float
    contrast: float | None
    raw_state: str
    online_llm_calls: int = 0

    def __post_init__(self) -> None:
        if self.raw_state not in {"matched", "unknown", "mismatch"}:
            raise ValueError("Invalid bilateral Environment state")
        if len(self.positive) > 3 or len(self.negative) > 3:
            raise ValueError("Bilateral retrieval exceeded top-3")
        if self.online_llm_calls:
            raise ValueError("Environment retrieval must not call an LLM")


def _observation_identity(state: AgentState, image_vector: Any) -> tuple[str, str]:
    payload = {
        "observation_ref": state.observation_ref,
        "task": state.task,
        "inventory": state.normalized_inventory(),
        "position": state.position,
        "metadata": state.metadata,
    }
    if image_vector is not None:
        vector = np.asarray(image_vector, dtype=np.float32).reshape(-1)
        payload["image_vector_sha256"] = hashlib.sha256(vector.tobytes()).hexdigest()
    digest = _sha(payload)
    return str(state.observation_ref or digest), digest


def bilateral_retrieve_v4_1(
    *,
    memory: MultimodalMemory,
    state: AgentState,
    image_vector: Any,
    action: Action,
    policy: CHRMLiteBilateralRetrievalPolicyV4_1,
    gamma_minus: float,
    gamma_plus: float,
) -> BilateralEvidenceV4_1:
    if not memory.readonly:
        raise ValueError("V4.1 retrieval requires read-only Paper Memory V5")
    if not gamma_minus < gamma_plus:
        raise ValueError("gamma_minus must be smaller than gamma_plus")
    query = np.asarray(image_vector, dtype=np.float32).reshape(-1)
    query_id, query_hash = _observation_identity(state, query)
    action_signature = canonical_action_key(action)
    compatible: list[BilateralMatchV4_1] = []
    incompatible: list[BilateralMatchV4_1] = []
    for exemplar in memory.exemplars.all():
        signature, _source = exemplar_action_key(exemplar)
        if not signature or exemplar.image_vector is None:
            continue
        score = normalized_cosine(query, exemplar.image_vector)
        if score is None or not math.isfinite(score):
            continue
        item = BilateralMatchV4_1(exemplar.exemplar_id, signature, float(score))
        if signature == action_signature:
            compatible.append(item)
        else:
            incompatible.append(item)
    key = lambda item: (-item.score, item.exemplar_id)
    compatible.sort(key=key)
    incompatible.sort(key=key)
    positive = tuple(compatible[: policy.top_k_per_side])
    negative = tuple(incompatible[: policy.top_k_per_side])
    cov_pos = min(len(positive), policy.top_k_per_side) / policy.top_k_per_side
    cov_neg = min(len(negative), policy.top_k_per_side) / policy.top_k_per_side
    contrast = None
    raw_state = "unknown"
    if (
        len(positive) >= policy.minimum_count_per_side
        and len(negative) >= policy.minimum_count_per_side
    ):
        contrast = sum(item.score for item in positive) / len(positive) - sum(
            item.score for item in negative
        ) / len(negative)
        if contrast >= gamma_plus:
            raw_state = "matched"
        elif contrast <= gamma_minus:
            raw_state = "mismatch"
    return BilateralEvidenceV4_1(
        query_observation_id=query_id,
        query_observation_hash=query_hash,
        action_signature=action_signature,
        compatible_pool=tuple(compatible),
        incompatible_pool=tuple(incompatible),
        positive=positive,
        negative=negative,
        coverage_positive=float(cov_pos),
        coverage_negative=float(cov_neg),
        contrast=None if contrast is None else float(contrast),
        raw_state=raw_state,
    )


@dataclass(frozen=True)
class StateEvidenceV4_1:
    inventory: Mapping[str, float]
    inventory_observed: bool = True
    held_item: str | None = None
    target_visible: bool | None = None
    target_distance: float | None = None
    target_block_present: bool | None = None
    target_entity_active: bool | None = None
    y_position: float | None = None
    underground: bool | None = None
    object_state: str | None = None
    technical_failure: str = ""

    def normalized_inventory(self) -> dict[str, float]:
        if not self.inventory_observed:
            return {}
        return {
            normalize_item_name(name): float(quantity)
            for name, quantity in self.inventory.items()
            if normalize_item_name(name)
        }

    @property
    def state_hash(self) -> str:
        return _sha(asdict(self))


@dataclass(frozen=True)
class ControllerReceiptV4_1:
    called: bool
    success: bool
    return_payload: Mapping[str, Any]
    elapsed_steps: int
    elapsed_seconds: float
    exception_type: str = ""


@dataclass(frozen=True)
class StepLabelV4_1:
    state: str
    value: int | None
    postcondition_id: str
    evidence: Mapping[str, Any]
    scientific_failure: bool
    technical_failure: bool

    def __post_init__(self) -> None:
        if self.state not in LABEL_STATES:
            raise ValueError("Unknown step label state")
        if self.state == "success" and self.value != 1:
            raise ValueError("Success label must be one")
        if self.state == "scientific_failure" and self.value != 0:
            raise ValueError("Scientific failure label must be zero")
        if self.state in {"technical_failure", "ambiguous_unobservable"} and self.value is not None:
            raise ValueError("Excluded labels cannot have a binary value")


def _target(action: Action) -> str:
    value = action.args.get("obj")
    if isinstance(value, Mapping):
        return normalize_item_name(next(iter(value), ""))
    return normalize_item_name(value)


def join_step_outcome_v4_1(
    *,
    action: Action,
    pre: StateEvidenceV4_1,
    post: StateEvidenceV4_1,
    controller: ControllerReceiptV4_1,
    interaction_distance: float = 3.0,
) -> StepLabelV4_1:
    postcondition_id = f"v4.1:{action.name}:postcondition"
    evidence = {
        "pre_state_hash": pre.state_hash,
        "post_state_hash": post.state_hash,
        "controller_success": controller.success,
        "controller_return_hash": _sha(controller.return_payload),
    }
    if post.technical_failure or controller.exception_type or not controller.called:
        return StepLabelV4_1(
            "technical_failure",
            None,
            postcondition_id,
            {**evidence, "reason": post.technical_failure or controller.exception_type or "controller_not_called"},
            False,
            True,
        )

    name = action.name
    target = _target(action)
    before = pre.normalized_inventory()
    after = post.normalized_inventory()
    observed: bool | None = None
    if name in {"mine", "craft"}:
        if not pre.inventory_observed or not post.inventory_observed:
            observed = None
        else:
            observed = after.get(target, 0.0) > before.get(target, 0.0)
            evidence["inventory_delta"] = after.get(target, 0.0) - before.get(target, 0.0)
        if name == "mine" and post.target_block_present is False:
            observed = True
            evidence["target_block_removed"] = True
    elif name == "equip":
        observed = None if post.held_item is None else normalize_item_name(post.held_item) == target
        evidence["held_item"] = post.held_item
    elif name == "find":
        observed = post.target_visible
        evidence["target_visible"] = post.target_visible
    elif name == "move_to":
        observed = None if post.target_distance is None else post.target_distance <= interaction_distance
        evidence["target_distance"] = post.target_distance
    elif name == "fight":
        observed = None if post.target_entity_active is None else not post.target_entity_active
        evidence["target_entity_active"] = post.target_entity_active
    elif name == "dig_down":
        target_y = float(action.args["y_level"])
        observed = None if post.y_position is None else post.y_position <= target_y
        evidence["target_y"] = target_y
        evidence["post_y"] = post.y_position
    elif name == "dig_up":
        observed = None if pre.y_position is None or post.y_position is None else post.y_position > pre.y_position
        if post.underground is False:
            observed = True
        evidence["pre_y"] = pre.y_position
        evidence["post_y"] = post.y_position
        evidence["post_underground"] = post.underground
    elif name == "apply":
        observed = None if pre.object_state is None or post.object_state is None else post.object_state != pre.object_state
        evidence["pre_object_state"] = pre.object_state
        evidence["post_object_state"] = post.object_state

    if observed is True:
        return StepLabelV4_1("success", 1, postcondition_id, evidence, False, False)
    if observed is False:
        return StepLabelV4_1("scientific_failure", 0, postcondition_id, evidence, True, False)
    return StepLabelV4_1(
        "ambiguous_unobservable",
        None,
        postcondition_id,
        {**evidence, "reason": "required_postcondition_evidence_missing"},
        False,
        False,
    )


@dataclass(frozen=True)
class TrackERunBindingV4_1:
    authorization_id: str
    authorization_status: str
    engineering_smoke_approved: bool
    engineering_only: bool
    campaign_id: str
    source_commit: str
    task: str
    terminal_task: str
    split: str
    group_id: str
    seed_commitment: str
    run_id: str
    episode_id: str
    memory_release_id: str
    dependency_schema_id: str
    rule_registry_id: str
    scene_release_id: str
    mineclip_policy_id: str
    planner_schema_id: str
    planner_prompt_id: str
    planner_parser_id: str
    controller_contract_id: str
    evaluator_contract_id: str
    budget_profile_id: str
    gamma_minus: float
    gamma_plus: float

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"Track E binding field {name} is required")
        if self.split not in {"dev_train", "dev_tune", "engineering_smoke"}:
            raise ValueError("Track E binding has an invalid split")
        if self.engineering_only and self.split != "engineering_smoke":
            raise ValueError("Engineering run must use the engineering_smoke split")
        if not self.gamma_minus < self.gamma_plus:
            raise ValueError("Approved smoke binding requires gamma_minus < gamma_plus")

    def require_execution_authorized(self) -> None:
        if not (
            self.authorization_status == "approved"
            and self.engineering_smoke_approved
            and self.engineering_only
        ):
            raise PermissionError("Engineering smoke is not author-approved")


@dataclass(frozen=True)
class PreExecutionRecordV4_1:
    record_id: str
    binding: TrackERunBindingV4_1
    decision_index: int
    action: Mapping[str, Any]
    subgoal: str
    action_signature: str
    confidence: str
    failure_mode: str
    same_generation_confidence: bool
    planner_call_count: int
    pre_state: StateEvidenceV4_1
    knowledge: KnowledgeFeaturesV4_1
    environment: BilateralEvidenceV4_1
    evaluation_before_action_calls: int = 0
    memory_write_count: int = 0
    acquisition_write_count: int = 0
    holdout_accessed: bool = False
    final_evaluation_accessed: bool = False

    def __post_init__(self) -> None:
        if self.confidence not in CONFIDENCE_LEVELS or self.failure_mode not in FAILURE_MODES:
            raise ValueError("Pre-execution Planner evidence is invalid")
        if not self.same_generation_confidence or self.planner_call_count != 1:
            raise ValueError("Track E requires one-call same-generation confidence")
        if any(
            (
                self.evaluation_before_action_calls,
                self.memory_write_count,
                self.acquisition_write_count,
                self.holdout_accessed,
                self.final_evaluation_accessed,
            )
        ):
            raise ValueError("Track E pre-record violates safety isolation")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionRecordV4_1:
    pre: PreExecutionRecordV4_1
    post_state: StateEvidenceV4_1
    controller: ControllerReceiptV4_1
    label: StepLabelV4_1
    engineering_only: bool
    formal_fitting_eligible: bool
    record_hash: str = ""

    def __post_init__(self) -> None:
        if self.engineering_only and self.formal_fitting_eligible:
            raise ValueError("Engineering smoke cannot enter formal fitting")
        if self.record_hash and self.record_hash != self.compute_hash():
            raise ValueError("Decision record hash mismatch")

    def payload_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("record_hash", None)
        return payload

    def compute_hash(self) -> str:
        return _sha(self.payload_without_hash())

    def with_hash(self) -> "DecisionRecordV4_1":
        return replace(self, record_hash=self.compute_hash())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.record_hash else self.with_hash()
        return {**item.payload_without_hash(), "record_hash": item.record_hash}


class AtomicDecisionStoreV4_1:
    """Two-stage, duplicate-safe materialization for Track E records."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.pending = self.root / "pending"
        self.accepted = self.root / "accepted"
        self.quarantine = self.root / "quarantine"
        for path in (self.pending, self.accepted, self.quarantine):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def paths_for(self, record_id: str) -> tuple[Path, Path, Path]:
        safe = _nonempty(record_id, "record_id")
        if any(character not in "0123456789abcdef" for character in safe):
            raise ValueError("record_id must be a lowercase hexadecimal digest")
        return (
            self.pending / f"{safe}.json",
            self.accepted / f"{safe}.json",
            self.quarantine / f"{safe}.json",
        )

    def should_execute(self, record_id: str) -> bool:
        pending, accepted, quarantine = self.paths_for(record_id)
        return not (accepted.exists() or quarantine.exists())

    def persist_pre(self, record: PreExecutionRecordV4_1) -> str:
        pending, accepted, quarantine = self.paths_for(record.record_id)
        if accepted.exists() or quarantine.exists():
            return "completed_do_not_relaunch"
        payload = record.to_dict()
        if pending.exists():
            existing = json.loads(pending.read_text(encoding="utf-8"))
            if _canonical_bytes(existing) != _canonical_bytes(payload):
                raise ValueError("Pending record ID collision")
            return "pending_resume"
        self._write_exclusive(pending, payload)
        return "created"

    def join_post(self, record: DecisionRecordV4_1) -> Path:
        item = record.with_hash()
        pending, accepted, quarantine = self.paths_for(item.pre.record_id)
        if not pending.exists() and not (accepted.exists() or quarantine.exists()):
            raise ValueError("Post receipt has no persisted pre-record")
        target = (
            accepted
            if item.label.state in {"success", "scientific_failure"}
            and not item.engineering_only
            else quarantine
        )
        other = quarantine if target == accepted else accepted
        if other.exists():
            raise ValueError("Record ID already materialized in another lifecycle state")
        payload = item.to_dict()
        if target.exists():
            existing = json.loads(target.read_text(encoding="utf-8"))
            if _canonical_bytes(existing) != _canonical_bytes(payload):
                raise ValueError("Final record ID collision")
            pending.unlink(missing_ok=True)
            return target
        temporary = target.with_suffix(".tmp")
        self._write_exclusive(temporary, payload)
        os.replace(temporary, target)
        pending.unlink(missing_ok=True)
        return target


def deterministic_record_id(
    binding: TrackERunBindingV4_1,
    decision_index: int,
    action_signature: str,
) -> str:
    return _sha(
        {
            "campaign_id": binding.campaign_id,
            "run_id": binding.run_id,
            "episode_id": binding.episode_id,
            "decision_index": int(decision_index),
            "action_signature": action_signature,
            "source_commit": binding.source_commit,
        }
    )


def _state_evidence_from_agent(state: AgentState) -> StateEvidenceV4_1:
    metadata = dict(state.metadata or {})
    return StateEvidenceV4_1(
        inventory=state.normalized_inventory(),
        held_item=metadata.get("held_item"),
        target_visible=metadata.get("target_visible"),
        target_distance=metadata.get("target_distance"),
        target_block_present=metadata.get("target_block_present"),
        target_entity_active=metadata.get("target_entity_active"),
        y_position=metadata.get("y_position"),
        underground=metadata.get("underground"),
        object_state=metadata.get("object_state"),
        technical_failure=str(metadata.get("technical_failure", "")),
    )


def _action_target(action: Action) -> str:
    value = action.args.get("obj")
    if isinstance(value, Mapping):
        return normalize_item_name(next(iter(value), ""))
    return normalize_item_name(value)


def build_rule_evidence_from_frozen_state(
    *,
    action: Action,
    state: AgentState,
    memory: MultimodalMemory,
    dependency_support_threshold: int,
) -> dict[str, tuple[bool | None, bool, Any]]:
    inventory = state.normalized_inventory()
    evidence: dict[str, tuple[bool | None, bool, Any]] = {
        "mechanics.action_schema": (True, True, action.to_dict()),
    }
    tool = normalize_item_name(action.args.get("tool"))
    mechanics_requires_tool = action.name == "mine" and _action_target(action) in {
        "cobblestone",
        "coal ore",
        "coal",
        "iron ore",
        "diamond",
        "redstone",
        "gold ore",
        "gold",
    }
    tool_eligible = action.name in {"mine", "fight", "dig_down", "dig_up", "apply"} and bool(
        tool or mechanics_requires_tool
    )
    evidence["controller.required_tool"] = (
        bool(tool and inventory.get(tool, 0.0) >= 1.0) if tool_eligible else None,
        tool_eligible,
        {"tool": tool, "quantity": inventory.get(tool, 0.0)},
    )
    if action.name == "equip":
        item = _action_target(action)
        evidence["controller.equip_inventory"] = (
            inventory.get(item, 0.0) >= 1.0,
            True,
            {"item": item, "quantity": inventory.get(item, 0.0)},
        )
    if action.name == "craft":
        materials = {
            normalize_item_name(name): float(quantity)
            for name, quantity in dict(action.args.get("materials", {})).items()
        }
        material_satisfaction = all(
            inventory.get(name, 0.0) >= quantity for name, quantity in materials.items()
        )
        evidence["controller.craft_material_quantity"] = (
            material_satisfaction,
            True,
            {"required": materials, "inventory": inventory},
        )
        platform = normalize_item_name(action.args.get("platform"))
        nearby = {
            normalize_item_name(name)
            for name in state.metadata.get("nearby_platforms", ())
        }
        evidence["controller.craft_platform_access"] = (
            bool(inventory.get(platform, 0.0) >= 1.0 or platform in nearby),
            bool(platform),
            {"platform": platform, "nearby": sorted(nearby)},
        )

    target = _action_target(action)
    hard_prerequisites = {
        tool,
        *(
            normalize_item_name(name)
            for name in dict(action.args.get("materials", {}))
        ),
        normalize_item_name(action.args.get("platform")),
    }
    eligible_edges = [
        edge
        for edge in memory.dependencies.prerequisites_for(target)
        if edge.success_count >= dependency_support_threshold
        and normalize_item_name(edge.prerequisite) not in hard_prerequisites
    ]
    if eligible_edges:
        satisfied = all(
            inventory.get(normalize_item_name(edge.prerequisite), 0.0) >= edge.quantity
            for edge in eligible_edges
        )
        evidence["memory.verified_dependency"] = (
            satisfied,
            True,
            [edge.to_dict() for edge in eligible_edges],
        )
    target_visible = state.metadata.get("target_visible")
    if target_visible is not None:
        evidence["environment.target_visibility"] = (
            bool(target_visible),
            True,
            {"target": target, "visible": bool(target_visible)},
        )
    return evidence


def _event_value(event: Any, name: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(name, default)
    return getattr(event, name, default)


def _event_payload(event: Any) -> Mapping[str, Any]:
    value = _event_value(event, "payload", {})
    return value if isinstance(value, Mapping) else {}


def _post_state_from_telemetry(
    pre: StateEvidenceV4_1,
    telemetry: Sequence[Any],
) -> tuple[StateEvidenceV4_1, ControllerReceiptV4_1]:
    finished = [
        event
        for event in telemetry
        if str(_event_value(event, "event_type", "")) == "action_finished"
    ]
    if not finished:
        return (
            replace(pre, technical_failure="missing_action_finished_telemetry"),
            ControllerReceiptV4_1(
                called=False,
                success=False,
                return_payload={},
                elapsed_steps=0,
                elapsed_seconds=0.0,
                exception_type="missing_action_finished_telemetry",
            ),
        )
    event = finished[-1]
    payload = _event_payload(event)
    result = payload.get("result", {})
    result = result if isinstance(result, Mapping) else {"raw": result}
    structured = result.get("post_state_evidence", {})
    structured = structured if isinstance(structured, Mapping) else {}
    inventory = payload.get("inventory", pre.inventory)
    inventory = inventory if isinstance(inventory, Mapping) else pre.inventory
    status = str(_event_value(event, "status", ""))
    post = StateEvidenceV4_1(
        inventory=dict(inventory),
        held_item=structured.get("held_item", pre.held_item),
        target_visible=structured.get("target_visible"),
        target_distance=structured.get("target_distance"),
        target_block_present=structured.get("target_block_present"),
        target_entity_active=structured.get("target_entity_active"),
        y_position=structured.get("y_position"),
        underground=structured.get("underground"),
        object_state=structured.get("object_state"),
        technical_failure=str(structured.get("technical_failure", "")),
    )
    return (
        post,
        ControllerReceiptV4_1(
            called=True,
            success=status in {"success", "skipped_satisfied"},
            return_payload=dict(result),
            elapsed_steps=int(structured.get("elapsed_steps", 0) or 0),
            elapsed_seconds=float(structured.get("elapsed_seconds", 0.0) or 0.0),
            exception_type=str(structured.get("exception_type", "")),
        ),
    )


class TrackECollectorV4_1:
    """Fail-closed observer used by the dedicated Stage6 collection mode."""

    def __init__(
        self,
        *,
        memory: MultimodalMemory,
        binding: TrackERunBindingV4_1,
        rule_registry: CHRMLiteRuleTypeRegistryV4_1,
        retrieval_policy: CHRMLiteBilateralRetrievalPolicyV4_1,
        store: AtomicDecisionStoreV4_1,
        dependency_support_threshold: int,
        gamma_minus: float,
        gamma_plus: float,
    ) -> None:
        if not memory.readonly:
            raise ValueError("Track E requires read-only Paper Memory V5")
        binding.require_execution_authorized()
        if binding.rule_registry_id != rule_registry.registry_id:
            raise ValueError("Track E binding/rule registry mismatch")
        if binding.dependency_schema_id != rule_registry.dependency_schema_id:
            raise ValueError("Track E binding/Dependency Schema mismatch")
        if binding.memory_release_id != retrieval_policy.paper_memory_v5_release_id:
            raise ValueError("Track E binding/Memory release mismatch")
        if binding.scene_release_id != retrieval_policy.scene_exemplar_release_id:
            raise ValueError("Track E binding/Scene release mismatch")
        if binding.mineclip_policy_id != retrieval_policy.mineclip_policy_id:
            raise ValueError("Track E binding/MineCLIP policy mismatch")
        self.memory = memory
        self.binding = binding
        self.rule_registry = rule_registry
        self.retrieval_policy = retrieval_policy
        self.store = store
        self.dependency_support_threshold = int(dependency_support_threshold)
        self.gamma_minus = float(gamma_minus)
        self.gamma_plus = float(gamma_plus)
        self.errors: list[str] = []
        self._pending: dict[tuple[str, int, str], PreExecutionRecordV4_1] = {}
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
            raise ValueError("Track E episode ID differs from frozen binding")
        if len(plan.steps) != 1 or len(plan.steps[0].actions) != 1:
            raise ValueError("Track E executes exactly one original high-level action")
        step = plan.steps[0]
        action = step.actions[0]
        metadata = dict(step.metadata)
        if not metadata.get("v4_1_same_generation") or metadata.get("v4_1_planner_call_count") != 1:
            raise ValueError("Track E Planner evidence is not same-generation one-call")
        if metadata.get("v4_1_prompt_id") != self.binding.planner_prompt_id:
            raise ValueError("Track E Planner prompt identity mismatch")
        if metadata.get("v4_1_parser_id") != self.binding.planner_parser_id:
            raise ValueError("Track E Planner parser identity mismatch")
        decision_index = int(attempt) - 1
        signature = canonical_action_key(action)
        record_id = deterministic_record_id(self.binding, decision_index, signature)
        if not self.store.should_execute(record_id):
            return False
        evidence_by_rule = build_rule_evidence_from_frozen_state(
            action=action,
            state=state,
            memory=self.memory,
            dependency_support_threshold=self.dependency_support_threshold,
        )
        knowledge = extract_knowledge_features_v4_1(
            self.rule_registry, action.name, evidence_by_rule
        )
        image_vector = getattr(context, "image_vector", None)
        if image_vector is None:
            raise ValueError("Track E requires a pre-execution MineCLIP image vector")
        environment = bilateral_retrieve_v4_1(
            memory=self.memory,
            state=state,
            image_vector=image_vector,
            action=action,
            policy=self.retrieval_policy,
            gamma_minus=self.gamma_minus,
            gamma_plus=self.gamma_plus,
        )
        pre = PreExecutionRecordV4_1(
            record_id=record_id,
            binding=self.binding,
            decision_index=decision_index,
            action=action.to_dict(),
            subgoal=_nonempty(metadata.get("local_subgoal"), "local_subgoal"),
            action_signature=signature,
            confidence=str(metadata.get("v4_1_confidence", "")),
            failure_mode=str(metadata.get("v4_1_failure_mode", "")),
            same_generation_confidence=True,
            planner_call_count=1,
            pre_state=_state_evidence_from_agent(state),
            knowledge=knowledge,
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
    ) -> None:
        del task_completed, attempt
        if episode_id != self.binding.episode_id:
            raise ValueError("Track E finalize episode mismatch")
        if confidence_observations:
            raise ValueError("Track E forbids a separate confidence provider call")
        step = plan.steps[0]
        key = (plan.plan_id, plan.version, step.step_id)
        pre = self._pending.get(key)
        if pre is None:
            raise ValueError("Track E finalization has no persisted pre-record")
        post, controller = _post_state_from_telemetry(pre.pre_state, execution_telemetry)
        label = join_step_outcome_v4_1(
            action=step.actions[0],
            pre=pre.pre_state,
            post=post,
            controller=controller,
        )
        record = DecisionRecordV4_1(
            pre=pre,
            post_state=post,
            controller=controller,
            label=label,
            engineering_only=self.binding.engineering_only,
            formal_fitting_eligible=False,
        )
        self.materialized_paths.append(str(self.store.join_post(record)))
