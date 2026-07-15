"""Round 2 knowledge evidence: hard constraints, graded coverage, and shadow mode.

This module is intentionally additive.  The legacy strategy remains untouched and is
selected by default until the factory/config integration is completed and validated.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol

from ..contracts import Action, AgentState, Plan, normalize_item_name
from ..memory.dependency_store import DependencyEdge
from .contracts import DimensionScore, ReliabilityContext
from .contracts import FusionEvidence
from .hybrid import HybridProbabilityModel
from .knowledge import KnowledgeReliabilityStrategy, PrerequisiteCheck
from .projection import (
    NON_INVENTORY_RESOURCES,
    apply_action_effect,
    normalized_inventory,
    project_inventory,
)


KNOWLEDGE_IMPLS = frozenset({"legacy_v1", "shadow_v2", "hard_gate_v2"})


class DependencyReader(Protocol):
    def prerequisites_for(self, target: str) -> List[DependencyEdge]:
        ...


def validate_knowledge_impl(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in KNOWLEDGE_IMPLS:
        raise ValueError(
            f"knowledge_impl must be one of {sorted(KNOWLEDGE_IMPLS)}, got {value!r}"
        )
    return normalized


def _target_for_action(action: Action) -> Optional[str]:
    if action.name == "craft":
        return normalize_item_name(next(iter(action.args["obj"])))
    if action.name == "mine":
        return normalize_item_name(action.args.get("obj"))
    if action.name in {"fight", "dig_down", "dig_up", "apply"}:
        return f"action {action.name.replace('_', ' ')}"
    return None


def _explicit_requirements(
    action: Action, repetitions: int
) -> Iterable[tuple[object, str, float]]:
    repetitions = max(1, int(repetitions))
    if action.name == "craft":
        for material, quantity in action.args["materials"].items():
            yield material, "material", float(quantity) * repetitions
        yield action.args.get("platform"), "platform", 1.0
    elif action.name in {"mine", "fight", "dig_down", "dig_up", "apply"}:
        yield action.args.get("tool"), "tool", 1.0


def _merge_requirement(
    requirements: Dict[tuple[str, str], Dict[str, Any]],
    item: object,
    relation_type: str,
    quantity: float,
    source: str,
) -> None:
    item_name = normalize_item_name(item)
    if item_name in NON_INVENTORY_RESOURCES:
        return
    key = (item_name, relation_type)
    current = requirements.setdefault(
        key,
        {
            "item": item_name,
            "relation_type": relation_type,
            "required": 0.0,
            "sources": [],
        },
    )
    current["required"] = max(float(current["required"]), float(quantity))
    if source not in current["sources"]:
        current["sources"].append(source)


def _dependency_support(source: str) -> Optional[int]:
    prefix = "dependency_graph:"
    if not source.startswith(prefix):
        return None
    try:
        value = int(source[len(prefix) :])
    except (TypeError, ValueError):
        return None
    return max(0, value)


def _is_hard_check(check: PrerequisiteCheck, graph_hard_min_support: int) -> bool:
    for source in check.sources:
        if source == "action_schema":
            return True
        support = _dependency_support(source)
        if support is not None and support >= graph_hard_min_support:
            return True
    return False


@dataclass(frozen=True)
class KnowledgeEvidenceV2:
    """Structured evidence used by the graded knowledge strategy.

    ``hard_feasible`` is ``None`` only when no knowledge is available.  When
    knowledge exists but there are no hard requirements, it is vacuously ``True``.
    """

    available: bool
    hard_feasible: Optional[bool]
    coverage: Optional[float]
    checks: tuple[PrerequisiteCheck, ...] = ()
    missing_hard: tuple[PrerequisiteCheck, ...] = ()
    missing_soft: tuple[PrerequisiteCheck, ...] = ()
    projected_inventory: Mapping[str, float] = None  # type: ignore[assignment]
    actions: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.projected_inventory is None:
            object.__setattr__(self, "projected_inventory", {})
        if self.available:
            if self.hard_feasible is None or self.coverage is None:
                raise ValueError(
                    "available knowledge evidence requires hard_feasible and coverage"
                )
            if not 0.0 <= float(self.coverage) <= 1.0:
                raise ValueError("knowledge coverage must be in [0, 1]")
        else:
            if self.hard_feasible is not None or self.coverage is not None:
                raise ValueError(
                    "unavailable knowledge evidence must use None feasibility/coverage"
                )
            if self.checks or self.missing_hard or self.missing_soft:
                raise ValueError("unavailable evidence cannot contain prerequisite checks")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "hard_feasible": self.hard_feasible,
            "coverage": self.coverage,
            "checks": [item.to_dict() for item in self.checks],
            "missing_hard": [item.to_dict() for item in self.missing_hard],
            "missing_soft": [item.to_dict() for item in self.missing_soft],
            "projected_inventory": dict(sorted(self.projected_inventory.items())),
            "actions": [dict(item) for item in self.actions],
        }


class KnowledgeReliabilityStrategyV2:
    """Prerequisite reliability with hard constraints and equal-weight coverage."""

    def __init__(
        self,
        dependencies: Optional[DependencyReader] = None,
        *,
        graph_hard_min_support: int = 2,
    ):
        if (
            isinstance(graph_hard_min_support, bool)
            or not isinstance(graph_hard_min_support, int)
            or graph_hard_min_support <= 0
        ):
            raise ValueError("graph_hard_min_support must be a positive integer")
        self.dependencies = dependencies
        self.graph_hard_min_support = graph_hard_min_support

    def evidence(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> KnowledgeEvidenceV2:
        del context  # reserved for future context-conditioned rules
        if not 0 <= step_index < len(plan.steps):
            raise IndexError(f"step_index {step_index} out of range")

        projection = project_inventory(plan, state)
        inventory = normalized_inventory(projection.before(step_index))
        step = plan.steps[step_index]
        all_checks: List[PrerequisiteCheck] = []
        action_evidence: List[Mapping[str, Any]] = []

        for action_position, action in enumerate(step.actions):
            requirements: Dict[tuple[str, str], Dict[str, Any]] = {}
            for item, relation_type, quantity in _explicit_requirements(
                action, step.times
            ):
                _merge_requirement(
                    requirements,
                    item,
                    relation_type,
                    quantity,
                    source="action_schema",
                )

            target = _target_for_action(action)
            if target and self.dependencies is not None:
                for edge in self.dependencies.prerequisites_for(target):
                    _merge_requirement(
                        requirements,
                        edge.prerequisite,
                        edge.relation_type,
                        edge.quantity,
                        source=f"dependency_graph:{edge.success_count}",
                    )

            action_checks = [
                PrerequisiteCheck(
                    item=record["item"],
                    relation_type=record["relation_type"],
                    required=float(record["required"]),
                    available=float(inventory.get(record["item"], 0.0)),
                    sources=tuple(record["sources"]),
                )
                for record in requirements.values()
            ]
            action_checks.sort(key=lambda item: (item.relation_type, item.item))
            all_checks.extend(action_checks)
            action_evidence.append(
                {
                    "action_position": action_position,
                    "action": action.to_dict(),
                    "target": target,
                    "inventory_before": dict(sorted(inventory.items())),
                    "checks": [check.to_dict() for check in action_checks],
                }
            )
            apply_action_effect(inventory, action, repetitions=step.times)

        if not all_checks:
            return KnowledgeEvidenceV2(
                available=False,
                hard_feasible=None,
                coverage=None,
                projected_inventory=projection.before(step_index),
                actions=tuple(action_evidence),
            )

        missing_hard: List[PrerequisiteCheck] = []
        missing_soft: List[PrerequisiteCheck] = []
        satisfied_count = 0
        for check in all_checks:
            if check.satisfied:
                satisfied_count += 1
                continue
            if _is_hard_check(check, self.graph_hard_min_support):
                missing_hard.append(check)
            else:
                missing_soft.append(check)

        coverage = satisfied_count / len(all_checks)
        return KnowledgeEvidenceV2(
            available=True,
            hard_feasible=not missing_hard,
            coverage=float(coverage),
            checks=tuple(all_checks),
            missing_hard=tuple(missing_hard),
            missing_soft=tuple(missing_soft),
            projected_inventory=projection.before(step_index),
            actions=tuple(action_evidence),
        )

    def score(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> DimensionScore:
        evidence = self.evidence(plan, step_index, state, context)
        step = plan.steps[step_index]
        if not evidence.available:
            return DimensionScore.unavailable(
                "knowledge",
                "No explicit or learned prerequisite was available for this step",
                evidence={
                    "step_id": step.step_id,
                    "knowledge_v2": evidence.to_dict(),
                },
            )

        if evidence.missing_hard:
            reason = "Missing mandatory prerequisite(s)"
        elif evidence.missing_soft:
            reason = "Known soft prerequisite evidence is incomplete"
        else:
            reason = "All known prerequisites are satisfied"

        return DimensionScore(
            dimension="knowledge",
            probability=float(evidence.coverage),
            available=True,
            reason=reason,
            evidence={
                "step_id": step.step_id,
                "knowledge_v2": evidence.to_dict(),
                # Keep the legacy key for downstream evaluation prompts.
                "missing": [
                    item.to_dict()
                    for item in (*evidence.missing_hard, *evidence.missing_soft)
                ],
                "known_check_count": len(evidence.checks),
            },
            hard_conflict=bool(evidence.missing_hard),
        )


class KnowledgeShadowStrategy:
    """Return legacy V1 decisions while attaching V2 evidence for comparison."""

    def __init__(
        self,
        legacy: KnowledgeReliabilityStrategy,
        candidate: KnowledgeReliabilityStrategyV2,
        *,
        fail_open: bool = False,
    ):
        self.legacy = legacy
        self.candidate = candidate
        self.fail_open = bool(fail_open)

    def score(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> DimensionScore:
        legacy_score = self.legacy.score(plan, step_index, state, context)
        evidence = dict(legacy_score.evidence)
        try:
            candidate_score = self.candidate.score(plan, step_index, state, context)
            evidence["shadow_v2"] = candidate_score.to_dict()
        except Exception as exc:
            if not self.fail_open:
                raise
            evidence["shadow_v2_error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
        return DimensionScore(
            dimension=legacy_score.dimension,
            probability=legacy_score.probability,
            available=legacy_score.available,
            reason=legacy_score.reason,
            evidence=evidence,
            hard_conflict=legacy_score.hard_conflict,
        )


class HardGatedHybridProbabilityModel(HybridProbabilityModel):
    """V2 hybrid wrapper that makes a hard prerequisite violation non-averagable."""

    def score_step(self, *args: Any, **kwargs: Any):
        result = super().score_step(*args, **kwargs)
        if not result.hard_conflict:
            return result
        notes = tuple(result.notes) + (
            "Overall reliability forced to zero by the knowledge hard gate",
        )
        fusion = result.fusion
        if fusion is not None:
            fusion = replace(
                fusion,
                probability=0.0,
                hard_gate_applied=True,
                reason="Overall reliability forced to zero by the knowledge hard gate",
            )
        else:
            fusion = FusionEvidence(
                method="memory_weighted_v1",
                probability=0.0,
                hard_gate_applied=True,
                reason="Overall reliability forced to zero by the knowledge hard gate",
            )
        return replace(result, probability=0.0, fusion=fusion, notes=notes)
