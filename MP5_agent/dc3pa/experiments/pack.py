"""Validate a real-experiment configuration pack and generate a runbook."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional

from dc3pa.reliability.activation_policy import load_activation_policy

from .blueprint import RealExperimentBlueprint, load_blueprint, sha256_file
from .binding import FrozenArtifactBinding, load_binding
from .phase_state import ExperimentPhaseState, load_state


PACK_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PackValidationReport:
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    summary: Mapping[str, Any]

    def require_eligible(self) -> None:
        if not self.eligible:
            raise ValueError("Experiment pack validation failed: " + "; ".join(self.errors))

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "summary": dict(self.summary),
        }


def validate_pack(
    *,
    blueprint_path: str | Path,
    activation_policy_path: str | Path,
    data_sufficiency_policy_path: str | Path,
    binding_path: Optional[str | Path] = None,
    state_path: Optional[str | Path] = None,
) -> PackValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    blueprint = load_blueprint(blueprint_path)
    policy = load_activation_policy(activation_policy_path)
    if blueprint.activation_policy_id != policy.policy_id:
        errors.append("Blueprint activation policy ID mismatch")
    if blueprint.activation_policy_file_sha256 != sha256_file(
        activation_policy_path
    ):
        errors.append("Activation policy file SHA mismatch")
    if blueprint.data_sufficiency_policy_file_sha256 != sha256_file(
        data_sufficiency_policy_path
    ):
        errors.append("Data sufficiency policy file SHA mismatch")

    binding = None
    if binding_path:
        try:
            binding = load_binding(binding_path)
        except ValueError as exc:
            errors.append(f"Artifact binding invalid: {exc}")
        else:
            if binding.blueprint_id != blueprint.blueprint_id:
                errors.append("Artifact binding blueprint ID mismatch")
            if not blueprint.environment_search_space.contains(
                binding.selected_environment_parameters
            ):
                errors.append("Binding selected unregistered Environment parameters")

    state = None
    if state_path:
        try:
            state = load_state(state_path)
        except ValueError as exc:
            errors.append(f"Phase state invalid: {exc}")
        else:
            if state.experiment_id != blueprint.blueprint_id:
                errors.append("Phase state experiment ID mismatch")
            if state.records and state.records[0].phase != "blueprint_frozen":
                errors.append("First phase state record must freeze the blueprint")
            if binding and "memory_frozen" in state.completed_phases:
                memory_record = next(
                    record for record in state.records if record.phase == "memory_frozen"
                )
                recorded = memory_record.artifact_ids.get("memory_snapshot_sha256", "")
                if recorded and recorded != binding.memory_snapshot_sha256:
                    errors.append("Phase-state memory SHA differs from binding")
            if (
                "final_test_started" in state.completed_phases
                and "paper_release_frozen" not in state.completed_phases
            ):
                errors.append("Final test started before paper release")

    summary = {
        "blueprint_id": blueprint.blueprint_id,
        "profile": blueprint.profile,
        "final_task_count": len(blueprint.final_test_exclusion.tasks),
        "acquisition_group_count": len(blueprint.acquisition_assignments),
        "development_group_count": len(blueprint.development_assignments),
        "binding_id": binding.binding_id if binding else "",
        "completed_phases": list(state.completed_phases) if state else [],
        "next_phase": state.next_phase if state else "blueprint_frozen",
    }
    return PackValidationReport(
        eligible=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        summary=summary,
    )


def render_runbook(
    *,
    blueprint: RealExperimentBlueprint,
    binding: Optional[FrozenArtifactBinding],
    state: Optional[ExperimentPhaseState],
) -> str:
    completed = set(state.completed_phases if state else ())
    next_phase = state.next_phase if state else "blueprint_frozen"
    lines = [
        f"# DC3PA Real Experiment Runbook — {blueprint.blueprint_name}",
        "",
        f"- Blueprint ID: `{blueprint.blueprint_id}`",
        f"- Profile: `{blueprint.profile}`",
        f"- Source commit: `{blueprint.source_commit}`",
        f"- Next permitted phase: `{next_phase}`",
        "",
        "## Frozen design",
        "",
        f"- Final tasks: {len(blueprint.final_test_exclusion.tasks)}",
        f"- Acquisition groups: {len(blueprint.acquisition_assignments)}",
        f"- Development groups: {len(blueprint.development_assignments)}",
        f"- Collector: `{blueprint.collector_mode}`",
        f"- Controller profile: `{blueprint.controller_profile}`",
        f"- Planner model: `{blueprint.planner_model_id}`",
        f"- Confidence model: `{blueprint.confidence_model_id}`",
        "",
        "## Phase checklist",
        "",
    ]
    for phase in (
        "blueprint_frozen",
        "dry_run_completed",
        "acquisition_completed",
        "memory_frozen",
        "confidence_frozen",
        "environment_frozen",
        "development_data_validated",
        "fusion_candidate_frozen",
        "holdout_locked",
        "holdout_evaluated",
        "paper_release_frozen",
        "final_test_started",
    ):
        mark = "x" if phase in completed else " "
        lines.append(f"- [{mark}] `{phase}`")
    lines.extend(
        [
            "",
            "## Mandatory scientific rules",
            "",
            "1. Final-held-out terminal goals never enter acquisition or development.",
            "2. Final test task–seed pairs never enter development.",
            "3. Dry-run outputs are excluded from final fitting.",
            "4. Memory is frozen before confidence/environment/fusion development.",
            "5. Confidence and Environment parameters are frozen before final Fusion features.",
            "6. Fusion fitting reads train/tune only.",
            "7. Holdout is locked and evaluated once.",
            "8. Final test begins only after an eligible paper release.",
            "",
        ]
    )
    if binding:
        lines.extend(
            [
                "## Frozen artifact binding",
                "",
                f"- Binding ID: `{binding.binding_id}`",
                f"- Memory SHA: `{binding.memory_snapshot_sha256}`",
                f"- Confidence artifact: `{binding.confidence_artifact_id}`",
                f"- Environment parameters: `{json.dumps(dict(binding.selected_environment_parameters), sort_keys=True)}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Command policy",
            "",
            "This runbook intentionally does not invent Minecraft task commands or "
            "credentials. Use the repository's validated phase scripts and the "
            "author-approved external manifests. Record stdout, stderr, exit code, "
            "configuration hashes, and artifact hashes outside Git.",
            "",
        ]
    )
    return "\n".join(lines)
