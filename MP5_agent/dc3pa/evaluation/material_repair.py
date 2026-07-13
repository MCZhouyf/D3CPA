from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

from ..contracts import Action, AgentState, Plan, PlanStep, normalize_item_name
from ..reliability.projection import (
    apply_action_effect,
    is_inventory_resource,
    normalized_inventory,
)


@dataclass(frozen=True)
class CraftRecipe:
    output: str
    quantity: float
    materials: Mapping[str, float]
    platform: Optional[str] = None


_CRAFT_RECIPES: Dict[str, CraftRecipe] = {
    "planks": CraftRecipe(
        output="planks",
        quantity=4.0,
        materials={"log": 1.0},
    ),
    "stick": CraftRecipe(
        output="stick",
        quantity=4.0,
        materials={"planks": 2.0},
    ),
    "crafting table": CraftRecipe(
        output="crafting table",
        quantity=1.0,
        materials={"planks": 4.0},
    ),
    "wooden pickaxe": CraftRecipe(
        output="wooden pickaxe",
        quantity=1.0,
        materials={"planks": 3.0, "stick": 2.0},
        platform="crafting table",
    ),
}

_MINEABLE_WITH_HAND = {"log"}
_GATHER_ACTIONS = {"find", "move_to", "mine"}


@dataclass(frozen=True)
class MaterialRepairResult:
    plan: Plan
    inserted_step_count: int
    inserted_targets: tuple[str, ...]


def _quantity(value: object) -> float:
    return float(value)


def _available(inventory: Mapping[str, float], item: str) -> float:
    return float(inventory.get(normalize_item_name(item), 0.0))


def _add_need(needs: MutableMapping[str, float], item: object, quantity: float) -> None:
    name = normalize_item_name(item)
    if not name or not is_inventory_resource(name):
        return
    needs[name] = max(float(needs.get(name, 0.0)), float(quantity))


def _action_requirements(action: Action, repetitions: int) -> Dict[str, float]:
    repetitions = max(1, int(repetitions))
    needs: Dict[str, float] = {}
    if action.name == "craft":
        for material, quantity in action.args["materials"].items():
            _add_need(needs, material, _quantity(quantity) * repetitions)
        _add_need(needs, action.args.get("platform"), 1.0)
    elif action.name in {"mine", "fight", "dig_down", "dig_up", "apply"}:
        _add_need(needs, action.args.get("tool"), 1.0)
    elif action.name == "equip":
        _add_need(needs, action.args.get("obj"), 1.0)
    return needs


def _action_material_requirements(action: Action, repetitions: int) -> Dict[str, float]:
    repetitions = max(1, int(repetitions))
    needs: Dict[str, float] = {}
    if action.name == "craft":
        for material, quantity in action.args["materials"].items():
            _add_need(needs, material, _quantity(quantity) * repetitions)
    return needs


def _action_outputs(action: Action, repetitions: int) -> Dict[str, float]:
    repetitions = max(1, int(repetitions))
    outputs: Dict[str, float] = {}
    if action.name == "craft":
        for output, quantity in action.args["obj"].items():
            _add_need(outputs, output, _quantity(quantity) * repetitions)
    elif action.name == "mine":
        _add_need(outputs, action.args.get("obj"), float(repetitions))
    return outputs


def _recipe_requirement_for_source(
    target: str,
    quantity: float,
    source: str,
    stack: tuple[str, ...] = (),
) -> float:
    target = normalize_item_name(target)
    source = normalize_item_name(source)
    if target == source:
        return float(quantity)
    if target in stack:
        return 0.0
    recipe = _CRAFT_RECIPES.get(target)
    if recipe is None:
        return 0.0
    times = max(1, int(math.ceil(float(quantity) / recipe.quantity)))
    return sum(
        _recipe_requirement_for_source(
            material,
            float(material_quantity) * times,
            source,
            (*stack, target),
        )
        for material, material_quantity in recipe.materials.items()
    )


def _expanded_material_requirement(
    action: Action,
    repetitions: int,
    source: str,
) -> float:
    repetitions = max(1, int(repetitions))
    if action.name != "craft":
        return 0.0
    return sum(
        _recipe_requirement_for_source(
            material,
            float(quantity) * repetitions,
            source,
        )
        for material, quantity in action.args["materials"].items()
    )


def _suffix_material_requirement(
    steps: Sequence[PlanStep],
    step_index: int,
    action_index: int,
    item: str,
) -> float:
    """Return how much consumable material is needed before the suffix starts."""

    item = normalize_item_name(item)
    required_now = 0.0
    surplus = 0.0
    for later_step_index in range(step_index, len(steps)):
        step = steps[later_step_index]
        start_action = action_index if later_step_index == step_index else 0
        for action in step.actions[start_action:]:
            needed = _action_material_requirements(action, step.times).get(item, 0.0)
            if item not in _MINEABLE_WITH_HAND:
                needed = max(
                    needed,
                    _expanded_material_requirement(action, step.times, item),
                )
            if needed > surplus:
                required_now += needed - surplus
                surplus = needed
            surplus -= needed
            surplus += _action_outputs(action, step.times).get(item, 0.0)
    return required_now


def _mine_step(item: str, quantity: float) -> PlanStep:
    count = max(1, int(math.ceil(quantity)))
    return PlanStep(
        actions=[
            Action("find", {"obj": item}),
            Action("move_to", {"obj": item}),
            Action("mine", {"obj": item, "tool": None}),
        ],
        times=count,
        metadata={"dc3pa_auto_material_repair": True, "target": item},
    )


def _craft_step(recipe: CraftRecipe, times: int) -> PlanStep:
    return PlanStep(
        actions=[
            Action(
                "craft",
                {
                    "obj": {recipe.output: recipe.quantity},
                    "materials": dict(recipe.materials),
                    "platform": recipe.platform,
                },
            )
        ],
        times=max(1, int(times)),
        metadata={"dc3pa_auto_material_repair": True, "target": recipe.output},
    )


def _apply_steps(inventory: MutableMapping[str, float], steps: Iterable[PlanStep]) -> None:
    for step in steps:
        for action in step.actions:
            apply_action_effect(inventory, action, repetitions=step.times)


def _direct_gather_target(step: PlanStep) -> Optional[str]:
    target = None
    for action in step.actions:
        if action.name not in _GATHER_ACTIONS:
            return None
        action_target = normalize_item_name(action.args.get("obj"))
        if not action_target:
            return None
        if target is None:
            target = action_target
        elif target != action_target:
            return None
    return target


def _is_invalid_direct_gather_step(step: PlanStep) -> bool:
    target = _direct_gather_target(step)
    return bool(target and target in _CRAFT_RECIPES and target not in _MINEABLE_WITH_HAND)


def _producer_steps(
    item: str,
    required_total: float,
    inventory: MutableMapping[str, float],
    stack: tuple[str, ...] = (),
) -> list[PlanStep]:
    item = normalize_item_name(item)
    missing = required_total - _available(inventory, item)
    if missing <= 0:
        return []
    if item in stack:
        return []

    if item in _MINEABLE_WITH_HAND:
        step = _mine_step(item, missing)
        _apply_steps(inventory, [step])
        return [step]

    recipe = _CRAFT_RECIPES.get(item)
    if recipe is None:
        return []

    times = max(1, int(math.ceil(missing / recipe.quantity)))
    steps: list[PlanStep] = []
    for material, quantity in recipe.materials.items():
        material_required = _available(inventory, material) + float(quantity) * times
        produced = _producer_steps(
            material,
            material_required,
            inventory,
            stack=(*stack, item),
        )
        steps.extend(produced)
    if recipe.platform:
        produced = _producer_steps(
            recipe.platform,
            1.0,
            inventory,
            stack=(*stack, item),
        )
        steps.extend(produced)

    if all(_available(inventory, material) >= float(quantity) * times for material, quantity in recipe.materials.items()) and (
        not recipe.platform or _available(inventory, recipe.platform) >= 1.0
    ):
        step = _craft_step(recipe, times)
        _apply_steps(inventory, [step])
        steps.append(step)
    return steps


def repair_material_deficits(plan: Plan, state: AgentState) -> MaterialRepairResult:
    """Insert known prerequisite producers before steps with explicit deficits.

    This is intentionally limited to generic item dependencies, not task-name-specific
    workflows. Unknown deficits remain unresolved for the normal reliability gate.
    """

    inventory = normalized_inventory(state.inventory)
    revised_steps: list[PlanStep] = []
    inserted_targets: list[str] = []

    for step_index, step in enumerate(plan.steps):
        if _is_invalid_direct_gather_step(step):
            inserted_targets.append(f"removed invalid direct gather:{_direct_gather_target(step)}")
            continue
        prerequisite_steps: list[PlanStep] = []
        for action_index, action in enumerate(step.actions):
            requirements = _action_requirements(action, step.times)
            for _ in range(8):
                material_requirements = _action_material_requirements(action, step.times)
                deficits = []
                for item, required in requirements.items():
                    required_total = required
                    if item in material_requirements:
                        required_total = max(
                            required,
                            _suffix_material_requirement(
                                plan.steps,
                                step_index,
                                action_index,
                                item,
                            ),
                        )
                    if _available(inventory, item) < required_total:
                        deficits.append((item, required_total))
                if not deficits:
                    break
                produced_any = False
                for item, required in deficits:
                    produced = _producer_steps(item, required, inventory)
                    if not produced:
                        continue
                    produced_any = True
                    prerequisite_steps.extend(produced)
                    inserted_targets.extend(
                        normalize_item_name(inserted.metadata.get("target", ""))
                        for inserted in produced
                    )
                if not produced_any:
                    break
        revised_steps.extend(prerequisite_steps)
        revised_steps.append(step)
        for action in step.actions:
            apply_action_effect(inventory, action, repetitions=step.times)

    if not inserted_targets:
        return MaterialRepairResult(plan=plan, inserted_step_count=0, inserted_targets=())

    repaired = Plan(
        task=plan.task,
        steps=revised_steps,
        version=plan.version + 1,
        source="dc3pa_material_repair",
        parent_plan_id=plan.plan_id,
        metadata={
            **dict(plan.metadata),
            "material_repair_inserted_targets": tuple(inserted_targets),
            "previous_plan_id": plan.plan_id,
            "previous_plan_version": plan.version,
        },
    )
    return MaterialRepairResult(
        plan=repaired,
        inserted_step_count=len(inserted_targets),
        inserted_targets=tuple(inserted_targets),
    )
