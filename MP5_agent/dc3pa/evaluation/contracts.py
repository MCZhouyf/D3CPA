from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

from ..contracts import AgentState, Plan, PlanStep
from ..errors import ContractValidationError
from ..reliability.contracts import ReliabilityContext, ReliabilityResult

EDIT_OPERATIONS = {"insert_before", "insert_after", "replace", "delete"}
ISSUE_DIMENSIONS = {"knowledge", "model", "environment", "mixed"}
ISSUE_SEVERITIES = {"info", "warning", "error", "critical"}


@dataclass(frozen=True)
class EvaluationIssue:
    step_id: str
    dimension: str
    severity: str
    diagnosis: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.step_id:
            raise ContractValidationError("EvaluationIssue.step_id cannot be empty")
        if self.dimension not in ISSUE_DIMENSIONS:
            raise ContractValidationError(
                f"Unknown issue dimension {self.dimension!r}"
            )
        if self.severity not in ISSUE_SEVERITIES:
            raise ContractValidationError(f"Unknown issue severity {self.severity!r}")
        if not self.diagnosis.strip():
            raise ContractValidationError("EvaluationIssue.diagnosis cannot be empty")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvaluationIssue":
        if not isinstance(data, Mapping):
            raise ContractValidationError("EvaluationIssue must be an object")
        evidence = data.get("evidence", {})
        if not isinstance(evidence, Mapping):
            raise ContractValidationError("EvaluationIssue.evidence must be an object")
        return cls(
            step_id=str(data.get("step_id", "")),
            dimension=str(data.get("dimension", "mixed")),
            severity=str(data.get("severity", "warning")),
            diagnosis=str(data.get("diagnosis", "")),
            evidence=dict(evidence),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlanEdit:
    operation: str
    target_step_id: str
    steps: tuple[PlanStep, ...] = field(default_factory=tuple)
    edit_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.edit_id.strip():
            raise ContractValidationError("PlanEdit.edit_id cannot be empty")
        if self.operation not in EDIT_OPERATIONS:
            raise ContractValidationError(f"Unknown plan edit operation {self.operation!r}")
        if not self.target_step_id:
            raise ContractValidationError("PlanEdit.target_step_id cannot be empty")
        if self.operation == "delete" and self.steps:
            raise ContractValidationError("delete edits cannot include steps")
        if self.operation != "delete" and not self.steps:
            raise ContractValidationError(
                f"{self.operation} edits must include at least one step"
            )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanEdit":
        if not isinstance(data, Mapping):
            raise ContractValidationError("PlanEdit must be an object")
        raw_steps = data.get("steps", [])
        if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes)):
            raise ContractValidationError("PlanEdit.steps must be a list")
        return cls(
            operation=str(data.get("operation", "")),
            target_step_id=str(data.get("target_step_id", "")),
            steps=tuple(PlanStep.from_dict(step) for step in raw_steps),
            edit_id=str(data.get("edit_id") or uuid.uuid4().hex),
            rationale=str(data.get("rationale", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "target_step_id": self.target_step_id,
            "steps": [step.to_dict() for step in self.steps],
            "edit_id": self.edit_id,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class EvaluationReport:
    plan_id: str
    plan_version: int
    summary: str
    issues: tuple[EvaluationIssue, ...] = field(default_factory=tuple)
    edits: tuple[PlanEdit, ...] = field(default_factory=tuple)
    replacement_steps: tuple[PlanStep, ...] = field(default_factory=tuple)
    accepted: bool = False
    request_replan: bool = False
    provider_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.plan_id:
            raise ContractValidationError("EvaluationReport.plan_id cannot be empty")
        if self.plan_version <= 0:
            raise ContractValidationError("EvaluationReport.plan_version must be positive")
        if not self.summary.strip():
            raise ContractValidationError("EvaluationReport.summary cannot be empty")
        if self.edits and self.replacement_steps:
            raise ContractValidationError(
                "Use either incremental edits or replacement_steps, not both"
            )
        if not isinstance(self.accepted, bool):
            raise ContractValidationError("accepted must be a JSON boolean")
        if not isinstance(self.request_replan, bool):
            raise ContractValidationError("request_replan must be a JSON boolean")
        outcomes = int(self.accepted) + int(self.request_replan) + int(self.has_patch)
        if outcomes != 1:
            raise ContractValidationError(
                "Exactly one evaluation outcome is required: accepted, concrete patch, "
                "or request_replan"
            )

    @property
    def has_patch(self) -> bool:
        return bool(self.edits or self.replacement_steps)

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        expected_plan: Optional[Plan] = None,
    ) -> "EvaluationReport":
        if not isinstance(data, Mapping):
            raise ContractValidationError("EvaluationReport must be an object")
        plan_id = str(data.get("plan_id") or (expected_plan.plan_id if expected_plan else ""))
        raw_version = data.get(
            "plan_version", expected_plan.version if expected_plan else 0
        )
        if isinstance(raw_version, bool):
            raise ContractValidationError("plan_version must be a positive integer")
        try:
            plan_version = int(raw_version)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("plan_version must be a positive integer") from exc
        if str(raw_version).strip() != str(plan_version) and not isinstance(raw_version, int):
            raise ContractValidationError("plan_version must be integer-like without truncation")
        raw_issues = data.get("issues", [])
        raw_edits = data.get("edits", [])
        raw_replacement = data.get(
            "replacement_steps", data.get("replacement_workflow", [])
        )
        if not isinstance(raw_issues, Sequence) or isinstance(raw_issues, (str, bytes)):
            raise ContractValidationError("EvaluationReport.issues must be a list")
        if not isinstance(raw_edits, Sequence) or isinstance(raw_edits, (str, bytes)):
            raise ContractValidationError("EvaluationReport.edits must be a list")
        if not isinstance(raw_replacement, Sequence) or isinstance(
            raw_replacement, (str, bytes)
        ):
            raise ContractValidationError(
                "EvaluationReport.replacement_steps must be a list"
            )
        accepted = data.get("accepted", False)
        request_replan = data.get("request_replan", False)
        if not isinstance(accepted, bool):
            raise ContractValidationError("accepted must be a JSON boolean")
        if not isinstance(request_replan, bool):
            raise ContractValidationError("request_replan must be a JSON boolean")
        provider_metadata = data.get("provider_metadata", {})
        if not isinstance(provider_metadata, Mapping):
            raise ContractValidationError("provider_metadata must be an object")
        report = cls(
            plan_id=plan_id,
            plan_version=plan_version,
            summary=str(data.get("summary", "")).strip(),
            issues=tuple(EvaluationIssue.from_dict(item) for item in raw_issues),
            edits=tuple(PlanEdit.from_dict(item) for item in raw_edits),
            replacement_steps=tuple(PlanStep.from_dict(item) for item in raw_replacement),
            accepted=accepted,
            request_replan=request_replan,
            provider_metadata=dict(provider_metadata),
        )
        if expected_plan is not None:
            valid_step_ids = {step.step_id for step in expected_plan.steps}
            unknown_issue_ids = {
                issue.step_id for issue in report.issues if issue.step_id not in valid_step_ids
            }
            if unknown_issue_ids:
                raise ContractValidationError(
                    f"Evaluation issues reference unknown step IDs: {sorted(unknown_issue_ids)}"
                )
            if report.plan_id != expected_plan.plan_id:
                raise ContractValidationError(
                    "Evaluation report targets a stale or different plan_id"
                )
            if report.plan_version != expected_plan.version:
                raise ContractValidationError(
                    "Evaluation report targets a stale plan version"
                )
        return report

    @classmethod
    def unresolved(cls, plan: Plan, summary: str) -> "EvaluationReport":
        return cls(
            plan_id=plan.plan_id,
            plan_version=plan.version,
            summary=summary,
            request_replan=True,
        )

    @classmethod
    def accepted_plan(cls, plan: Plan, summary: str) -> "EvaluationReport":
        return cls(
            plan_id=plan.plan_id,
            plan_version=plan.version,
            summary=summary,
            accepted=True,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "summary": self.summary,
            "issues": [issue.to_dict() for issue in self.issues],
            "edits": [edit.to_dict() for edit in self.edits],
            "replacement_steps": [step.to_dict() for step in self.replacement_steps],
            "accepted": self.accepted,
            "request_replan": self.request_replan,
            "provider_metadata": dict(self.provider_metadata),
        }


@dataclass(frozen=True)
class EvaluationRequest:
    plan: Plan
    state: AgentState
    step_indices: tuple[int, ...]
    reliability: tuple[ReliabilityResult, ...]
    context: ReliabilityContext = field(default_factory=ReliabilityContext)

    def __post_init__(self) -> None:
        if not self.step_indices:
            raise ContractValidationError("EvaluationRequest.step_indices cannot be empty")
        if len(self.step_indices) != len(self.reliability):
            raise ContractValidationError(
                "EvaluationRequest reliability must align with step_indices"
            )
        for index, result in zip(self.step_indices, self.reliability):
            if not 0 <= index < len(self.plan.steps):
                raise ContractValidationError(f"Evaluation step index {index} is out of range")
            if result.plan_id != self.plan.plan_id or result.plan_version != self.plan.version:
                raise ContractValidationError("Reliability result is stale for this plan")
            if result.step_index != index:
                raise ContractValidationError("Reliability result index mismatch")

    def to_prompt_payload(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "state": self.state.to_dict(),
            "evaluated_step_indices": list(self.step_indices),
            "reliability": [result.to_dict() for result in self.reliability],
            "context": self.context.prompt_metadata(),
        }
