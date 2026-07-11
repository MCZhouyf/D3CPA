from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from ..contracts import Plan, PlanStep
from ..errors import ContractValidationError
from .contracts import EvaluationReport, PlanEdit


@dataclass(frozen=True)
class PatchApplication:
    original_plan: Plan
    revised_plan: Plan
    earliest_changed_index: int
    changed_step_ids: tuple[str, ...]
    applied_edit_ids: tuple[str, ...]


class PlanEditor:
    """Apply an EvaluationReport atomically without mutating the input plan."""

    def apply(self, plan: Plan, report: EvaluationReport) -> PatchApplication:
        if report.plan_id != plan.plan_id or report.plan_version != plan.version:
            raise ContractValidationError("Cannot apply a stale evaluation report")
        if not report.has_patch:
            raise ContractValidationError("Evaluation report contains no concrete patch")
        existing_ids = [step.step_id for step in plan.steps]
        if len(existing_ids) != len(set(existing_ids)):
            raise ContractValidationError("Input plan contains duplicate step IDs")

        if report.replacement_steps:
            new_steps = list(report.replacement_steps)
            earliest = 0
            changed_ids = tuple(step.step_id for step in new_steps)
            edit_ids: tuple[str, ...] = tuple()
        else:
            new_steps, earliest, changed_ids, edit_ids = self._apply_edits(
                plan.steps, report.edits
            )
        if not new_steps:
            raise ContractValidationError("A patch cannot delete every plan step")
        final_ids = [step.step_id for step in new_steps]
        if len(final_ids) != len(set(final_ids)):
            raise ContractValidationError("Patched plan contains duplicate step IDs")
        revised = Plan(
            task=plan.task,
            steps=new_steps,
            version=plan.version + 1,
            source="evaluation_chain",
            parent_plan_id=plan.plan_id,
            metadata={
                **dict(plan.metadata),
                "evaluation_summary": report.summary,
                "previous_plan_id": plan.plan_id,
                "previous_plan_version": plan.version,
            },
        )
        return PatchApplication(
            original_plan=plan,
            revised_plan=revised,
            earliest_changed_index=earliest,
            changed_step_ids=changed_ids,
            applied_edit_ids=edit_ids,
        )

    def _apply_edits(
        self, original_steps: Sequence[PlanStep], edits: Sequence[PlanEdit]
    ) -> tuple[List[PlanStep], int, tuple[str, ...], tuple[str, ...]]:
        index_by_id = {step.step_id: index for index, step in enumerate(original_steps)}
        before: Dict[str, List[PlanStep]] = {}
        after: Dict[str, List[PlanStep]] = {}
        terminal: Dict[str, PlanEdit] = {}
        earliest = len(original_steps)
        changed_ids: List[str] = []
        applied_ids: List[str] = []

        edit_ids = [edit.edit_id for edit in edits]
        if len(edit_ids) != len(set(edit_ids)):
            raise ContractValidationError("Evaluation report contains duplicate edit IDs")

        for edit in edits:
            if edit.target_step_id not in index_by_id:
                raise ContractValidationError(
                    f"Unknown edit target_step_id {edit.target_step_id!r}"
                )
            target_index = index_by_id[edit.target_step_id]
            earliest = min(earliest, target_index)
            if edit.operation == "insert_before":
                before.setdefault(edit.target_step_id, []).extend(edit.steps)
            elif edit.operation == "insert_after":
                after.setdefault(edit.target_step_id, []).extend(edit.steps)
            else:
                if edit.target_step_id in terminal:
                    raise ContractValidationError(
                        f"Conflicting terminal edits for {edit.target_step_id!r}"
                    )
                terminal[edit.target_step_id] = edit
            changed_ids.append(edit.target_step_id)
            changed_ids.extend(step.step_id for step in edit.steps)
            applied_ids.append(edit.edit_id)

        output: List[PlanStep] = []
        for step in original_steps:
            output.extend(before.get(step.step_id, []))
            terminal_edit = terminal.get(step.step_id)
            if terminal_edit is None:
                output.append(step)
            elif terminal_edit.operation == "replace":
                output.extend(terminal_edit.steps)
            elif terminal_edit.operation != "delete":
                raise ContractValidationError(
                    f"Unexpected terminal operation {terminal_edit.operation!r}"
                )
            output.extend(after.get(step.step_id, []))
        if earliest == len(original_steps):
            raise ContractValidationError("No edits were supplied")
        return output, earliest, tuple(changed_ids), tuple(applied_ids)
