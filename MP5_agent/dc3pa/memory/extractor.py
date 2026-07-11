from __future__ import annotations

from typing import Iterable, List

from ..contracts import Action, Plan, normalize_item_name
from .dependency_store import DependencyEdge


class DependencyExtractor:
    """Extract only explicit prerequisite relations from successful workflows.

    It deliberately avoids treating every previous step as a causal dependency. That
    conservative choice reduces false graph edges during Stage 2.
    """

    def extract(self, plan: Plan) -> List[DependencyEdge]:
        edges: List[DependencyEdge] = []
        for step in plan.steps:
            for action in step.actions:
                edges.extend(self._from_action(action, step.times))
        deduplicated = {}
        for edge in edges:
            key = (edge.prerequisite, edge.target, edge.relation_type)
            previous = deduplicated.get(key)
            if previous is None or edge.quantity > previous.quantity:
                deduplicated[key] = edge
        return list(deduplicated.values())

    def _from_action(self, action: Action, times: int) -> Iterable[DependencyEdge]:
        if action.name == "craft":
            output_name, output_quantity = next(iter(action.args["obj"].items()))
            target = normalize_item_name(output_name)
            for material, quantity in action.args["materials"].items():
                yield DependencyEdge(
                    prerequisite=normalize_item_name(material),
                    target=target,
                    relation_type="material",
                    quantity=float(quantity),
                )
            platform = normalize_item_name(action.args.get("platform"))
            if platform:
                yield DependencyEdge(
                    prerequisite=platform,
                    target=target,
                    relation_type="platform",
                    quantity=1.0,
                )
        elif action.name == "mine":
            target = normalize_item_name(action.args.get("obj"))
            tool = normalize_item_name(action.args.get("tool"))
            if tool:
                yield DependencyEdge(
                    prerequisite=tool,
                    target=target,
                    relation_type="tool",
                    quantity=1.0,
                )
        elif action.name in {"fight", "dig_down", "dig_up", "apply"}:
            tool = normalize_item_name(action.args.get("tool"))
            if tool:
                target = f"action {action.name.replace('_', ' ')}"
                yield DependencyEdge(
                    prerequisite=tool,
                    target=target,
                    relation_type="tool",
                    quantity=1.0,
                )
