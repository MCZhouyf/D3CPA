from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from .contracts import EvaluationReport, EvaluationRequest

_CODE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.IGNORECASE | re.DOTALL)


@runtime_checkable
class EvaluationProvider(Protocol):
    def complete(self, prompt: str) -> Any:
        ...


@runtime_checkable
class PlanEvaluationChain(Protocol):
    def evaluate(self, request: EvaluationRequest) -> EvaluationReport:
        ...


@dataclass
class CallableEvaluationProvider:
    function: Callable[[str], Any]

    def complete(self, prompt: str) -> Any:
        return self.function(prompt)


def build_evaluation_prompt(request: EvaluationRequest) -> str:
    schema = {
        "plan_id": request.plan.plan_id,
        "plan_version": request.plan.version,
        "summary": "concise diagnosis",
        "issues": [
            {
                "step_id": "existing step id",
                "dimension": "knowledge|model|environment|mixed",
                "severity": "info|warning|error|critical",
                "diagnosis": "concise reason",
                "evidence": {},
            }
        ],
        "edits": [
            {
                "operation": "insert_before|insert_after|replace|delete",
                "target_step_id": "existing step id",
                "steps": [
                    {
                        "times": 1,
                        "actions": [{"name": "find", "args": {"obj": "example"}}],
                        "expected_outputs": {},
                        "metadata": {},
                    }
                ],
                "rationale": "concise reason",
            }
        ],
        "replacement_steps": [],
        "accepted": False,
        "request_replan": False,
    }
    return (
        "You are the DC3PA Evaluation Chain. Inspect only the supplied plan, state, "
        "and reliability evidence. Return JSON only. Do not reveal hidden chain-of-thought; "
        "give short, auditable diagnoses. Use existing target_step_id values. Use either "
        "incremental edits, a full replacement_steps list, accepted=true, or "
        "request_replan=true. Select exactly one outcome and never mix alternatives. "
        "Allowed action names are exactly: find, move_to, mine, craft, fight, equip, "
        "dig_down, dig_up, apply. Do not invent actions such as look, search, walk, "
        "or collect. "
        "Use accepted=true only when detailed evaluation confirms no correction is needed. "
        "Preserve valid steps and make the smallest sufficient fix.\n"
        "OUTPUT SCHEMA:\n"
        + json.dumps(schema, sort_keys=True, ensure_ascii=False)
        + "\nINPUT:\n"
        + json.dumps(
            request.to_prompt_payload(), sort_keys=True, ensure_ascii=False, default=str
        )
    )


def parse_evaluation_payload(raw: Any) -> Mapping[str, Any]:
    if isinstance(raw, Mapping):
        return raw
    if not isinstance(raw, str):
        raise TypeError("Evaluation provider must return a mapping or JSON string")
    text = raw.strip()
    match = _CODE_FENCE.match(text)
    if match:
        text = match.group(1)
    parsed = json.loads(text)
    if not isinstance(parsed, Mapping):
        raise TypeError("Evaluation JSON must be an object")
    return parsed


class StructuredEvaluationChain:
    def __init__(self, provider: EvaluationProvider, failure_mode: str = "raise"):
        if failure_mode not in {"raise", "request_replan"}:
            raise ValueError("failure_mode must be 'raise' or 'request_replan'")
        self.provider = provider
        self.failure_mode = failure_mode

    def evaluate(self, request: EvaluationRequest) -> EvaluationReport:
        prompt = build_evaluation_prompt(request)
        try:
            raw = self.provider.complete(prompt)
            payload = parse_evaluation_payload(raw)
            report = EvaluationReport.from_dict(payload, expected_plan=request.plan)
            metadata = dict(report.provider_metadata)
            metadata.setdefault("provider_type", type(self.provider).__name__)
            return EvaluationReport(
                plan_id=report.plan_id,
                plan_version=report.plan_version,
                summary=report.summary,
                issues=report.issues,
                edits=report.edits,
                replacement_steps=report.replacement_steps,
                accepted=report.accepted,
                request_replan=report.request_replan,
                provider_metadata=metadata,
            )
        except Exception as exc:
            if self.failure_mode == "raise":
                raise
            return EvaluationReport.unresolved(
                request.plan,
                f"Evaluation provider failed: {type(exc).__name__}: {exc}",
            )
