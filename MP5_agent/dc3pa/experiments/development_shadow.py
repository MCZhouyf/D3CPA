"""Read-only Round 5.11 shadow evidence collection.

The collector observes the plan sent to the Controller and joins the existing
passive confidence observations with existing execution telemetry. It never
selects, edits, rejects, or executes an action.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from ..contracts import AgentState, Plan
from ..memory.multimodal_memory import MultimodalMemory
from ..integration.local_subgoal import resolve_local_subgoal
from ..reliability.confidence_observation import ModelConfidenceObservation
from ..reliability.contracts import ReliabilityContext
from ..reliability.environment_v2 import (
    EnvironmentReliabilityStrategyV2,
    select_environment_action,
)
from ..reliability.knowledge_v2 import KnowledgeReliabilityStrategyV2
from ..reliability.step_labels import join_confidence_with_execution
from .development_records import DevelopmentDecisionRecord


CONFIDENCE_LEVEL_EXPORT = {
    "very_unlikely": "very_low",
    "unlikely": "low",
    "uncertain": "medium",
    "likely": "high",
    "very_likely": "very_high",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _record_id(collection_id: str, run_id: str, decision_index: int) -> str:
    return hashlib.sha256(
        f"{collection_id}\0{run_id}\0{decision_index}".encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class Round511RunBinding:
    collection_id: str
    development_input_release_id: str
    development_protocol_id: str
    role: str
    group_id: str
    task: str
    seed: str
    difficulty: str
    run_id: str
    source_commit: str
    paper_memory_v5_release_id: str
    snapshot_root_sha256: str
    bootstrap_policy_id: str
    prompt_hash_bundle_id: str
    requested_model_name: str = "gpt-5.1"

    def __post_init__(self) -> None:
        if self.role not in {"dev_train", "dev_tune"}:
            raise ValueError("Round 5.11 run role must be dev_train or dev_tune")
        if self.task == "mine sand":
            raise ValueError("Round 5.11 cannot run the superseded mine sand task")
        required = (
            self.collection_id,
            self.development_input_release_id,
            self.development_protocol_id,
            self.group_id,
            self.task,
            self.seed,
            self.difficulty,
            self.run_id,
            self.source_commit,
            self.paper_memory_v5_release_id,
            self.snapshot_root_sha256,
            self.bootstrap_policy_id,
            self.prompt_hash_bundle_id,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Round 5.11 run binding is incomplete")
        if self.requested_model_name != "gpt-5.1":
            raise ValueError("Round 5.11 requested model must be gpt-5.1")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Round511RunBinding":
        return cls(**{name: payload[name] for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class _PendingStep:
    plan: Plan
    step_index: int
    knowledge_hard_feasible: bool
    knowledge_coverage: float
    knowledge_unknown: bool
    knowledge_missing_prerequisites: tuple[str, ...]
    environment_topk_exemplar_ids: tuple[str, ...]
    environment_topk_similarities: tuple[float, ...]
    environment_compatibility: float
    environment_coverage: float
    environment_raw_state: str


@dataclass(frozen=True)
class _LabeledStep:
    pending: _PendingStep
    confidence: ModelConfidenceObservation
    decision_correct: bool


class Round511ShadowCollector:
    """Accumulate decision evidence without affecting Controller execution."""

    def __init__(
        self,
        *,
        memory: MultimodalMemory,
        binding: Round511RunBinding,
        knowledge_strategy: Optional[KnowledgeReliabilityStrategyV2] = None,
        environment_strategy: Optional[EnvironmentReliabilityStrategyV2] = None,
    ) -> None:
        if not memory.readonly:
            raise ValueError("Round 5.11 shadow collection requires read-only memory")
        self.memory = memory
        self.binding = binding
        self.knowledge = knowledge_strategy or KnowledgeReliabilityStrategyV2(
            memory.dependencies
        )
        self.environment = environment_strategy or EnvironmentReliabilityStrategyV2(
            memory,
            top_k=3,
            text_threshold=0.0,
            match_threshold=0.5,
            scope="current_context_only",
            require_text_relevance=True,
            task_name_filter=False,
        )
        self._pending: dict[tuple[str, int, str], _PendingStep] = {}
        self._labeled: list[_LabeledStep] = []
        self.errors: list[str] = []
        self.excluded_step_count = 0

    def _make_record(self, **values: Any) -> DevelopmentDecisionRecord:
        """Construct one record; protected phases may override only its schema."""
        return DevelopmentDecisionRecord(**values).with_hash()

    def prepare_attempt(
        self,
        *,
        plan: Plan,
        state: AgentState,
        context: ReliabilityContext,
        episode_id: str,
        attempt: int,
    ) -> None:
        del episode_id, attempt
        for step_index, step in enumerate(plan.steps):
            knowledge = self.knowledge.evidence(plan, step_index, state, context)
            environment = self.environment.evaluate(plan, step_index, state, context)
            missing = tuple(
                sorted(
                    {
                        item.item
                        for item in (*knowledge.missing_hard, *knowledge.missing_soft)
                    }
                )
            )
            matches = tuple(environment.matches[:3])
            raw_state = (
                environment.status
                if environment.status in {"matched", "mismatch", "unknown"}
                else "unknown"
            )
            key = (plan.plan_id, plan.version, step.step_id)
            self._pending[key] = _PendingStep(
                plan=plan,
                step_index=step_index,
                knowledge_hard_feasible=(
                    bool(knowledge.hard_feasible) if knowledge.available else True
                ),
                knowledge_coverage=(
                    float(knowledge.coverage) if knowledge.coverage is not None else 0.0
                ),
                knowledge_unknown=not knowledge.available,
                knowledge_missing_prerequisites=missing,
                environment_topk_exemplar_ids=tuple(
                    item.exemplar_id for item in matches
                ),
                environment_topk_similarities=tuple(
                    float(item.joint_score) for item in matches
                ),
                environment_compatibility=(
                    float(environment.compatibility)
                    if environment.compatibility is not None
                    else 0.0
                ),
                environment_coverage=float(environment.coverage),
                environment_raw_state=raw_state,
            )

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
        observations = tuple(
            ModelConfidenceObservation.from_mapping(item)
            for item in confidence_observations
        )
        included, excluded = join_confidence_with_execution(
            episode_id=episode_id,
            plan=plan.to_dict(),
            telemetry=execution_telemetry,
            observations=observations,
        )
        self.excluded_step_count += len(excluded)
        by_step = {item.step_id: item for item in observations}
        for label in included:
            key = (plan.plan_id, plan.version, label.step_id)
            pending = self._pending.get(key)
            confidence = by_step.get(label.step_id)
            if pending is None or confidence is None:
                self.errors.append(f"missing shadow evidence for {key}")
                continue
            if confidence.confidence_level not in CONFIDENCE_LEVEL_EXPORT:
                self.errors.append(
                    f"unsupported Confidence level {confidence.confidence_level!r}"
                )
                continue
            self._labeled.append(
                _LabeledStep(
                    pending=pending,
                    confidence=confidence,
                    decision_correct=bool(label.label),
                )
            )

        labelable_step_ids = {
            item.step_id
            for item in included
        } | {
            item.step_id for item in excluded if item.reason != "censored"
        }
        observed_step_ids = {item.step_id for item in observations}
        missing_confidence = sorted(labelable_step_ids - observed_step_ids)
        if missing_confidence:
            self.errors.append(
                "executed steps lack passive Confidence observations: "
                + ",".join(missing_confidence)
            )

    def build_records(
        self,
        *,
        task_completed: bool,
        planner_calls: int,
        reflection_calls: int,
        evaluation_chain_calls: int,
        controller_calls: int,
        bootstrap_event_count: int,
        injected_log_count: int,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int,
        latency_ms: float,
        returned_model_identities: Sequence[str],
        snapshot_root_sha256_after: str,
        formal_memory_write_count: int,
        acquisition_write_count: int,
    ) -> tuple[DevelopmentDecisionRecord, ...]:
        if self.errors:
            raise ValueError("; ".join(self.errors))
        if snapshot_root_sha256_after != self.binding.snapshot_root_sha256:
            raise ValueError("Paper Memory V5 snapshot root changed during collection")
        if formal_memory_write_count or acquisition_write_count:
            raise ValueError("Round 5.11 attempted a memory/acquisition write")
        identities = tuple(
            value for value in (str(item).strip() for item in returned_model_identities)
            if value
        )
        if not identities:
            raise ValueError("Round 5.11 run has no returned provider identity")

        records: list[DevelopmentDecisionRecord] = []
        for decision_index, item in enumerate(self._labeled):
            step = item.pending.plan.steps[item.pending.step_index]
            action = select_environment_action(step)
            proposed_action = _canonical_json(
                action.to_dict() if hasattr(action, "to_dict") else action
            )
            records.append(
                self._make_record(
                    record_id=_record_id(
                        self.binding.collection_id,
                        self.binding.run_id,
                        decision_index,
                    ),
                    collection_id=self.binding.collection_id,
                    development_input_release_id=(
                        self.binding.development_input_release_id
                    ),
                    development_protocol_id=self.binding.development_protocol_id,
                    role=self.binding.role,
                    group_id=self.binding.group_id,
                    task=self.binding.task,
                    seed=self.binding.seed,
                    difficulty=self.binding.difficulty,
                    run_id=self.binding.run_id,
                    decision_index=decision_index,
                    source_commit=self.binding.source_commit,
                    paper_memory_v5_release_id=(
                        self.binding.paper_memory_v5_release_id
                    ),
                    snapshot_root_sha256_before=(
                        self.binding.snapshot_root_sha256
                    ),
                    snapshot_root_sha256_after=snapshot_root_sha256_after,
                    bootstrap_policy_id=self.binding.bootstrap_policy_id,
                    prompt_hash_bundle_id=self.binding.prompt_hash_bundle_id,
                    requested_model_name=self.binding.requested_model_name,
                    returned_model_identities=identities,
                    local_subgoal=resolve_local_subgoal(
                        step, fallback_index=item.pending.step_index
                    ),
                    proposed_action=proposed_action,
                    knowledge_hard_feasible=(
                        item.pending.knowledge_hard_feasible
                    ),
                    knowledge_coverage=item.pending.knowledge_coverage,
                    knowledge_unknown=item.pending.knowledge_unknown,
                    knowledge_missing_prerequisites=(
                        item.pending.knowledge_missing_prerequisites
                    ),
                    confidence_level=CONFIDENCE_LEVEL_EXPORT[
                        item.confidence.confidence_level
                    ],
                    environment_topk_exemplar_ids=(
                        item.pending.environment_topk_exemplar_ids
                    ),
                    environment_topk_similarities=(
                        item.pending.environment_topk_similarities
                    ),
                    environment_compatibility=(
                        item.pending.environment_compatibility
                    ),
                    environment_coverage=item.pending.environment_coverage,
                    environment_raw_state=item.pending.environment_raw_state,
                    decision_correct=item.decision_correct,
                    task_completed=bool(task_completed),
                    planner_calls=int(planner_calls),
                    reflection_calls=int(reflection_calls),
                    evaluation_chain_calls=int(evaluation_chain_calls),
                    controller_calls=int(controller_calls),
                    bootstrap_event_count=int(bootstrap_event_count),
                    injected_log_count=int(injected_log_count),
                    input_tokens=int(input_tokens),
                    output_tokens=int(output_tokens),
                    reasoning_tokens=int(reasoning_tokens),
                    latency_ms=float(latency_ms),
                    formal_memory_write_count=int(formal_memory_write_count),
                    acquisition_write_count=int(acquisition_write_count),
                    holdout_accessed=False,
                    excluded_from_final_evaluation=True,
                )
            )
        if not records:
            raise ValueError("Round 5.11 run produced no labelable decision records")
        return tuple(records)
