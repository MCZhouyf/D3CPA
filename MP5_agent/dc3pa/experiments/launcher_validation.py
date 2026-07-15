"""Pre-launch validation helpers for author-approved real experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .binding import FrozenArtifactBinding
from .blueprint import (
    AcquisitionAssignment,
    PhaseBudget,
    RealExperimentBlueprint,
)
from .phase_state import ExperimentPhaseState


PHASE_TO_BUDGET = {
    "dry_run_completed": "dry_run",
    "acquisition_completed": "experience_acquisition",
    "confidence_frozen": "confidence_collection",
    "development_data_validated": "confidence_collection",
    "environment_frozen": "environment_tuning",
    "fusion_candidate_frozen": "fusion_feature_generation",
    "holdout_evaluated": "development_holdout",
    "final_test_started": "final_evaluation",
}


@dataclass(frozen=True)
class LaunchValidationResult:
    phase: str
    task: str
    seed: str
    budget_phase: str
    blueprint_id: str
    binding_id: str = ""
    phase_state_id: str = ""
    run_manifest_ids: Optional[Mapping[str, str]] = None

    def to_trace_payload(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "task": self.task,
            "seed": self.seed,
            "budget_phase": self.budget_phase,
            "blueprint_id": self.blueprint_id,
            "binding_id": self.binding_id,
            "phase_state_id": self.phase_state_id,
            "run_manifest_ids": dict(self.run_manifest_ids or {}),
        }


def _budget_for(blueprint: RealExperimentBlueprint, phase: str) -> PhaseBudget:
    budget_phase = PHASE_TO_BUDGET.get(phase)
    if budget_phase is None:
        raise ValueError(f"Phase {phase!r} is not a runnable experiment phase")
    for budget in blueprint.phase_budgets:
        if budget.phase == budget_phase:
            return budget
    raise ValueError(f"Blueprint has no budget for phase {budget_phase!r}")


def _assignment_pair(item: AcquisitionAssignment | Any) -> tuple[str, str]:
    return (str(item.task), str(item.seed))


def _validate_phase_assignment(
    *,
    blueprint: RealExperimentBlueprint,
    phase: str,
    task: str,
    seed: str,
) -> None:
    pair = (task, str(seed))
    if phase == "dry_run_completed":
        allowed = {
            _assignment_pair(item)
            for item in blueprint.development_assignments
            if item.role == "dev_train"
        }
        if pair not in allowed:
            raise ValueError("Dry-run launch must use a preregistered dev_train task-seed")
        return
    if phase == "acquisition_completed":
        allowed = {_assignment_pair(item) for item in blueprint.acquisition_assignments}
        if pair not in allowed:
            raise ValueError("Acquisition launch task-seed is not preregistered")
        return
    if phase in {
        "confidence_frozen",
        "development_data_validated",
        "environment_frozen",
        "fusion_candidate_frozen",
    }:
        allowed = {
            _assignment_pair(item)
            for item in blueprint.development_assignments
            if item.role in {"dev_train", "dev_tune"}
        }
        if pair not in allowed:
            raise ValueError("Development launch must use dev_train/dev_tune task-seed")
        return
    if phase == "holdout_evaluated":
        allowed = {
            _assignment_pair(item)
            for item in blueprint.development_assignments
            if item.role == "dev_holdout"
        }
        if pair not in allowed:
            raise ValueError("Holdout launch must use a dev_holdout task-seed")
        return
    if phase == "final_test_started":
        allowed = blueprint.final_test_exclusion.final_task_seed_pairs
        if pair not in allowed:
            raise ValueError("Final launch task-seed is not in the frozen final set")
        return
    raise ValueError(f"Phase {phase!r} is not launchable")


def validate_real_experiment_launch(
    *,
    blueprint: RealExperimentBlueprint,
    phase: str,
    task: str,
    seed: str,
    max_execution_attempts: Optional[int] = None,
    binding: Optional[FrozenArtifactBinding] = None,
    phase_state: Optional[ExperimentPhaseState] = None,
    run_manifest_ids: Optional[Mapping[str, str]] = None,
) -> LaunchValidationResult:
    blueprint_id = blueprint.blueprint_id or blueprint.compute_blueprint_id()
    if binding is not None and binding.blueprint_id != blueprint_id:
        raise ValueError("Binding blueprint ID does not match launch blueprint")
    if phase_state is not None and phase_state.experiment_id != blueprint_id:
        raise ValueError("Phase-state experiment ID does not match blueprint")
    if phase_state is not None and phase != phase_state.next_phase:
        raise ValueError(
            f"Launch phase must be the next permitted phase {phase_state.next_phase!r}"
        )
    budget = _budget_for(blueprint, phase)
    if max_execution_attempts is not None:
        if max_execution_attempts <= 0:
            raise ValueError("max_execution_attempts must be positive")
        if max_execution_attempts > budget.maximum_replans_per_episode + 1:
            raise ValueError("Launch attempts exceed preregistered replan budget")
    _validate_phase_assignment(
        blueprint=blueprint,
        phase=phase,
        task=task,
        seed=str(seed),
    )
    return LaunchValidationResult(
        phase=phase,
        task=task,
        seed=str(seed),
        budget_phase=budget.phase,
        blueprint_id=blueprint_id,
        binding_id=binding.binding_id if binding else "",
        phase_state_id=phase_state.state_id if phase_state else "",
        run_manifest_ids=dict(run_manifest_ids or {}),
    )
