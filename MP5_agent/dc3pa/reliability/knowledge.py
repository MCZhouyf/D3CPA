from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol

from ..contracts import Action, AgentState, Plan, normalize_item_name
from ..memory.dependency_store import DependencyEdge
from .contracts import DimensionScore, ReliabilityContext
from .projection import (
    NON_INVENTORY_RESOURCES,
    apply_action_effect,
    normalized_inventory,
    project_inventory,
)


class DependencyReader(Protocol):
    def prerequisites_for(self, target: str) -> List[DependencyEdge]:
        ...


@dataclass(frozen=True)
class PrerequisiteCheck:
    item: str
    relation_type: str
    required: float
    available: float
    sources: tuple[str, ...]

    @property
    def satisfied(self) -> bool:
        return self.available >= self.required

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item": self.item,
            "relation_type": self.relation_type,
            "required": self.required,
            "available": self.available,
            "satisfied": self.satisfied,
            "sources": list(self.sources),
        }


def _target_for_action(action: Action) -> Optional[str]:
    if action.name == "craft":
        return normalize_item_name(next(iter(action.args["obj"])))
    if action.name == "mine":
        return normalize_item_name(action.args.get("obj"))
    if action.name in {"fight", "dig_down", "dig_up", "apply"}:
        return f"action {action.name.replace('_', ' ')}"
    return None


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


def _explicit_requirements(action: Action, repetitions: int) -> Iterable[tuple[object, str, float]]:
    repetitions = max(1, int(repetitions))
    if action.name == "craft":
        for material, quantity in action.args["materials"].items():
            yield material, "material", float(quantity) * repetitions
        yield action.args.get("platform"), "platform", 1.0
    elif action.name in {"mine", "fight", "dig_down", "dig_up", "apply"}:
        yield action.args.get("tool"), "tool", 1.0


class KnowledgeReliabilityStrategy:
    """Binary prerequisite feasibility from explicit actions and learned graph edges."""

    def __init__(self, dependencies: Optional[DependencyReader] = None):
        self.dependencies = dependencies

    def score(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> DimensionScore:
        if not 0 <= step_index < len(plan.steps):
            raise IndexError(f"step_index {step_index} out of range")
        projection = project_inventory(plan, state)
        inventory = normalized_inventory(projection.before(step_index))
        step = plan.steps[step_index]
        all_checks: List[PrerequisiteCheck] = []
        action_evidence: List[Dict[str, Any]] = []

        for action_position, action in enumerate(step.actions):
            requirements: Dict[tuple[str, str], Dict[str, Any]] = {}
            for item, relation_type, quantity in _explicit_requirements(action, step.times):
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
            return DimensionScore.unavailable(
                "knowledge",
                "No explicit or learned prerequisite was available for this step",
                evidence={
                    "step_id": step.step_id,
                    "actions": action_evidence,
                    "projected_inventory": projection.before(step_index),
                },
            )

        missing = [check for check in all_checks if not check.satisfied]
        probability = 0.0 if missing else 1.0
        return DimensionScore(
            dimension="knowledge",
            probability=probability,
            available=True,
            reason=(
                "Missing prerequisite(s)"
                if missing
                else "All known prerequisites are satisfied"
            ),
            evidence={
                "step_id": step.step_id,
                "actions": action_evidence,
                "missing": [check.to_dict() for check in missing],
                "known_check_count": len(all_checks),
            },
            hard_conflict=bool(missing),
        )
