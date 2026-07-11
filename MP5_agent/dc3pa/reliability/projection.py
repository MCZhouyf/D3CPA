from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, MutableMapping

from ..contracts import Action, AgentState, Plan, normalize_item_name

NON_INVENTORY_RESOURCES = {"", "none", "null", "hand", "bare hand", "air"}


def is_inventory_resource(value: object) -> bool:
    return normalize_item_name(value) not in NON_INVENTORY_RESOURCES


def _quantity(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Inventory quantity {value!r} is not numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"Inventory quantity {value!r} must be finite")
    return number


@dataclass(frozen=True)
class InventoryProjection:
    before_steps: tuple[Dict[str, float], ...]
    after_plan: Dict[str, float]

    def before(self, step_index: int) -> Dict[str, float]:
        return dict(self.before_steps[step_index])


def normalized_inventory(inventory: Mapping[str, float]) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for item, raw_quantity in inventory.items():
        item_name = normalize_item_name(item)
        if not item_name:
            continue
        result[item_name] = result.get(item_name, 0.0) + _quantity(raw_quantity)
    return result


def apply_action_effect(
    inventory: MutableMapping[str, float], action: Action, repetitions: int = 1
) -> None:
    """Apply optimistic declared effects for plan-prefix feasibility checks.

    The projection assumes preceding actions succeed. It is not an execution model; it
    only prevents future steps from being marked infeasible when their prerequisites are
    explicitly produced earlier in the same candidate plan.
    """

    repetitions = max(1, int(repetitions))
    if action.name == "craft":
        for material, quantity in action.args["materials"].items():
            name = normalize_item_name(material)
            inventory[name] = inventory.get(name, 0.0) - _quantity(quantity) * repetitions
        for output, quantity in action.args["obj"].items():
            name = normalize_item_name(output)
            inventory[name] = inventory.get(name, 0.0) + _quantity(quantity) * repetitions
    elif action.name == "mine":
        target = normalize_item_name(action.args.get("obj"))
        if target:
            inventory[target] = inventory.get(target, 0.0) + float(repetitions)


def project_inventory(plan: Plan, state: AgentState) -> InventoryProjection:
    inventory = normalized_inventory(state.inventory)
    snapshots = []
    for step in plan.steps:
        snapshots.append(dict(inventory))
        for action in step.actions:
            apply_action_effect(inventory, action, repetitions=step.times)
    return InventoryProjection(tuple(snapshots), dict(inventory))
