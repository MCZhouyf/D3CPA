"""Real-experiment configuration and orchestration contracts."""

from .binding import (
    FrozenArtifactBinding,
    build_artifact_binding,
    build_bound_development_protocol,
    load_binding,
    save_binding,
)
from .blueprint import (
    AcquisitionAssignment,
    AuthorApproval,
    EnvironmentSearchSpace,
    PhaseBudget,
    RealExperimentBlueprint,
    load_blueprint,
    save_blueprint,
)
from .pack import PackValidationReport, render_runbook, validate_pack
from .phase_state import (
    ExperimentPhaseState,
    PhaseRecord,
    load_state,
    save_state_atomic,
)
from .launcher_validation import (
    LaunchValidationResult,
    validate_real_experiment_launch,
)
from .author_decisions import (
    AuthorDecisionPackManifest,
    compile_author_decision_pack,
    prompt_hashes,
)
from .dry_run import (
    DryRunAuditReport,
    DryRunCampaign,
    DryRunReceipt,
    audit_dry_run,
    build_dry_run_campaign,
    ensure_not_dry_run_artifact_path,
    load_campaign,
    load_receipt,
)

__all__ = [
    "AcquisitionAssignment",
    "AuthorApproval",
    "AuthorDecisionPackManifest",
    "DryRunAuditReport",
    "DryRunCampaign",
    "DryRunReceipt",
    "EnvironmentSearchSpace",
    "ExperimentPhaseState",
    "FrozenArtifactBinding",
    "LaunchValidationResult",
    "PackValidationReport",
    "PhaseBudget",
    "PhaseRecord",
    "RealExperimentBlueprint",
    "build_artifact_binding",
    "build_bound_development_protocol",
    "build_dry_run_campaign",
    "audit_dry_run",
    "compile_author_decision_pack",
    "ensure_not_dry_run_artifact_path",
    "load_binding",
    "load_blueprint",
    "load_campaign",
    "load_receipt",
    "load_state",
    "prompt_hashes",
    "render_runbook",
    "save_binding",
    "save_blueprint",
    "save_state_atomic",
    "validate_pack",
    "validate_real_experiment_launch",
]
