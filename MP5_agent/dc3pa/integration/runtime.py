from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Tuple, runtime_checkable

from ..contracts import AgentState, Plan
from ..integration.controller import ControllerAdapter, ExecutionResult
from ..memory.acquisition import AcquisitionStore
from ..memory.calibration_store import CalibrationEpisodeStore
from ..memory.modes import MemoryMode
from ..memory.multimodal_memory import SceneObservation, SuccessfulEpisode
from ..memory.snapshot import MemorySnapshotManifest, SnapshotGuard
from ..observability.trace import JsonlTraceWriter
from ..reliability import DimensionScore, ReliabilityContext
from ..reliability.confidence_observation import ConfidenceObservationCollector
from .events import AttemptRecord, RuntimeEvent, TaskRunResult, sanitize_for_trace
from .round11_persistence import (
    commit_calibration_episode,
    commit_successful_acquisition,
    new_episode_id,
)
from .stage6_config import Stage6RuntimeConfig
from .state import StateProvider, StateSnapshot, task_name_from_information


@runtime_checkable
class PlanSource(Protocol):
    def plan(
        self, task: str, state: AgentState, context: Optional[Mapping[str, Any]] = None
    ) -> Plan:
        ...


@runtime_checkable
class CognitivePlanner(Protocol):
    def plan_with_outcome(
        self,
        task: str,
        state: AgentState,
        context: Optional[Mapping[str, Any] | ReliabilityContext] = None,
    ) -> Any:
        ...


@runtime_checkable
class GoalChecker(Protocol):
    def is_done(self, task_information: Mapping[str, Any]) -> bool:
        ...


@runtime_checkable
class ReflexionProvider(Protocol):
    def reflect(
        self,
        *,
        task_information: Mapping[str, Any],
        previous_workflow: Mapping[str, Any],
        check_result: Mapping[str, Any],
        underground: bool = False,
    ) -> str:
        ...


@runtime_checkable
class LegacyMemorySink(Protocol):
    def record_success(
        self, task_information: Mapping[str, Any], plan: Plan
    ) -> Any:
        ...


@runtime_checkable
class MultimodalMemorySink(Protocol):
    def record_success(self, episode: SuccessfulEpisode) -> Any:
        ...


@runtime_checkable
class PassiveConfidenceScorer(Protocol):
    def score(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> DimensionScore:
        ...


@dataclass(frozen=True)
class _PlanningDecision:
    plan: Optional[Plan]
    outcome: Any = None
    fallback_used: bool = False
    blocked_reason: str = ""
    unsafe_unresolved_execution: bool = False


class Stage6ClosedLoopRunner:
    """Execute the Stage-6 closed loop while preserving legacy Controller semantics.

    The Controller receives a complete, finalized high-level plan. Stage 6 deliberately
    does not split it into individual actions because the legacy Controller contains
    workflow-level navigation/recovery behavior. Pre-execution revisions and post-failure
    reactive replans are counted separately.
    """

    def __init__(
        self,
        *,
        env: Any,
        config: Stage6RuntimeConfig,
        reasoning_chain: PlanSource,
        controller: ControllerAdapter,
        state_provider: StateProvider,
        goal_checker: GoalChecker,
        cognitive_planner: Optional[CognitivePlanner] = None,
        legacy_plan_source: Optional[PlanSource] = None,
        reflexion: Optional[ReflexionProvider] = None,
        legacy_memory_sink: Optional[LegacyMemorySink] = None,
        multimodal_memory_sink: Optional[MultimodalMemorySink] = None,
        acquisition_store: Optional[AcquisitionStore] = None,
        calibration_store: Optional[CalibrationEpisodeStore] = None,
        confidence_observer: Optional[ConfidenceObservationCollector] = None,
        passive_confidence_scorer: Optional[PassiveConfidenceScorer] = None,
        trace_writer: Optional[JsonlTraceWriter] = None,
        record_metadata_provider: Optional[
            Callable[[bool], Mapping[str, Any]]
        ] = None,
        episode_id_provider: Optional[Callable[[int], str]] = None,
        development_shadow_observer: Any = None,
        chrmlite_plan_source: Optional[PlanSource] = None,
    ):
        config.validate()
        if config.mode == "dc3pa" and cognitive_planner is None:
            raise ValueError("cognitive_planner is required in dc3pa mode")
        if config.mode == "mp5_legacy" and legacy_plan_source is None:
            raise ValueError("legacy_plan_source is required in mp5_legacy mode")
        if (
            config.mode == "chrmlite_estimation_collection_v41"
            and chrmlite_plan_source is None
        ):
            raise ValueError(
                "chrmlite_plan_source is required in chrmlite_estimation_collection_v41 mode"
            )
        self.env = env
        self.config = config
        self.reasoning_chain = reasoning_chain
        self.controller = controller
        self.state_provider = state_provider
        self.goal_checker = goal_checker
        self.cognitive_planner = cognitive_planner
        self.legacy_plan_source = legacy_plan_source
        self.reflexion = reflexion
        self.legacy_memory_sink = legacy_memory_sink
        self.multimodal_memory_sink = multimodal_memory_sink
        self.acquisition_store = acquisition_store
        self.calibration_store = calibration_store
        self.confidence_observer = confidence_observer
        self.passive_confidence_scorer = passive_confidence_scorer
        self.trace_writer = trace_writer
        self.record_metadata_provider = record_metadata_provider
        self.episode_id_provider = episode_id_provider
        self.development_shadow_observer = development_shadow_observer
        self.chrmlite_plan_source = chrmlite_plan_source
        self.memory_mode = MemoryMode.parse(config.memory_mode)
        if config.model_confidence_collection == "passive_final_plan":
            if confidence_observer is None or passive_confidence_scorer is None:
                raise ValueError(
                    "passive_final_plan confidence collection requires an observation "
                    "collector and passive scorer"
                )

    def _record_metadata(self, task_completed: bool) -> Dict[str, Any]:
        if self.record_metadata_provider is None:
            return {}
        metadata = dict(self.record_metadata_provider(bool(task_completed)))
        if any(not str(key).strip() for key in metadata):
            raise ValueError("Record metadata contains an empty key")
        return metadata

    def _emit(
        self,
        events: list[RuntimeEvent],
        event_type: str,
        attempt: int,
        payload: Mapping[str, Any],
    ) -> None:
        event = RuntimeEvent(
            event_type=event_type,
            attempt=attempt,
            payload=dict(sanitize_for_trace(dict(payload))),
        )
        events.append(event)
        if self.trace_writer is not None:
            self.trace_writer.write(event_type, {"attempt": attempt, **event.to_dict()["payload"]})

    @staticmethod
    def _planning_context(
        *,
        snapshot: StateSnapshot,
        task_information: Mapping[str, Any],
        underground: bool,
        previous_plan: Optional[Plan],
        check_result: Mapping[str, Any],
        reflection: str,
        env: Any,
    ) -> Dict[str, Any]:
        return {
            "task_information": dict(task_information),
            "underground": bool(underground),
            "previous_workflow": (
                previous_plan.to_legacy_workflow() if previous_plan is not None else None
            ),
            "check_result": dict(check_result),
            "reflection": reflection,
            # Work_Memory currently accepts env but does not need the object for prompt
            # generation. Do not place a simulator instance inside ReliabilityContext.
            "env": None,
            "task_context": snapshot.reliability_context.task_context,
            "image": snapshot.reliability_context.image,
            "image_vector": snapshot.reliability_context.image_vector,
            **dict(snapshot.reliability_context.metadata),
        }

    @staticmethod
    def _cognitive_context(
        planning_context: Mapping[str, Any], snapshot: StateSnapshot
    ) -> ReliabilityContext:
        metadata = {
            key: value
            for key, value in planning_context.items()
            if key not in {"task_context", "image", "image_vector"}
        }
        metadata.setdefault("environment_step_index", 0)
        return ReliabilityContext(
            task_context=snapshot.reliability_context.task_context,
            image=snapshot.reliability_context.image,
            image_vector=snapshot.reliability_context.image_vector,
            metadata=metadata,
        )

    @staticmethod
    def _validate_plan_task(plan: Plan, task: str) -> Plan:
        if not isinstance(plan, Plan):
            raise TypeError("planner must return a Plan")
        if plan.task != task:
            raise ValueError(
                f"planner returned task {plan.task!r} for requested task {task!r}"
            )
        return plan

    def _fallback_reasoning_plan(
        self,
        task: str,
        state: AgentState,
        planning_context: Mapping[str, Any],
    ) -> Plan:
        return self._validate_plan_task(
            self.reasoning_chain.plan(task, state, planning_context), task
        )

    @staticmethod
    def _is_non_retryable_planning_error(error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        if error_type in {"authenticationerror", "permissionerror"}:
            return True
        message = str(error).lower()
        markers = (
            "quota",
            "insufficient",
            "forbidden",
            "unauthorized",
            "invalid api key",
            "incorrect api key",
        )
        return any(marker in message for marker in markers)

    def _plan(
        self,
        *,
        task: str,
        snapshot: StateSnapshot,
        planning_context: Mapping[str, Any],
        attempt: int,
        events: list[RuntimeEvent],
    ) -> _PlanningDecision:
        if self.config.mode == "mp5_legacy":
            assert self.legacy_plan_source is not None
            plan = self._validate_plan_task(
                self.legacy_plan_source.plan(task, snapshot.state, planning_context), task
            )
            return _PlanningDecision(plan=plan)
        if self.config.mode == "reasoning_only":
            return _PlanningDecision(
                plan=self._validate_plan_task(
                    self.reasoning_chain.plan(task, snapshot.state, planning_context), task
                )
            )
        if self.config.mode == "chrmlite_estimation_collection_v41":
            assert self.chrmlite_plan_source is not None
            return _PlanningDecision(
                plan=self._validate_plan_task(
                    self.chrmlite_plan_source.plan(
                        task, snapshot.state, planning_context
                    ),
                    task,
                )
            )

        assert self.cognitive_planner is not None
        try:
            outcome = self.cognitive_planner.plan_with_outcome(
                task,
                snapshot.state,
                self._cognitive_context(planning_context, snapshot),
            )
        except Exception as exc:
            self._emit(
                events,
                "dc3pa_planning_failed",
                attempt,
                {"error_type": type(exc).__name__, "error": str(exc)},
            )
            if self.config.planner_failure_policy == "raise":
                raise
            if self.config.planner_failure_policy == "return_failure":
                return _PlanningDecision(
                    plan=None,
                    blocked_reason=f"dc3pa_planning_failed:{type(exc).__name__}",
                )
            if self._is_non_retryable_planning_error(exc):
                return _PlanningDecision(
                    plan=None,
                    blocked_reason=f"dc3pa_planning_failed:{type(exc).__name__}",
                )
            try:
                fallback = self._fallback_reasoning_plan(
                    task, snapshot.state, planning_context
                )
            except Exception as fallback_exc:
                self._emit(
                    events,
                    "reasoning_fallback_failed",
                    attempt,
                    {
                        "error_type": type(fallback_exc).__name__,
                        "error": str(fallback_exc),
                    },
                )
                return _PlanningDecision(
                    plan=None,
                    fallback_used=True,
                    blocked_reason=(
                        "reasoning_fallback_failed:"
                        f"{type(fallback_exc).__name__}"
                    ),
                )
            self._emit(
                events,
                "reasoning_fallback_used",
                attempt,
                {"reason": f"dc3pa_planning_failed:{type(exc).__name__}"},
            )
            return _PlanningDecision(plan=fallback, fallback_used=True)

        final_plan = getattr(outcome, "final_plan", None)
        if not isinstance(final_plan, Plan):
            raise TypeError("cognitive planner outcome must expose final_plan: Plan")
        self._validate_plan_task(final_plan, task)
        unresolved = tuple(getattr(outcome, "unresolved", ()) or ())
        if unresolved:
            blocking_unresolved = tuple(
                item
                for item in unresolved
                if not (
                    isinstance(item, Mapping)
                    and item.get("hard_conflict") is False
                )
            )
            self._emit(
                events,
                "dc3pa_plan_unresolved",
                attempt,
                {
                    "plan_id": final_plan.plan_id,
                    "plan_version": final_plan.version,
                    "unresolved": unresolved,
                    "blocking_unresolved": blocking_unresolved,
                },
            )
            if not blocking_unresolved:
                self._emit(
                    events,
                    "non_blocking_dc3pa_unresolved",
                    attempt,
                    {
                        "plan_id": final_plan.plan_id,
                        "plan_version": final_plan.version,
                        "unresolved_count": len(unresolved),
                    },
                )
                return _PlanningDecision(plan=final_plan, outcome=outcome)
            if self.config.unresolved_plan_policy == "block":
                return _PlanningDecision(
                    plan=None,
                    outcome=outcome,
                    blocked_reason="unresolved_dc3pa_plan",
                )
            if self.config.unresolved_plan_policy == "reasoning_only":
                try:
                    fallback = self._fallback_reasoning_plan(
                        task, snapshot.state, planning_context
                    )
                except Exception as exc:
                    return _PlanningDecision(
                        plan=None,
                        outcome=outcome,
                        fallback_used=True,
                        blocked_reason=(
                            "unresolved_reasoning_fallback_failed:"
                            f"{type(exc).__name__}"
                        ),
                    )
                self._emit(
                    events,
                    "reasoning_fallback_used",
                    attempt,
                    {"reason": "unresolved_dc3pa_plan"},
                )
                return _PlanningDecision(
                    plan=fallback, outcome=outcome, fallback_used=True
                )
            self._emit(
                events,
                "unsafe_unresolved_plan_execution_enabled",
                attempt,
                {
                    "plan_id": final_plan.plan_id,
                    "plan_version": final_plan.version,
                },
            )
            return _PlanningDecision(
                plan=final_plan,
                outcome=outcome,
                unsafe_unresolved_execution=True,
            )
        return _PlanningDecision(plan=final_plan, outcome=outcome)

    def _record_success_memories(
        self,
        *,
        task: str,
        task_information: Mapping[str, Any],
        plan: Plan,
        execution_telemetry: Tuple[Any, ...],
        initial_scene: Optional[SceneObservation],
        final_scene: Optional[SceneObservation],
        attempt: int,
        events: list[RuntimeEvent],
    ) -> bool:
        if self.memory_mode is not MemoryMode.ACQUIRE:
            self._emit(
                events,
                "memory_recording_skipped",
                attempt,
                {"task": task, "memory_mode": self.memory_mode.value},
            )
            return False

        requested_any = False
        recorded_any = False
        failures: list[Exception] = []
        if self.config.record_legacy_workflow_memory and self.legacy_memory_sink is not None:
            requested_any = True
            try:
                self.legacy_memory_sink.record_success(task_information, plan)
                recorded_any = True
                self._emit(events, "legacy_memory_recorded", attempt, {"task": task})
            except Exception as exc:
                failures.append(exc)
                self._emit(
                    events,
                    "legacy_memory_record_failed",
                    attempt,
                    {"error_type": type(exc).__name__, "error": str(exc)},
                )
        if (
            self.config.record_multimodal_memory
            and self.multimodal_memory_sink is not None
        ):
            requested_any = True
            scenes = []
            if self.config.capture_initial_scene and initial_scene is not None:
                scenes.append(initial_scene)
            if self.config.capture_final_scene and final_scene is not None:
                scenes.append(final_scene)
            try:
                result = self.multimodal_memory_sink.record_success(
                    SuccessfulEpisode(
                        task_name=task,
                        plan=plan,
                        scenes=tuple(scenes),
                        metadata={
                            "stage": 6,
                            "mode": self.config.mode,
                            "attempt": attempt,
                            **self._record_metadata(True),
                        },
                    )
                )
                recorded_any = True
                self._emit(
                    events,
                    "multimodal_memory_recorded",
                    attempt,
                    {"task": task, "scene_count": len(scenes), "result": result},
                )
            except Exception as exc:
                failures.append(exc)
                self._emit(
                    events,
                    "multimodal_memory_record_failed",
                    attempt,
                    {"error_type": type(exc).__name__, "error": str(exc)},
                )
        if failures and self.config.memory_failure_policy == "raise":
            raise failures[0]
        return recorded_any if requested_any else False

    def _record_acquisition_success(
        self,
        *,
        task: str,
        task_information: Mapping[str, Any],
        plan: Plan,
        execution_telemetry: Tuple[Any, ...],
        episode_id: str,
        attempt: int,
        events: list[RuntimeEvent],
    ) -> bool:
        if self.acquisition_store is None:
            return False

        path, candidate_count = commit_successful_acquisition(
            store=self.acquisition_store,
            episode_id=episode_id,
            task=task,
            task_information=task_information,
            plan=plan,
            execution_telemetry=execution_telemetry,
            attempt=attempt,
            mode=self.config.mode,
            metadata=self._record_metadata(True),
        )
        self._emit(
            events,
            "acquisition_record_committed",
            attempt,
            {
                "task": task,
                "episode_id": episode_id,
                "scene_candidate_count": candidate_count,
                "path": str(path),
            },
        )
        return True

    def _record_calibration_episode(
        self,
        *,
        task: str,
        task_information: Mapping[str, Any],
        plan: Plan,
        execution_telemetry: Tuple[Any, ...],
        episode_id: str,
        success: bool,
        failure_reason: str,
        confidence_observations: Tuple[Mapping[str, Any], ...] = (),
        attempt: int,
        events: list[RuntimeEvent],
    ) -> bool:
        if self.calibration_store is None:
            return False

        path = commit_calibration_episode(
            store=self.calibration_store,
            episode_id=episode_id,
            task=task,
            task_information=task_information,
            plan=plan,
            execution_telemetry=execution_telemetry,
            success=success,
            failure_reason=failure_reason,
            attempt=attempt,
            mode=self.config.mode,
            confidence_observations=confidence_observations,
            metadata=self._record_metadata(success),
        )
        self._emit(
            events,
            "calibration_episode_committed",
            attempt,
            {
                "task": task,
                "episode_id": episode_id,
                "success": success,
                "path": str(path),
            },
        )
        return True

    def _collect_passive_final_plan_confidence(
        self,
        *,
        plan: Plan,
        state: AgentState,
        context: ReliabilityContext,
        attempt: int,
        events: list[RuntimeEvent],
    ) -> None:
        if self.config.model_confidence_collection != "passive_final_plan":
            return
        assert self.confidence_observer is not None
        assert self.passive_confidence_scorer is not None
        self.confidence_observer.clear()
        for step_index, _step in enumerate(plan.steps):
            try:
                self.passive_confidence_scorer.score(plan, step_index, state, context)
            except Exception as exc:
                self._emit(
                    events,
                    "passive_confidence_collection_failed",
                    attempt,
                    {
                        "plan_id": plan.plan_id,
                        "plan_version": plan.version,
                        "step_index": step_index,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                continue
        self._emit(
            events,
            "passive_confidence_collected",
            attempt,
            {
                "plan_id": plan.plan_id,
                "plan_version": plan.version,
                "step_count": len(plan.steps),
                "observation_count": len(
                    self.confidence_observer.for_plan(plan.plan_id, plan.version)
                ),
            },
        )

    def _reflect(
        self,
        *,
        task_information: Mapping[str, Any],
        plan: Plan,
        execution: ExecutionResult,
        underground: bool,
        events: list[RuntimeEvent],
        attempt: int,
    ) -> str:
        if self.reflexion is None:
            return ""
        try:
            reflection = self.reflexion.reflect(
                task_information=task_information,
                previous_workflow=plan.to_legacy_workflow(),
                check_result=execution.raw
                or {
                    "success": execution.success,
                    "feedback": execution.feedback,
                    "suggestion": execution.suggestion,
                },
                underground=underground,
            )
            self._emit(
                events,
                "reflection_created",
                attempt,
                {"has_reflection": bool(reflection)},
            )
            return reflection
        except Exception as exc:
            self._emit(
                events,
                "reflection_failed",
                attempt,
                {"error_type": type(exc).__name__, "error": str(exc)},
            )
            return ""

    def run_task(
        self,
        task_information: Mapping[str, Any],
        *,
        underground: bool = False,
    ) -> TaskRunResult:
        if not isinstance(task_information, Mapping):
            raise TypeError("task_information must be a mapping")

        guard = None
        if self.memory_mode.requires_frozen_snapshot:
            manifest = MemorySnapshotManifest.from_json(
                self.config.memory_snapshot_manifest
            )
            guard = SnapshotGuard(manifest)
            guard.__enter__()
        try:
            return self._run_task_guarded(task_information, underground=underground)
        finally:
            if guard is not None:
                guard.__exit__(*sys.exc_info())

    def _run_task_guarded(
        self,
        task_information: Mapping[str, Any],
        *,
        underground: bool = False,
    ) -> TaskRunResult:
        if not isinstance(task_information, Mapping):
            raise TypeError("task_information must be a mapping")
        task = task_name_from_information(task_information)
        events: list[RuntimeEvent] = []
        attempts: list[AttemptRecord] = []
        previous_plan: Optional[Plan] = None
        check_result: Dict[str, Any] = {}
        reflection = ""
        reactive_replans = 0
        pre_execution_revisions = 0
        evaluation_count = 0
        fallback_count = 0
        block_count = 0
        controller_executions = 0
        final_plan: Optional[Plan] = None
        failure_reason = "attempt_limit_reached"

        for attempt_index in range(1, self.config.max_execution_attempts + 1):
            started = time.monotonic()
            initial_snapshot = self.state_provider.snapshot(task_information, underground)
            if initial_snapshot.state.task != task:
                raise ValueError(
                    f"StateProvider returned task {initial_snapshot.state.task!r}, expected {task!r}"
                )
            planning_context = self._planning_context(
                snapshot=initial_snapshot,
                task_information=task_information,
                underground=underground,
                previous_plan=previous_plan,
                check_result=check_result,
                reflection=reflection,
                env=self.env,
            )
            self._emit(
                events,
                "planning_started",
                attempt_index,
                {
                    "task": task,
                    "mode": self.config.mode,
                    "inventory": initial_snapshot.state.normalized_inventory(),
                    "underground": underground,
                },
            )
            try:
                decision = self._plan(
                    task=task,
                    snapshot=initial_snapshot,
                    planning_context=planning_context,
                    attempt=attempt_index,
                    events=events,
                )
            except Exception:
                if self.config.planner_failure_policy == "raise":
                    raise
                decision = _PlanningDecision(
                    plan=None, blocked_reason="unhandled_planning_failure"
                )

            if decision.fallback_used:
                fallback_count += 1
            outcome = decision.outcome
            if outcome is not None:
                pre_execution_revisions += int(getattr(outcome, "revision_count", 0) or 0)
                evaluation_count += len(tuple(getattr(outcome, "evaluation_reports", ()) or ()))
                self._emit(
                    events,
                    "dc3pa_planning_outcome",
                    attempt_index,
                    {
                        "revision_count": int(getattr(outcome, "revision_count", 0) or 0),
                        "evaluation_count": len(
                            tuple(getattr(outcome, "evaluation_reports", ()) or ())
                        ),
                        "unresolved_count": len(
                            tuple(getattr(outcome, "unresolved", ()) or ())
                        ),
                    },
                )
            if decision.plan is None:
                block_count += 1
                failure_reason = decision.blocked_reason or "planning_blocked"
                self._emit(
                    events,
                    "planning_blocked",
                    attempt_index,
                    {"reason": failure_reason},
                )
                attempts.append(
                    AttemptRecord(
                        attempt=attempt_index,
                        plan_id=None,
                        plan_version=None,
                        controller_executed=False,
                        controller_success=False,
                        goal_success=False,
                        duration_seconds=time.monotonic() - started,
                        fallback_used=decision.fallback_used,
                        blocked_reason=failure_reason,
                    )
                )
                break

            plan = decision.plan
            final_plan = plan
            reliability_context = self._cognitive_context(planning_context, initial_snapshot)
            self._emit(
                events,
                "plan_ready_for_controller",
                attempt_index,
                {
                    "plan_id": plan.plan_id,
                    "plan_version": plan.version,
                    "step_count": len(plan.steps),
                    "source": plan.source,
                    "fallback_used": decision.fallback_used,
                    "unsafe_unresolved_execution": decision.unsafe_unresolved_execution,
                },
            )
            episode_id = (
                self.episode_id_provider(attempt_index)
                if self.episode_id_provider is not None
                else new_episode_id(task, attempt_index)
            )
            observer_prepared = True
            if self.development_shadow_observer is not None:
                try:
                    prepared = self.development_shadow_observer.prepare_attempt(
                        plan=plan,
                        state=initial_snapshot.state,
                        context=reliability_context,
                        episode_id=episode_id,
                        attempt=attempt_index,
                    )
                    if prepared is False:
                        observer_prepared = False
                except Exception as exc:
                    if self.config.mode == "chrmlite_estimation_collection_v41":
                        raise
                    self.development_shadow_observer.errors.append(
                        f"prepare attempt {attempt_index}: {type(exc).__name__}: {exc}"
                    )
                    self._emit(
                        events,
                        "development_shadow_prepare_failed",
                        attempt_index,
                        {"error_type": type(exc).__name__, "error": str(exc)},
                    )
            if not observer_prepared:
                failure_reason = "completed_receipt_prevents_relaunch"
                self._emit(
                    events,
                    "collection_relaunch_blocked",
                    attempt_index,
                    {"plan_id": plan.plan_id, "reason": failure_reason},
                )
                attempts.append(
                    AttemptRecord(
                        attempt=attempt_index,
                        plan_id=plan.plan_id,
                        plan_version=plan.version,
                        controller_executed=False,
                        controller_success=False,
                        goal_success=False,
                        duration_seconds=time.monotonic() - started,
                        blocked_reason=failure_reason,
                    )
                )
                break
            self._collect_passive_final_plan_confidence(
                plan=plan,
                state=initial_snapshot.state,
                context=reliability_context,
                attempt=attempt_index,
                events=events,
            )
            controller_executions += 1
            try:
                execution = self.controller.execute(
                    self.env, plan, dict(task_information), underground
                )
            except Exception as exc:
                if self.config.controller_exception_policy == "raise":
                    raise
                execution = ExecutionResult(
                    success=False,
                    underground=underground,
                    feedback=f"Controller exception: {type(exc).__name__}: {exc}",
                    suggestion="Inspect Controller trace and environment state.",
                    raw={"success": False, "error_type": type(exc).__name__},
                )
                self._emit(
                    events,
                    "controller_exception",
                    attempt_index,
                    {"error_type": type(exc).__name__, "error": str(exc)},
                )
            underground = bool(execution.underground)
            goal_success = False
            goal_check_called = False
            goal_check_error = ""
            if execution.success:
                if self.config.require_goal_check:
                    goal_check_called = True
                    try:
                        goal_success = self.goal_checker.is_done(task_information)
                    except Exception as exc:
                        goal_check_error = f"{type(exc).__name__}: {exc}"
                        if self.config.goal_check_exception_policy == "raise":
                            raise
                        goal_success = False
                        self._emit(
                            events,
                            "goal_check_exception",
                            attempt_index,
                            {"error_type": type(exc).__name__, "error": str(exc)},
                        )
                else:
                    goal_success = True
            attempt_failure_reason = (
                "" if goal_success else (
                    "goal_not_achieved"
                    if execution.success
                    else "controller_reported_failure"
                )
            )
            confidence_observations: Tuple[Mapping[str, Any], ...] = ()
            if self.confidence_observer is not None:
                confidence_observations = tuple(
                    item.to_dict()
                    for item in self.confidence_observer.drain_for_execution(
                        plan_id=plan.plan_id,
                        plan_version=plan.version,
                        episode_id=episode_id,
                    )
                )
            self._emit(
                events,
                "controller_completed",
                attempt_index,
                {
                    "plan_id": plan.plan_id,
                    "controller_success": execution.success,
                    "goal_success": goal_success,
                    "feedback": execution.feedback,
                    "suggestion": execution.suggestion,
                    "underground": underground,
                },
            )
            if self.development_shadow_observer is not None:
                try:
                    finalize_kwargs = dict(
                        plan=plan,
                        episode_id=episode_id,
                        execution_telemetry=execution.telemetry,
                        confidence_observations=confidence_observations,
                        task_completed=goal_success,
                        attempt=attempt_index,
                    )
                    if getattr(
                        self.development_shadow_observer,
                        "supports_dual_level_outcomes",
                        False,
                    ):
                        finalize_kwargs.update(
                            evaluator_called=goal_check_called,
                            evaluator_error=goal_check_error,
                        )
                    self.development_shadow_observer.finalize_attempt(
                        **finalize_kwargs
                    )
                except Exception as exc:
                    if self.config.mode == "chrmlite_estimation_collection_v41":
                        raise
                    self.development_shadow_observer.errors.append(
                        f"finalize attempt {attempt_index}: {type(exc).__name__}: {exc}"
                    )
                    self._emit(
                        events,
                        "development_shadow_finalize_failed",
                        attempt_index,
                        {"error_type": type(exc).__name__, "error": str(exc)},
                    )
            self._record_calibration_episode(
                task=task,
                task_information=task_information,
                plan=plan,
                execution_telemetry=execution.telemetry,
                episode_id=episode_id,
                success=goal_success,
                failure_reason=attempt_failure_reason,
                confidence_observations=confidence_observations,
                attempt=attempt_index,
                events=events,
            )
            attempts.append(
                AttemptRecord(
                    attempt=attempt_index,
                    plan_id=plan.plan_id,
                    plan_version=plan.version,
                    controller_executed=True,
                    controller_success=execution.success,
                    goal_success=goal_success,
                    duration_seconds=time.monotonic() - started,
                    feedback=execution.feedback,
                    suggestion=execution.suggestion,
                    fallback_used=decision.fallback_used,
                )
            )
            if goal_success:
                final_scene = None
                if self.config.capture_final_scene:
                    try:
                        final_snapshot = self.state_provider.snapshot(
                            task_information, underground
                        )
                        final_scene = final_snapshot.scene
                    except Exception as exc:
                        self._emit(
                            events,
                            "final_state_snapshot_failed",
                            attempt_index,
                            {"error_type": type(exc).__name__, "error": str(exc)},
                        )
                        if self.config.memory_failure_policy == "raise":
                            raise
                memory_recorded = self._record_success_memories(
                    task=task,
                    task_information=task_information,
                    plan=plan,
                    execution_telemetry=execution.telemetry,
                    initial_scene=initial_snapshot.scene,
                    final_scene=final_scene,
                    attempt=attempt_index,
                    events=events,
                )
                acquisition_recorded = self._record_acquisition_success(
                    task=task,
                    task_information=task_information,
                    plan=plan,
                    execution_telemetry=execution.telemetry,
                    episode_id=episode_id,
                    attempt=attempt_index,
                    events=events,
                )
                self._emit(
                    events,
                    "task_succeeded",
                    attempt_index,
                    {
                        "task": task,
                        "memory_recorded": memory_recorded,
                        "acquisition_recorded": acquisition_recorded,
                    },
                )
                return TaskRunResult(
                    task=task,
                    mode=self.config.mode,
                    success=True,
                    attempts=tuple(attempts),
                    events=tuple(events),
                    reactive_replan_count=reactive_replans,
                    pre_execution_revision_count=pre_execution_revisions,
                    evaluation_count=evaluation_count,
                    planning_fallback_count=fallback_count,
                    pre_execution_block_count=block_count,
                    controller_execution_count=controller_executions,
                    final_plan=plan,
                    final_underground=underground,
                    memory_recorded=memory_recorded,
                )

            failure_reason = (
                "goal_not_achieved" if execution.success else "controller_reported_failure"
            )
            check_result = {
                "success": execution.success,
                "feedback": execution.feedback,
                "suggestion": execution.suggestion,
            }
            check_result.update(dict(execution.raw))
            check_result.setdefault("success", execution.success)
            check_result.setdefault("feedback", execution.feedback)
            check_result.setdefault("suggestion", execution.suggestion)
            reflection = self._reflect(
                task_information=task_information,
                plan=plan,
                execution=execution,
                underground=underground,
                events=events,
                attempt=attempt_index,
            )
            previous_plan = plan
            if attempt_index < self.config.max_execution_attempts:
                reactive_replans += 1
                self._emit(
                    events,
                    "reactive_replan_scheduled",
                    attempt_index,
                    {"next_attempt": attempt_index + 1, "reason": failure_reason},
                )

        return TaskRunResult(
            task=task,
            mode=self.config.mode,
            success=False,
            attempts=tuple(attempts),
            events=tuple(events),
            reactive_replan_count=reactive_replans,
            pre_execution_revision_count=pre_execution_revisions,
            evaluation_count=evaluation_count,
            planning_fallback_count=fallback_count,
            pre_execution_block_count=block_count,
            controller_execution_count=controller_executions,
            final_plan=final_plan,
            final_underground=underground,
            memory_recorded=False,
            failure_reason=failure_reason,
        )
