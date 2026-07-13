from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence

from ..contracts import AgentState, Plan
from ..evaluation import (
    EvaluationReport,
    EvaluationRequest,
    PatchApplication,
    PlanEditor,
    PlanEvaluationChain,
)
from ..evaluation.material_repair import MaterialRepairResult, repair_material_deficits
from ..observability.trace import JsonlTraceWriter
from ..reliability import (
    AdaptiveTriggerConfig,
    DualChainConfig,
    ReliabilityContext,
    ReliabilityResult,
)
from .constraint_repair_policy import should_attempt_deterministic_repair
from ..trigger import (
    AdaptiveTriggerSession,
    FixedIntervalTriggerSession,
    TriggerObservation,
)
from .interfaces import ReasoningChain


class ReliabilityModel(Protocol):
    def score_window(
        self,
        plan: Plan,
        step_indices: Sequence[int],
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
        successful_memory_count: Optional[int] = None,
    ) -> list[ReliabilityResult]:
        ...


class TriggerSession(Protocol):
    def next_window(self):
        ...

    def observe(
        self, probabilities: Sequence[Optional[float]], hard_conflict: bool = False
    ) -> TriggerObservation:
        ...

    def restart_after_revision(self, start_index: int, total_steps: int) -> None:
        ...


@dataclass(frozen=True)
class PlanningOutcome:
    initial_plan: Plan
    final_plan: Plan
    reliability_results: tuple[ReliabilityResult, ...]
    trigger_observations: tuple[TriggerObservation, ...]
    evaluation_reports: tuple[EvaluationReport, ...]
    patch_applications: tuple[PatchApplication, ...]
    unresolved: tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def revision_count(self) -> int:
        return len(self.patch_applications)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_plan": self.initial_plan.to_dict(),
            "final_plan": self.final_plan.to_dict(),
            "reliability_results": [item.to_dict() for item in self.reliability_results],
            "trigger_observations": [item.to_dict() for item in self.trigger_observations],
            "evaluation_reports": [item.to_dict() for item in self.evaluation_reports],
            "patch_applications": [
                {
                    "original_plan_id": item.original_plan.plan_id,
                    "revised_plan_id": item.revised_plan.plan_id,
                    "earliest_changed_index": item.earliest_changed_index,
                    "changed_step_ids": list(item.changed_step_ids),
                    "applied_edit_ids": list(item.applied_edit_ids),
                }
                for item in self.patch_applications
            ],
            "unresolved": list(self.unresolved),
            "revision_count": self.revision_count,
        }


class CognitiveControlPlanner:
    """Shared Stage-4/5 planner loop parameterized by a trigger session."""

    def __init__(
        self,
        reasoning_chain: ReasoningChain,
        reliability_model: ReliabilityModel,
        evaluation_chain: PlanEvaluationChain,
        session_factory: Callable[[int], TriggerSession],
        config: DualChainConfig,
        plan_editor: Optional[PlanEditor] = None,
        trace_writer: Optional[JsonlTraceWriter] = None,
    ):
        config.validate()
        self.reasoning_chain = reasoning_chain
        self.reliability_model = reliability_model
        self.evaluation_chain = evaluation_chain
        self.session_factory = session_factory
        self.config = config
        self.plan_editor = plan_editor or PlanEditor()
        self.trace_writer = trace_writer
        self.last_outcome: Optional[PlanningOutcome] = None

    def _trace(self, event_type: str, payload: Mapping[str, Any]) -> None:
        if self.trace_writer is not None:
            self.trace_writer.write(event_type, payload)

    def _repair_material_deficits(
        self,
        plan: Plan,
        state: AgentState,
        *,
        phase: str,
        hard_conflict: bool,
        preserve_revision: bool = False,
    ) -> tuple[Plan, Optional[MaterialRepairResult]]:
        repair = repair_material_deficits(plan, state)
        if repair.inserted_step_count <= 0:
            return plan, None
        repaired_plan = repair.plan
        if preserve_revision:
            repaired_plan = Plan(
                task=plan.task,
                steps=repair.plan.steps,
                plan_id=plan.plan_id,
                version=plan.version,
                source=plan.source,
                parent_plan_id=plan.parent_plan_id,
                metadata={
                    **dict(plan.metadata),
                    "material_repair_inserted_targets": repair.inserted_targets,
                },
            )
            repair = MaterialRepairResult(
                plan=repaired_plan,
                inserted_step_count=repair.inserted_step_count,
                inserted_targets=repair.inserted_targets,
            )
        self._trace(
            "material_deficits_repaired",
            {
                "original_plan_id": plan.plan_id,
                "original_plan_version": plan.version,
                "repaired_plan_id": repair.plan.plan_id,
                "repaired_plan_version": repair.plan.version,
                "inserted_step_count": repair.inserted_step_count,
                "inserted_targets": list(repair.inserted_targets),
                "constraint_repair_policy": self.config.constraint_repair_policy,
                "repair_phase": phase,
                "deterministic_repair_attempted": True,
                "hard_conflict": bool(hard_conflict),
            },
        )
        return repaired_plan, repair

    def create_plan(
        self,
        task: str,
        state: AgentState,
        context: Optional[Mapping[str, Any] | ReliabilityContext] = None,
    ) -> Plan:
        return self.plan_with_outcome(task, state, context).final_plan

    def plan_with_outcome(
        self,
        task: str,
        state: AgentState,
        context: Optional[Mapping[str, Any] | ReliabilityContext] = None,
    ) -> PlanningOutcome:
        if state.task and state.task != task:
            raise ValueError(
                f"AgentState.task {state.task!r} does not match requested task {task!r}"
            )
        if isinstance(context, ReliabilityContext):
            reliability_context = context
            # Reserved fields win over metadata to prevent accidental or malicious
            # shadowing of the actual visual/task context.
            reasoning_context: Mapping[str, Any] = {
                **dict(context.metadata),
                "task_context": context.task_context,
                "image": context.image,
                "image_vector": context.image_vector,
            }
        else:
            reasoning_context = dict(context or {})
            reliability_context = ReliabilityContext(
                task_context=str(reasoning_context.get("task_context", "")),
                image=reasoning_context.get("image"),
                image_vector=reasoning_context.get("image_vector"),
                metadata={
                    key: value
                    for key, value in reasoning_context.items()
                    if key not in {"image", "image_vector", "task_context"}
                },
            )
        initial = self.reasoning_chain.plan(
            task=task, state=state, context=reasoning_context
        )
        if initial.task != task:
            raise ValueError(
                f"Reasoning chain returned plan task {initial.task!r} for {task!r}"
            )
        plan = initial
        session = self.session_factory(len(plan.steps))
        reliability_history: List[ReliabilityResult] = []
        trigger_history: List[TriggerObservation] = []
        report_history: List[EvaluationReport] = []
        patch_history: List[PatchApplication] = []
        material_repairs: List[MaterialRepairResult] = []
        unresolved: List[Dict[str, Any]] = []
        current_plan_had_hard_unresolved = False

        self._trace("reasoning_plan_created", {"plan": plan.to_dict()})
        while True:
            window = session.next_window()
            if window is None:
                break
            results = self.reliability_model.score_window(
                plan=plan,
                step_indices=window.step_indices,
                state=state,
                context=reliability_context,
            )
            if len(results) != len(window.step_indices):
                raise ValueError(
                    "Reliability model returned a result count that does not match "
                    "the requested window"
                )
            for expected_index, result in zip(window.step_indices, results):
                expected_step = plan.steps[expected_index]
                if (
                    result.plan_id != plan.plan_id
                    or result.plan_version != plan.version
                    or result.step_index != expected_index
                    or result.step_id != expected_step.step_id
                ):
                    raise ValueError(
                        "Reliability model returned stale or misaligned step evidence"
                    )
            reliability_history.extend(results)
            hard_conflict = any(result.hard_conflict for result in results)
            probabilities = [result.probability for result in results]
            observation = session.observe(
                probabilities=probabilities,
                hard_conflict=hard_conflict,
            )
            trigger_history.append(observation)
            self._trace(
                "reliability_window_evaluated",
                {
                    "plan_id": plan.plan_id,
                    "plan_version": plan.version,
                    "window": window.to_dict(),
                    "results": [result.to_dict() for result in results],
                    "trigger": observation.to_dict(),
                },
            )

            numeric_low = (
                observation.monitored_confidence is not None
                and observation.monitored_confidence < self.config.confidence_threshold
            )
            should_evaluate = (
                hard_conflict
                or numeric_low
                or (
                    self.config.evaluate_when_unavailable
                    and observation.had_unavailable
                )
            )
            if not should_evaluate:
                continue
            if len(patch_history) >= self.config.max_revision_rounds:
                unresolved.append(
                    {
                        "plan_id": plan.plan_id,
                        "window": window.to_dict(),
                        "reason": "max_revision_rounds_reached",
                        "hard_conflict": hard_conflict,
                    }
                )
                current_plan_had_hard_unresolved = current_plan_had_hard_unresolved or hard_conflict
                self._trace("evaluation_skipped", unresolved[-1])
                continue

            request = EvaluationRequest(
                plan=plan,
                state=state,
                step_indices=window.step_indices,
                reliability=tuple(results),
                context=reliability_context,
            )
            report = self.evaluation_chain.evaluate(request)
            report_history.append(report)
            self._trace("evaluation_report", report.to_dict())
            if report.accepted:
                if hard_conflict:
                    unresolved.append(
                        {
                            "plan_id": plan.plan_id,
                            "window": window.to_dict(),
                            "reason": "accepted_despite_hard_conflict",
                            "summary": report.summary,
                            "hard_conflict": True,
                        }
                    )
                    current_plan_had_hard_unresolved = True
                    self._trace("evaluation_conflict_unresolved", unresolved[-1])
                else:
                    self._trace(
                        "evaluation_accepted",
                        {
                            "plan_id": plan.plan_id,
                            "plan_version": plan.version,
                            "window": window.to_dict(),
                            "summary": report.summary,
                        },
                    )
                continue
            if report.request_replan:
                repair_allowed = should_attempt_deterministic_repair(
                    self.config.constraint_repair_policy,
                    phase="request_replan",
                    hard_conflict=hard_conflict,
                )
                if repair_allowed:
                    repaired_plan, material_repair = self._repair_material_deficits(
                        plan,
                        state,
                        phase="request_replan",
                        hard_conflict=hard_conflict,
                    )
                    if material_repair is not None:
                        material_repairs.append(material_repair)
                        plan = repaired_plan
                        current_plan_had_hard_unresolved = False
                        restart_index = min(window.start_index, len(plan.steps) - 1)
                        self._trace(
                            "plan_revised",
                            {
                                "report": report.to_dict(),
                                "revised_plan": plan.to_dict(),
                                "restart_index": restart_index,
                                "repair_source": "local_material_repair",
                            },
                        )
                        session.restart_after_revision(restart_index, len(plan.steps))
                        continue
                else:
                    self._trace(
                        "material_deficits_repair_skipped",
                        {
                            "plan_id": plan.plan_id,
                            "plan_version": plan.version,
                            "constraint_repair_policy": self.config.constraint_repair_policy,
                            "repair_phase": "request_replan",
                            "deterministic_repair_attempted": False,
                            "hard_conflict": hard_conflict,
                        },
                    )
                unresolved.append(
                    {
                        "plan_id": plan.plan_id,
                        "window": window.to_dict(),
                        "reason": "request_replan",
                        "summary": report.summary,
                        "hard_conflict": hard_conflict,
                    }
                )
                current_plan_had_hard_unresolved = current_plan_had_hard_unresolved or hard_conflict
                continue

            application = self.plan_editor.apply(plan, report)
            patch_history.append(application)
            plan = application.revised_plan
            repair_allowed = should_attempt_deterministic_repair(
                self.config.constraint_repair_policy,
                phase="post_patch",
                hard_conflict=hard_conflict,
            )
            if repair_allowed:
                plan, material_repair = self._repair_material_deficits(
                    plan,
                    state,
                    phase="post_patch",
                    hard_conflict=hard_conflict,
                    preserve_revision=True,
                )
                if material_repair is not None:
                    material_repairs.append(material_repair)
            else:
                self._trace(
                    "material_deficits_repair_skipped",
                    {
                        "plan_id": plan.plan_id,
                        "plan_version": plan.version,
                        "constraint_repair_policy": self.config.constraint_repair_policy,
                        "repair_phase": "post_patch",
                        "deterministic_repair_attempted": False,
                        "hard_conflict": hard_conflict,
                    },
                )
            current_plan_had_hard_unresolved = False
            restart_index = min(
                application.earliest_changed_index,
                len(plan.steps) - 1,
            )
            self._trace(
                "plan_revised",
                {
                    "report": report.to_dict(),
                    "revised_plan": plan.to_dict(),
                    "restart_index": restart_index,
                },
            )
            session.restart_after_revision(restart_index, len(plan.steps))

        if not current_plan_had_hard_unresolved:
            unresolved = [
                item
                for item in unresolved
                if item.get("hard_conflict") or item.get("plan_id") == plan.plan_id
            ]
        outcome = PlanningOutcome(
            initial_plan=initial,
            final_plan=plan,
            reliability_results=tuple(reliability_history),
            trigger_observations=tuple(trigger_history),
            evaluation_reports=tuple(report_history),
            patch_applications=tuple(patch_history),
            unresolved=tuple(unresolved),
        )
        self.last_outcome = outcome
        self._trace("cognitive_control_complete", outcome.to_dict())
        return outcome


class HighFrequencyDualChainPlanner(CognitiveControlPlanner):
    """Stage 4: fixed high-frequency evaluation with M=1."""

    def __init__(
        self,
        reasoning_chain: ReasoningChain,
        reliability_model: ReliabilityModel,
        evaluation_chain: PlanEvaluationChain,
        config: DualChainConfig = DualChainConfig(),
        plan_editor: Optional[PlanEditor] = None,
        trace_writer: Optional[JsonlTraceWriter] = None,
    ):
        config.validate()
        super().__init__(
            reasoning_chain=reasoning_chain,
            reliability_model=reliability_model,
            evaluation_chain=evaluation_chain,
            session_factory=lambda total: FixedIntervalTriggerSession(
                total_steps=total,
                interval=1,
                threshold=config.confidence_threshold,
            ),
            config=config,
            plan_editor=plan_editor,
            trace_writer=trace_writer,
        )


class AdaptiveCognitiveControlPlanner(CognitiveControlPlanner):
    """Stage 5: variable evaluation cadence controlled by recent reliability."""

    def __init__(
        self,
        reasoning_chain: ReasoningChain,
        reliability_model: ReliabilityModel,
        evaluation_chain: PlanEvaluationChain,
        trigger_config: AdaptiveTriggerConfig = AdaptiveTriggerConfig(),
        dual_chain_config: Optional[DualChainConfig] = None,
        plan_editor: Optional[PlanEditor] = None,
        trace_writer: Optional[JsonlTraceWriter] = None,
    ):
        trigger_config.validate()
        if dual_chain_config is None:
            dual_chain_config = DualChainConfig(
                confidence_threshold=trigger_config.threshold
            )
        dual_chain_config.validate()
        if dual_chain_config.confidence_threshold != trigger_config.threshold:
            raise ValueError(
                "Dual-chain and adaptive-trigger thresholds must match to avoid "
                "ambiguous evaluation decisions"
            )
        super().__init__(
            reasoning_chain=reasoning_chain,
            reliability_model=reliability_model,
            evaluation_chain=evaluation_chain,
            session_factory=lambda total: AdaptiveTriggerSession(
                total_steps=total,
                config=trigger_config,
            ),
            config=dual_chain_config,
            plan_editor=plan_editor,
            trace_writer=trace_writer,
        )
