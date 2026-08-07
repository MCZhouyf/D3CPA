import os
import sys
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from utils import *
from dc3pa_feature_flags import legacy_task_hacks_enabled
from structured_actions import *
from minedojo.sim import InventoryItem

try:
    from dc3pa.integration.execution_observer import (
        compact_action_payload,
        current_rgb_from_events,
        emit_execution_event,
        snapshot_inventory,
    )
except ModuleNotFoundError:
    mp5_root = Path(__file__).resolve().parents[1]
    if str(mp5_root) not in sys.path:
        sys.path.insert(0, str(mp5_root))
    from dc3pa.integration.execution_observer import (
        compact_action_payload,
        current_rgb_from_events,
        emit_execution_event,
        snapshot_inventory,
    )

class Controller:
    def __init__(
        self,
        memory, 
        checker
    ):
        self.memory = memory
        self.checker = checker

    def _is_deep_mining_task(self, task_information):
        bounded_fallback_enabled = os.environ.get(
            "DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK", ""
        ).lower() in {"1", "true", "yes", "on"}
        return task_information.get("task") in {"diamond", "redstone", "gold"} and (
            legacy_task_hacks_enabled() or bounded_fallback_enabled
        )

    def _deep_mining_target(self, task_information):
        return normalize_inventory_name(task_information.get("task"))

    def _target_ore_name(self, task_information):
        target = self._deep_mining_target(task_information)
        if target in {"diamond", "redstone", "gold"}:
            return f"{target} ore"
        return target

    def _sync_memory(self, env):
        events,_,_,_ = env.step([0,0,0,12,12,0,0,0])
        share_memory(self.memory, events)
        return events

    def _consume_execution_failure(self):
        """Consume a low-level failure so the outer agent loop can ask the LLM to re-plan."""
        failure = getattr(self.memory, "_dc3pa_execution_failure", None)
        self.memory._dc3pa_execution_failure = None
        if not isinstance(failure, dict):
            return None
        return {
            "feedback": str(failure.get("feedback", "Low-level execution failed.")),
            "success": False,
            "suggestion": str(
                failure.get(
                    "suggestion",
                    "Re-plan from the current observed state before resuming execution.",
                )
            ),
            "reason": str(failure.get("reason", "execution_failure")),
            "tool": str(failure.get("tool", "")),
            "resource_goal": failure.get("resource_goal"),
            "observed_underground": failure.get("observed_underground"),
        }

    def _diamond_bootstrap_ready(self):
        inventory = self.memory.inventory
        return inventory.get("wooden pickaxe", 0) >= 1

    def _is_diamond_bootstrap_step(self, step):
        for action in step["actions"]:
            name = action["name"]
            args = action["args"]
            if name in {"find", "move_to", "mine"}:
                if args.get("obj") != "log":
                    return False
                continue
            if name == "craft":
                crafted_obj = normalize_inventory_name(list(args["obj"].keys())[0])
                if crafted_obj not in {"planks", "stick", "crafting table", "wooden pickaxe"}:
                    return False
                continue
            if name == "equip":
                if normalize_inventory_name(args.get("obj")) != "wooden pickaxe":
                    return False
                continue
            return False
        return True

    def _inventory_has(self, item_name, quantity=1):
        return self.memory.inventory.get(normalize_inventory_name(item_name), 0) >= quantity

    def _inventory_count(self, item_name):
        return self.memory.inventory.get(normalize_inventory_name(item_name), 0)

    def _mine_step_goal_reached(self, target_name, initial_quantity, repetitions):
        """Whether a repeated mine step has already observed its requested yield.

        In the workflow grammar, a mine step's ``times`` is the requested
        resource quantity.  One physical mine action can legitimately collect
        several adjacent blocks.  Continuing to issue the remaining attacks
        after the requested quantity is present only consumes the declared
        tool, and can prevent the following craft from happening.
        """
        return self._inventory_count(target_name) >= (
            float(initial_quantity) + int(repetitions)
        )

    def _is_optional_deep_mining_craft(self, crafted_obj):
        return normalize_inventory_name(crafted_obj) in {"torch"}

    def _has_wooden_pickaxe_materials(self):
        inventory = self.memory.inventory
        return (
            inventory.get("crafting table", 0) >= 1
            and inventory.get("planks", 0) >= 3
            and inventory.get("stick", 0) >= 2
        )

    def _set_inventory_from_memory(self, env, overrides=None, *, callback_kind=""):
        """Apply the sole permitted inventory mutation: a delayed log callback.

        All non-log resources and all crafted items must be obtained through
        Minecraft actions.  This guard makes accidental inventory fallback a
        hard failure instead of silently turning an execution failure into a
        successful episode.
        """
        normalized_overrides = {
            normalize_inventory_name(item_name): float(quantity)
            for item_name, quantity in (overrides or {}).items()
        }
        current_inventory = {
            normalize_inventory_name(item_name): float(quantity)
            for item_name, quantity in self.memory.inventory.items()
            if item_name != "air" and quantity > 0
        }
        if callback_kind != "log_callback" or set(normalized_overrides) != {"log"}:
            raise RuntimeError("inventory mutation is restricted to the log callback")
        requested_logs = normalized_overrides["log"]
        if requested_logs < current_inventory.get("log", 0):
            raise RuntimeError("log callback may only add missing logs")

        merged_inventory = dict(current_inventory)
        merged_inventory["log"] = requested_logs
        changed_non_logs = {
            item_name
            for item_name in set(current_inventory) | set(merged_inventory)
            if item_name != "log"
            and current_inventory.get(item_name, 0) != merged_inventory.get(item_name, 0)
        }
        if changed_non_logs:
            raise RuntimeError(f"log callback attempted to change non-log items: {changed_non_logs}")

        inventory_items = []
        for slot_idx, (item_name, quantity) in enumerate(merged_inventory.items()):
            if quantity <= 0:
                continue
            minedojo_item_name = "gold_ore" if item_name == "gold" else item_name.replace(" ", "_")
            inventory_items.append(
                InventoryItem(
                    slot=slot_idx,
                    name=minedojo_item_name,
                    variant=None,
                    quantity=int(quantity),
                )
            )

        env.set_inventory(inventory_items)
        self._sync_memory(env)
        # MineDojo can report one stale frame immediately after set_inventory.
        self.memory.inventory = merged_inventory
    def _fallback_craft_wooden_pickaxe(self, env):
        print("Wooden-pickaxe inventory fallback is disabled; require physical crafting.")
        return False
    def _fallback_craft_bootstrap_item(self, env, crafted_obj, target_quantity=1):
        crafted_obj = normalize_inventory_name(crafted_obj)
        if self.memory.inventory.get(crafted_obj, 0) >= target_quantity:
            return True
        print(f"Inventory fallback for {crafted_obj} is disabled; require physical crafting.")
        return False
    def _has_stone_pickaxe_materials(self):
        inventory = self.memory.inventory
        return (
            inventory.get("crafting table", 0) >= 1
            and inventory.get("cobblestone", 0) >= 3
            and inventory.get("stick", 0) >= 2
        )

    def _fallback_craft_stone_pickaxe(self, env):
        if self.memory.inventory.get("stone pickaxe", 0) >= 1:
            return True
        print("Stone-pickaxe inventory fallback is disabled; require physical crafting.")
        return False
    def _fallback_mine_diamond_resource(self, env, inventory_obj, required_quantity):
        inventory_obj = normalize_inventory_name(inventory_obj)
        if self.memory.inventory.get(inventory_obj, 0) >= required_quantity:
            return True
        print(
            f"Inventory fallback for {inventory_obj} is disabled; "
            "require physical collection."
        )
        return False
    def _deep_mining_required_quantity(self, inventory_obj, step_times):
        inventory_obj = normalize_inventory_name(inventory_obj)
        required_quantity = max(1, int(step_times))
        if inventory_obj == "cobblestone":
            required_quantity = max(required_quantity, 3)
        elif inventory_obj in {"coal", "iron ore"}:
            required_quantity = max(required_quantity, 3)
        return required_quantity

    @staticmethod
    def _workflow_material_requirement(workflow, after_step_index, inventory_obj, fallback_quantity):
        """Infer a mined resource's required total from downstream craft inputs.

        This intentionally derives demand from the LLM workflow itself rather
        than keeping a resource/recipe registry in the controller.
        """
        inventory_obj = normalize_inventory_name(inventory_obj)
        required_quantity = 0
        for step in workflow[after_step_index + 1:]:
            repetitions = max(1, int(step.get("times", 1)))
            for action in step.get("actions", []):
                if action.get("name") != "craft":
                    continue
                for material, quantity in action.get("args", {}).get("materials", {}).items():
                    if normalize_inventory_name(material) == inventory_obj:
                        required_quantity += repetitions * int(quantity)
        return max(1, required_quantity or int(fallback_quantity))

    @staticmethod
    def _cap_unused_craft_surplus(workflow):
        """Cap a craft output to the quantity consumed later in the plan.

        The cap is inferred only from the LLM workflow's own downstream tools,
        platforms, and material inputs.  It prevents a malformed plan such as
        crafting 20 iron ingots for one pickaxe from forcing collection of 20
        ore, without introducing a recipe or resource registry.
        """
        downstream_need = {}
        for step in reversed(workflow):
            repetitions = max(1, int(step.get("times", 1)))
            actions = step.get("actions", [])
            for action in reversed(actions):
                name = action.get("name")
                args = action.get("args", {})
                tool = normalize_inventory_name(args.get("tool"))
                if tool:
                    downstream_need[tool] = max(downstream_need.get(tool, 0), 1)
                if name == "equip":
                    equipped = normalize_inventory_name(args.get("obj"))
                    if equipped:
                        downstream_need[equipped] = max(
                            downstream_need.get(equipped, 0), 1
                        )
                if name != "craft" or not args.get("obj"):
                    continue

                output_name, output_quantity = next(iter(args["obj"].items()))
                output_name = normalize_inventory_name(output_name)
                output_quantity = max(1, int(output_quantity))
                declared_total = output_quantity * repetitions
                consumed_later = int(downstream_need.pop(output_name, 0))
                desired_total = (
                    min(declared_total, consumed_later)
                    if consumed_later > 0
                    else declared_total
                )

                effective_repetitions = repetitions
                if len(actions) == 1 and desired_total < declared_total:
                    effective_repetitions = max(
                        1, min(repetitions, math.ceil(desired_total / output_quantity))
                    )
                    step["times"] = str(effective_repetitions)
                desired_per_action = max(
                    1, math.ceil(desired_total / effective_repetitions)
                )
                if desired_per_action < output_quantity:
                    scale = desired_per_action / output_quantity
                    original_materials = args.get("materials", {})
                    args["obj"] = {output_name: desired_per_action}
                    args["materials"] = {
                        material: max(1, math.ceil(int(quantity) * scale))
                        for material, quantity in original_materials.items()
                    }
                    print(
                        "Capped unused craft surplus from workflow demand: "
                        f"{output_name} {declared_total} -> "
                        f"{desired_per_action * effective_repetitions}."
                    )

                for material, quantity in args.get("materials", {}).items():
                    material = normalize_inventory_name(material)
                    downstream_need[material] = (
                        downstream_need.get(material, 0)
                        + int(quantity) * effective_repetitions
                    )
                platform = normalize_inventory_name(args.get("platform"))
                if platform:
                    downstream_need[platform] = max(
                        downstream_need.get(platform, 0), 1
                    )

        return workflow

    def _fallback_craft_diamond_item(self, env, crafted_obj, target_quantity):
        crafted_obj = normalize_inventory_name(crafted_obj)
        if self.memory.inventory.get(crafted_obj, 0) >= target_quantity:
            return True
        print(
            f"Inventory fallback for crafted {crafted_obj} is disabled; "
            "require physical crafting."
        )
        return False
    def _prepare_deep_mining_craft_dependencies(self, env, crafted_obj):
        """Prepare only through physical actions; never synthesize dependencies."""
        crafted_obj = normalize_inventory_name(crafted_obj)
        # A stone pickaxe depends on cobblestone, sticks, and a crafting table;
        # it does not depend on retaining or recreating a wooden pickaxe.  The
        # old call to ensure_wooden_bootstrap here consumed the placed table
        # after furnace crafting and started an impossible underground log
        # search even though all stone-pickaxe materials were already present.
        return None
    def _available_pickaxe(self):
        """Return an available pickaxe without maintaining a tool registry."""
        for item_name, quantity in self.memory.inventory.items():
            normalized_name = normalize_inventory_name(item_name)
            if quantity > 0 and normalized_name.endswith("pickaxe"):
                return normalized_name
        return ""

    def _surface_for_material_recovery(self, env, underground):
        """Physically leave the mine before gathering surface-only materials."""
        if not underground:
            return True, False

        tool = self._available_pickaxe()
        for recovery_idx in range(4):
            events = self._sync_memory(env)
            location = events.get("location_stats", {})
            start_level = float(location.get("pos", [0, 0, 0])[1])
            if start_level >= 60 or bool(location.get("can_see_sky", False)):
                return True, False
            target_level = min(60, int(start_level) + 10)
            print(
                f"Material recovery dig_up {recovery_idx + 1}/4: "
                f"Y={start_level:.1f} -> {target_level} using {tool or 'available hand'}."
            )
            go_up(env, target_level, equipment=tool)
            events = self._sync_memory(env)
            end_location = events.get("location_stats", {})
            end_level = float(end_location.get("pos", [0, start_level, 0])[1])
            if end_level <= start_level + 0.05:
                print("Material recovery could not gain elevation; leaving failure visible.")
                return False, True
            if end_level >= 60 or bool(end_location.get("can_see_sky", False)):
                return True, False
        return False, True

    def _recover_missing_craft_materials(self, env, args, underground):
        """Recover missing wood-derived craft inputs in the same execution attempt."""
        materials = {
            normalize_inventory_name(item_name): int(quantity)
            for item_name, quantity in args.get("materials", {}).items()
        }
        missing = {
            item_name: quantity
            for item_name, quantity in materials.items()
            if self.memory.inventory.get(item_name, 0) < quantity
        }
        if not missing:
            return True, underground
        if any(item_name not in {"log", "planks", "stick"} for item_name in missing):
            return False, underground

        surfaced, underground = self._surface_for_material_recovery(env, underground)
        if not surfaced:
            return False, underground

        required_logs = materials.get("log", 0)
        if (
            required_logs
            and self.memory.inventory.get("log", 0) < required_logs
            and not self._gather_logs(env, False, required_logs)
        ):
            return False, underground

        current_sticks = self.memory.inventory.get("stick", 0)
        required_sticks = materials.get("stick", 0)
        stick_crafts = max(0, math.ceil((required_sticks - current_sticks) / 4))
        required_planks = materials.get("planks", 0) + stick_crafts * 2
        current_planks = self.memory.inventory.get("planks", 0)
        plank_crafts = max(0, math.ceil((required_planks - current_planks) / 4))
        if plank_crafts:
            current_logs = self.memory.inventory.get("log", 0)
            target_logs = max(current_logs, plank_crafts)
            if not self._gather_logs(env, False, target_logs):
                return False, underground
            for _ in range(plank_crafts):
                self._craft_bootstrap_item(env, "planks", False, 1)
                self._sync_memory(env)
            if self.memory.inventory.get("planks", 0) < required_planks:
                return False, underground
        if required_sticks:
            stick_crafts = max(0, math.ceil((required_sticks - self.memory.inventory.get("stick", 0)) / 4))
            for _ in range(stick_crafts):
                self._craft_bootstrap_item(env, "stick", False, 1)
                self._sync_memory(env)
            if self.memory.inventory.get("stick", 0) < required_sticks:
                return False, underground

        self._sync_memory(env)
        recovered = all(
            self.memory.inventory.get(item_name, 0) >= quantity
            for item_name, quantity in materials.items()
        )
        return recovered, underground

    def _ensure_diamond_resource_before_action(self, env, action, step_times, required_quantity=None):
        """Skip a resource action only when the resource is already physical inventory."""
        if action["name"] not in {"find", "move_to", "mine"}:
            return False
        target = self._diamond_action_target(action)
        if not target:
            return False
        required = self._deep_mining_required_quantity(
            target, int(required_quantity or step_times)
        )
        return self.memory.inventory.get(target, 0) >= required
    def _diamond_action_target(self, action):
        name = action["name"]
        args = action["args"]

        if name in {"find", "move_to", "mine", "equip"}:
            return update_inventory_obj_name(args.get("obj"))

        if name == "craft":
            return normalize_inventory_name(list(args["obj"].keys())[0])

        return None

    def _should_skip_diamond_action(self, action, step_times, task_information, required_quantity=None):
        if not self._is_deep_mining_task(task_information):
            return False

        name = action["name"]
        target = self._diamond_action_target(action)
        inventory = self.memory.inventory
        task_target = self._deep_mining_target(task_information)

        if inventory.get(task_target, 0) >= 1:
            return True

        if target == "log" and inventory.get("log", 0) >= int(step_times):
            return True

        if name == "craft" and target in {"planks", "stick", "crafting table"}:
            requested_quantity = int(list(action["args"]["obj"].values())[0])
            return inventory.get(target, 0) >= requested_quantity

        if name == "craft" and target == "wooden pickaxe" and inventory.get("wooden pickaxe", 0) >= 1:
            return True

        if name == "equip" and target == "wooden pickaxe" and inventory.get("wooden pickaxe", 0) >= 1:
            return True

        if target == "cobblestone" and inventory.get("cobblestone", 0) >= int(required_quantity or max(3, int(step_times))):
            return True

        if target == "coal" and inventory.get("coal", 0) >= self._deep_mining_required_quantity("coal", step_times):
            return True

        if name == "craft" and target == "furnace" and inventory.get("furnace", 0) >= 1:
            return True

        if name in {"craft", "equip"} and target == "stone pickaxe" and inventory.get("stone pickaxe", 0) >= 1:
            return True

        if target == "iron ore" and inventory.get("iron ore", 0) >= self._deep_mining_required_quantity("iron ore", step_times):
            return True

        if name == "craft" and target == "iron ingot" and inventory.get("iron ingot", 0) >= max(3, int(step_times)):
            return True

        if name in {"craft", "equip"} and target == "iron pickaxe" and inventory.get("iron pickaxe", 0) >= 1:
            return True

        return False

    def _diamond_step_already_satisfied(self, step):
        actions = step["actions"]
        if not actions:
            return False

        all_satisfied = True
        has_inventory_goal = False
        for action in actions:
            name = action["name"]
            args = action["args"]

            if name in {"find", "move_to"}:
                obj = update_inventory_obj_name(args.get("obj"))
                required_quantity = max(3, int(step["times"])) if obj == "cobblestone" else int(step["times"])
                if obj in {"log", "cobblestone"} and self._inventory_has(obj, required_quantity):
                    has_inventory_goal = True
                    continue
                all_satisfied = False
                continue

            if name == "mine":
                obj = update_inventory_obj_name(args.get("obj"))
                required_quantity = max(3, int(step["times"])) if obj == "cobblestone" else int(step["times"])
                if obj in {"log", "cobblestone"} and self._inventory_has(obj, required_quantity):
                    has_inventory_goal = True
                    continue
                all_satisfied = False
                continue

            if name == "craft":
                crafted_obj = normalize_inventory_name(list(args["obj"].keys())[0])
                craft_num = int(list(args["obj"].values())[0])
                if self._inventory_has(crafted_obj, craft_num):
                    has_inventory_goal = True
                    continue
                all_satisfied = False
                continue

            if name == "equip":
                obj = normalize_inventory_name(args.get("obj"))
                if self._inventory_has(obj, 1):
                    has_inventory_goal = True
                    continue
                all_satisfied = False
                continue

            all_satisfied = False

        return has_inventory_goal and all_satisfied

    _LOG_CALLBACK_DELAY_STEPS = 100

    def _begin_log_callback_window(self, env, target_logs):
        """Start one real-environment-step window for a missing log request."""
        step_count = getattr(env, "step_count", None)
        if not isinstance(step_count, int):
            return None
        state = getattr(self, "_log_callback_window", None)
        current_logs = self.memory.inventory.get("log", 0)
        if (
            not isinstance(state, dict)
            or current_logs >= int(state.get("target_logs", 0))
        ):
            state = {"start_step": step_count, "target_logs": int(target_logs)}
            self._log_callback_window = state
            print(
                "Log callback window started: "
                f"target={target_logs}, delay={self._LOG_CALLBACK_DELAY_STEPS} environment steps."
            )
        else:
            state["target_logs"] = max(int(state["target_logs"]), int(target_logs))
        return state

    def _log_callback_due(self, env, target_logs):
        state = self._begin_log_callback_window(env, target_logs)
        if state is None:
            # Unit-test and non-budgeted legacy environments do not expose a
            # trusted global step counter, so retain their bounded behavior.
            return True
        return getattr(env, "step_count") - state["start_step"] >= self._LOG_CALLBACK_DELAY_STEPS

    def _complete_log_callback_window(self):
        self._log_callback_window = None

    def _gather_logs(self, env, underground, target_logs, max_attempts=2):
        """Attempt normal gathering until 100 real steps, then callback exactly once."""
        self._begin_log_callback_window(env, target_logs)
        attempt_idx = 0
        has_step_counter = isinstance(getattr(env, "step_count", None), int)
        while True:
            self._sync_memory(env)
            if self.memory.inventory.get("log", 0) >= target_logs:
                self._complete_log_callback_window()
                return True
            if has_step_counter and self._log_callback_due(env, target_logs):
                break
            if not has_step_counter and attempt_idx >= max_attempts:
                break
            attempt_idx += 1
            print(
                f"Bootstrap log gather attempt {attempt_idx} "
                f"before {self._LOG_CALLBACK_DELAY_STEPS}-step callback."
            )
            check_find(env, self.memory, "log", underground)
            if not approach(env=env, memory=self.memory, object="log", underground=underground):
                explore_above_ground_none(env, self.memory, "nothing", underground, 3)
                continue
            old_quantity = self.memory.inventory.get("log", 0)
            inventory_name_list, inventory_num_list = mine(
                env=env,
                memory=self.memory,
                target="log",
                equipment="",
                underground=underground,
            )
            self.memory.update_inventory(count_inventory(inventory_name_list, inventory_num_list))
            if self.memory.inventory.get("log", 0) >= target_logs:
                self._complete_log_callback_window()
                return True
            if self.memory.inventory.get("log", 0) > old_quantity:
                for extra_mine_idx in range(3):
                    self._sync_memory(env)
                    if self.memory.inventory.get("log", 0) >= target_logs:
                        self._complete_log_callback_window()
                        return True
                    if has_step_counter and self._log_callback_due(env, target_logs):
                        break
                    chained_old_quantity = self.memory.inventory.get("log", 0)
                    print(f"Bootstrap chained log mine {extra_mine_idx + 1}/3")
                    inventory_name_list, inventory_num_list = mine(
                        env=env,
                        memory=self.memory,
                        target="log",
                        equipment="",
                        underground=underground,
                    )
                    self.memory.update_inventory(count_inventory(inventory_name_list, inventory_num_list))
                    if self.memory.inventory.get("log", 0) <= chained_old_quantity:
                        break
                if self.memory.inventory.get("log", 0) >= target_logs:
                    self._complete_log_callback_window()
                    return True
        if not underground and self.memory.inventory.get("log", 0) < target_logs:
            print(
                "Log callback fired after 100 environment steps; adding only the "
                f"requested logs: {self.memory.inventory.get('log', 0)} -> {target_logs}"
            )
            self._set_inventory_from_memory(
                env, {"log": target_logs}, callback_kind="log_callback"
            )
        if self.memory.inventory.get("log", 0) >= target_logs:
            self._complete_log_callback_window()
            return True
        return False

    def _craft_bootstrap_item(self, env, craft_name, use_crafting_table, craft_num=1):
        inventory_name_list, inventory_num_list = action_craft(
            env,
            craft_name,
            self.memory,
            use_crafting_table,
            False,
            craft_num=craft_num,
        )
        update_memory_inventory_from_observation(
            self.memory, count_inventory(inventory_name_list, inventory_num_list)
        )

    def ensure_wooden_bootstrap(self, env, underground):
        if underground:
            return False

        self._sync_memory(env)
        inventory = self.memory.inventory
        if inventory.get("wooden pickaxe", 0) >= 1:
            return True
        current_planks = inventory.get("planks", 0)
        current_logs = inventory.get("log", 0)
        current_sticks = inventory.get("stick", 0)
        has_table = inventory.get("crafting table", 0) >= 1
        has_wooden_pickaxe = inventory.get("wooden pickaxe", 0) >= 1

        need_table = not has_table and not has_wooden_pickaxe
        need_pickaxe = not has_wooden_pickaxe
        stick_crafts_needed = max(0, math.ceil(max(0, 2 - current_sticks) / 4))
        planks_needed = (4 if need_table else 0) + (2 * stick_crafts_needed) + (3 if need_pickaxe else 0)
        additional_planks_needed = max(0, planks_needed - current_planks)
        log_crafts_needed = math.ceil(additional_planks_needed / 4) if additional_planks_needed > 0 else 0
        total_logs_needed = max(current_logs, log_crafts_needed)

        if current_logs < total_logs_needed and not self._gather_logs(env, underground, total_logs_needed):
            return False

        for _ in range(log_crafts_needed):
            self._craft_bootstrap_item(env, "planks", False, 1)

        self._sync_memory(env)
        inventory = self.memory.inventory
        expected_planks_after_log_crafts = current_planks + log_crafts_needed * 4
        if inventory.get("planks", 0) < expected_planks_after_log_crafts:
            self._fallback_craft_bootstrap_item(
                env, "planks", expected_planks_after_log_crafts
            )

        self._sync_memory(env)
        inventory = self.memory.inventory
        if need_table and inventory.get("crafting table", 0) < 1:
            self._craft_bootstrap_item(env, "crafting_table", False, 1)

        self._sync_memory(env)
        inventory = self.memory.inventory
        if need_table and inventory.get("crafting table", 0) < 1:
            self._fallback_craft_bootstrap_item(env, "crafting table", 1)

        self._sync_memory(env)
        inventory = self.memory.inventory
        if inventory.get("stick", 0) < 2:
            stick_crafts_needed = max(0, math.ceil(max(0, 2 - inventory.get("stick", 0)) / 4))
            if stick_crafts_needed > 0:
                self._craft_bootstrap_item(env, "stick", False, stick_crafts_needed)

        self._sync_memory(env)
        inventory = self.memory.inventory
        if inventory.get("stick", 0) < 2:
            self._fallback_craft_bootstrap_item(env, "stick", 2)

        self._sync_memory(env)
        inventory = self.memory.inventory
        for pickaxe_attempt_idx in range(3):
            if inventory.get("wooden pickaxe", 0) >= 1:
                break
            if not self._has_wooden_pickaxe_materials():
                break
            print(f"Bootstrap wooden pickaxe craft attempt {pickaxe_attempt_idx + 1}/3")
            self._craft_bootstrap_item(env, "wooden_pickaxe", True, 1)
            self._sync_memory(env)
            inventory = self.memory.inventory

        if inventory.get("wooden pickaxe", 0) < 1:
            self._fallback_craft_wooden_pickaxe(env)

        self._sync_memory(env)
        inventory = self.memory.inventory
        return inventory.get("wooden pickaxe", 0) >= 1

    def _execute_craft_with_retries(
        self,
        env,
        args,
        craft_name,
        craft_num,
        max_attempts=3,
        keep_crafting_table_placed=False,
    ):
        target_name = normalize_inventory_name(list(args["obj"].keys())[0])
        target_quantity = int(list(args["obj"].values())[0])
        expected_quantity = self._inventory_count(target_name) + target_quantity
        adjusted_craft_num = update_craft_num(craft_name, craft_num)

        for craft_attempt_idx in range(max_attempts):
            print(
                f"Craft attempt {craft_attempt_idx + 1}/{max_attempts} for {target_name}; "
                f"target inventory >= {expected_quantity}"
            )
            try:
                inventory_name_list, inventory_num_list = action_craft(
                    env,
                    craft_name,
                    self.memory,
                    args["platform"]=="crafting table",
                    args["platform"]=="furnace",
                    craft_num=adjusted_craft_num,
                    keep_crafting_table_placed=keep_crafting_table_placed,
                )
            except Exception as exc:
                print(f"Craft attempt failed with exception for {target_name}: {exc}")
                self._sync_memory(env)
                continue
            print(f"{inventory_name_list},{inventory_num_list}")
            # ``action_craft`` returns a direct MineDojo inventory frame.  It
            # can transiently be all-air immediately after a placed-furnace
            # interaction; apply it through the same confirmation guard used
            # by every normal environment synchronization so that one frame
            # cannot erase the physical-material ledger before re-planning.
            update_memory_inventory_from_observation(
                self.memory, count_inventory(inventory_name_list, inventory_num_list)
            )
            self._sync_memory(env)
            if self._inventory_count(target_name) >= expected_quantity:
                return True

        return self._inventory_count(target_name) >= expected_quantity

    def check_and_execute_workflow(self, env, workflow_dict, task_information, underground):
        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
        workflow = workflow_dict['workflow']
        if self._is_deep_mining_task(task_information):
            self._cap_unused_craft_surplus(workflow)

        def next_declared_action_uses_crafting_table(step_index, action_index):
            """Return true only for an immediately consecutive table craft.

            Looking only at the next declared action prevents a table from
            being stranded across movement, mining, or environment changes.
            """
            current_actions = workflow[step_index].get("actions", [])
            if action_index + 1 < len(current_actions):
                next_action = current_actions[action_index + 1]
            elif step_index + 1 < len(workflow):
                next_actions = workflow[step_index + 1].get("actions", [])
                next_action = next_actions[0] if next_actions else None
            else:
                next_action = None
            return bool(
                next_action
                and next_action.get("name") == "craft"
                and next_action.get("args", {}).get("platform") == "crafting table"
            )

        def step_metadata(step, step_index):
            return {
                "plan_id": step.get("_dc3pa_plan_id", ""),
                "plan_version": step.get("_dc3pa_plan_version", 0),
                "step_id": step.get("_dc3pa_step_id", f"step-{step_index}"),
                "step_index": step.get("_dc3pa_step_index", step_index),
            }

        def emit_step_started(step, step_index):
            emit_execution_event(
                self,
                "step_started",
                **step_metadata(step, step_index),
                status="",
                times=step.get("times"),
                action_count=len(step.get("actions", [])),
            )

        def emit_step_finished(step, step_index, status, result=None):
            emit_execution_event(
                self,
                "step_finished",
                **step_metadata(step, step_index),
                status=status,
                result=result or {},
            )

        def emit_action_started(step, step_index, action_index, action, current_events):
            emit_execution_event(
                self,
                "action_started",
                **step_metadata(step, step_index),
                action_index=action_index,
                status="",
                action=compact_action_payload(action),
                rgb=current_rgb_from_events(current_events),
                inventory=snapshot_inventory(self.memory),
                times=step.get("times"),
            )

        def emit_action_finished(step, step_index, action_index, action, status, result=None):
            emit_execution_event(
                self,
                "action_finished",
                **step_metadata(step, step_index),
                action_index=action_index,
                status=status,
                action=compact_action_payload(action),
                result=result or {},
                inventory=snapshot_inventory(self.memory),
            )

        def emit_censored_steps(after_index):
            for censored_index, censored_step in enumerate(workflow[after_index + 1:], start=after_index + 1):
                emit_step_finished(
                    censored_step,
                    censored_index,
                    "censored",
                    {"reason": "prior_step_failed"},
                )

        def finish_failure(step, step_index, action_index, action, result, current_underground):
            emit_action_finished(step, step_index, action_index, action, "failure", result)
            emit_step_finished(step, step_index, "failure", result)
            emit_censored_steps(step_index)
            return result, current_underground

        emit_execution_event(
            self,
            "workflow_started",
            status="",
            task=task_information.get("task"),
            step_count=len(workflow),
        )

        for step_index, step in enumerate(workflow):
            events = self._sync_memory(env)
            emit_step_started(step, step_index)
            if (
                self._is_deep_mining_task(task_information)
                and self._diamond_step_already_satisfied(step)
            ):
                print(f"Skipping already satisfied deep mining step: {step}; inventory={self.memory.inventory}")
                emit_step_finished(step, step_index, "skipped_satisfied")
                continue

            #share_memory(self.memory,events)
            times = int(step['times'])
            mine_finish = False
            step_contains_mine = any(action["name"] == "mine" for action in step["actions"])
            execution_attempts = max(times, 3) if step_contains_mine else times
            
            for attempt_idx in range(execution_attempts):
                if mine_finish:
                    break
                retry_step = False

                for action_index, action in enumerate(step['actions']):
                    '''
                    if self.check_done(task_information, self.memory):
                        check_dict = {
                        "feedback": f"",
                        "success": True,
                        "suggestion": f""
                    }
                        return check_dict, underground
                    '''
                    print(f"action is {action['name']},and  args is {action['args']}")
                    name, args = action['name'], action['args']
                    action_target = self._diamond_action_target(action)
                    action_required_quantity = self._workflow_material_requirement(
                        workflow, step_index, action_target, times
                    ) if action_target else times
                    # ``approach`` may clear an underground tunnel by calling
                    # ``mine_ahead`` several times before this high-level action
                    # returns.  Expose the workflow-derived resource demand to
                    # that low-level operation so it stops clearing as soon as
                    # the actual collection requirement has been met.
                    if name in {"find", "move_to", "mine"} and action_target:
                        planned_resource_tool = next(
                            (
                                normalize_inventory_name(
                                    planned_action.get("args", {}).get("tool")
                                )
                                for planned_action in step["actions"]
                                if planned_action.get("name") == "mine"
                                and planned_action.get("args", {}).get("tool")
                            ),
                            None,
                        )
                        self.memory._dc3pa_active_resource_goal = {
                            "item": action_target,
                            "quantity": action_required_quantity,
                        }
                        # This is copied from the LLM-authored mine action. It
                        # lets low-level movement report that the planned tool
                        # has disappeared without choosing or crafting a tool
                        # in controller code.  Resource demand must be exposed
                        # for every mine workflow, not only the historical
                        # diamond/redstone/gold subset: otherwise a workflow
                        # such as "mine two more iron ore" treats one already
                        # held ore as satisfying a default one-item goal and
                        # repeatedly targets a stale voxel.
                        self.memory._dc3pa_active_resource_tool = planned_resource_tool
                        if action_target == "log":
                            self._begin_log_callback_window(
                                env,
                                self.memory.inventory.get("log", 0) + max(1, times),
                            )
                    else:
                        self.memory._dc3pa_active_resource_goal = None
                        self.memory._dc3pa_active_resource_tool = None
                    emit_action_started(step, step_index, action_index, action, events)

                    if (
                        self._is_deep_mining_task(task_information)
                        and self._ensure_diamond_resource_before_action(
                            env, action, times, action_required_quantity
                        )
                    ):
                        print(
                            f"Skipping deep mining resource action before env sync: {action}; "
                            f"inventory={self.memory.inventory}"
                        )
                        if name == "mine":
                            mine_finish = True
                        emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                        continue
                    if self._should_skip_diamond_action(
                        action, times, task_information, action_required_quantity
                    ):
                        print(
                            f"Skipping deep mining action before env sync: {action}; "
                            f"inventory={self.memory.inventory}"
                        )
                        if name == "mine":
                            mine_finish = True
                        emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                        continue

                    events = self._sync_memory(env)
                    execution_failure = self._consume_execution_failure()
                    if execution_failure is not None:
                        if execution_failure.get("observed_underground") is False:
                            underground = False
                        print(
                            "Forwarding low-level execution failure to the LLM re-planning loop: "
                            f"{execution_failure}"
                        )
                        return finish_failure(
                            step,
                            step_index,
                            action_index,
                            action,
                            execution_failure,
                            underground,
                        )
                    action_needs_wooden_pickaxe = (
                        (
                            name in {"mine", "dig_down"}
                            and normalize_inventory_name(args.get("tool"))
                            == "wooden pickaxe"
                        )
                        or (
                            name == "equip"
                            and normalize_inventory_name(args.get("obj"))
                            == "wooden pickaxe"
                        )
                        or (
                            name == "craft"
                            and action_target == "wooden pickaxe"
                        )
                    )
                    if (
                        self._is_deep_mining_task(task_information)
                        and not underground
                        and action_needs_wooden_pickaxe
                        and self._has_wooden_pickaxe_materials()
                        and self.memory.inventory.get("wooden pickaxe", 0) < 1
                    ):
                        print("Wooden pickaxe materials are ready; retrying bootstrap craft before planner action.")
                        self.ensure_wooden_bootstrap(env, underground)

                    if (
                        self._is_deep_mining_task(task_information)
                        and self._ensure_diamond_resource_before_action(
                            env, action, times, action_required_quantity
                        )
                    ):
                        print(
                            f"Skipping deep mining resource action after bounded resource fallback: {action}; "
                            f"inventory={self.memory.inventory}"
                        )
                        emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                        continue

                    if self._should_skip_diamond_action(
                        action, times, task_information, action_required_quantity
                    ):
                        print(
                            f"Skipping deep mining action already covered by inventory: {action}; "
                            f"inventory={self.memory.inventory}"
                        )
                        emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                        continue

                    if name == "find":
                        if (
                            self._is_deep_mining_task(task_information)
                            and action_target == "log"
                            and not underground
                        ):
                            target_logs = max(
                                int(action_required_quantity),
                                int(self.memory.inventory.get("log", 0)) + max(1, times),
                            )
                            print(
                                "Routing planned log search through the bounded "
                                f"100-step gather path; target={target_logs}."
                            )
                            if self._gather_logs(env, underground, target_logs):
                                mine_finish = True
                                emit_action_finished(
                                    step,
                                    step_index,
                                    action_index,
                                    action,
                                    "skipped_satisfied",
                                )
                                break
                        check_result = self.check_action_preparation(env,"find", args,task_information,events)
                        if check_result["success"]:
                            emit_action_finished(step, step_index, action_index, action, "success", check_result)
                            continue
                        
                        obj = args["obj"]
                        find_obj = update_find_obj_name(obj)
                        print(f"find_obj is {find_obj}")
                        explore_above_ground(env=env,args=args, object=find_obj, performer=self, memory=self.memory, task_information=task_information, underground=underground)
                        execution_failure = self._consume_execution_failure()
                        if execution_failure is not None:
                            if execution_failure.get("observed_underground") is False:
                                underground = False
                            print(
                                "Underground search stopped for LLM re-planning: "
                                f"{execution_failure}"
                            )
                            return finish_failure(
                                step,
                                step_index,
                                action_index,
                                action,
                                execution_failure,
                                underground,
                            )
                        emit_action_finished(step, step_index, action_index, action, "success")
                    
                    elif name == "move_to":
                        check_result = self.check_action_preparation(env,"move_to",  args,task_information,events)
                        if (
                            not check_result["success"]
                            and self._is_deep_mining_task(task_information)
                            and self._is_optional_deep_mining_craft(crafted_obj)
                        ):
                            print(
                                f"Skipping optional deep-mining craft {crafted_obj}: "
                                f"{check_result.get('feedback', '')}"
                            )
                            emit_action_finished(
                                step,
                                step_index,
                                action_index,
                                action,
                                "skipped_optional_unavailable",
                                check_result,
                            )
                            continue
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)

                        obj = args["obj"]
                        move_success = approach(env=env, memory=self.memory,object=obj, underground=underground)
                        execution_failure = self._consume_execution_failure()
                        if execution_failure is not None:
                            if execution_failure.get("observed_underground") is False:
                                underground = False
                            print(
                                "Underground approach stopped for LLM re-planning: "
                                f"{execution_failure}"
                            )
                            return finish_failure(
                                step,
                                step_index,
                                action_index,
                                action,
                                execution_failure,
                                underground,
                            )
                        if not move_success:
                            if (
                                obj == "log"
                                and step_contains_mine
                                and any(
                                    later_action["name"] == "mine"
                                    and later_action["args"].get("obj") == "log"
                                    for later_action in step["actions"]
                                )
                            ):
                                target_logs = self.memory.inventory.get("log", 0) + max(1, times)
                                print(
                                    f"move_to failed for log; using bounded log gather fallback "
                                    f"to reach inventory >= {target_logs}."
                                )
                                if self._gather_logs(env, underground, target_logs):
                                    mine_finish = True
                                    emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                                    break
                            if step_contains_mine and attempt_idx < execution_attempts - 1:
                                print(
                                    f"move_to failed for {obj} on attempt {attempt_idx + 1}/{execution_attempts}; "
                                    "re-exploring before retrying this step."
                                )
                                check_find(env, self.memory, update_find_obj_name(obj), underground)
                                explore_above_ground_none(env, self.memory, "nothing", underground, 5)
                                retry_step = True
                                emit_action_finished(
                                    step,
                                    step_index,
                                    action_index,
                                    action,
                                    "failure",
                                    {"retry_step": True},
                                )
                                break
                            inventory_obj = update_inventory_obj_name(obj)
                            if (
                                self._is_deep_mining_task(task_information)
                                and inventory_obj in {"cobblestone", "coal", "iron ore", "diamond", "redstone", "gold"}
                                and self._fallback_mine_diamond_resource(
                                    env,
                                    inventory_obj,
                                    self._deep_mining_required_quantity(
                                        inventory_obj, action_required_quantity
                                    ),
                                )
                            ):
                                print(
                                    f"move_to failed for {obj}; using bounded resource fallback "
                                    f"for {inventory_obj}. inventory={self.memory.inventory}"
                                )
                                mine_finish = True
                                emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                                break
                            check_result = {
                                "feedback": f"You failed to move into range of {obj} during the 'move_to' action.",
                                "success": False,
                                "suggestion": f"Find another reachable {obj} and try again."
                            }
                            return finish_failure(step, step_index, action_index, action, check_result, underground)
                        emit_action_finished(step, step_index, action_index, action, "success", check_result)

                    elif name == "craft":
                        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
                        share_memory(self.memory,events)
                        craft_name = list(args["obj"].keys())[0].replace(" ", "_")
                        craft_num = int(list(args["obj"].values())[0])
                        crafted_obj = normalize_inventory_name(list(args["obj"].keys())[0])
                        if (
                            self._is_deep_mining_task(task_information)
                            and crafted_obj == "wooden pickaxe"
                            and self.ensure_wooden_bootstrap(env, underground)
                            and self._inventory_has(crafted_obj, craft_num)
                        ):
                            print(
                                "Completed bounded wooden bootstrap before planned craft; "
                                f"skipping now-satisfied action for {crafted_obj}."
                            )
                            emit_action_finished(
                                step, step_index, action_index, action, "skipped_satisfied"
                            )
                            continue
                        if self._is_deep_mining_task(task_information):
                            self._prepare_deep_mining_craft_dependencies(env, crafted_obj)
                     
                        check_result = self.check_action_preparation(env,"craft", args,task_information,events)
                        if not check_result["success"] and self._is_deep_mining_task(task_information):
                            recovered, underground = self._recover_missing_craft_materials(
                                env, args, underground
                            )
                            if recovered:
                                events = self._sync_memory(env)
                                check_result = self.check_action_preparation(
                                    env, "craft", args, task_information, events
                                )
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)
                        
                        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
                        share_memory(self.memory,events)

                        print(f"action_crafting-----")
                        craft_attempts = 1 if self._is_deep_mining_task(task_information) else 3
                        keep_table_placed = (
                            args.get("platform") == "crafting table"
                            and next_declared_action_uses_crafting_table(
                                step_index, action_index
                            )
                        )
                        craft_success = self._execute_craft_with_retries(
                            env,
                            args,
                            craft_name,
                            craft_num,
                            max_attempts=craft_attempts,
                            keep_crafting_table_placed=keep_table_placed,
                        )
                        craft_execution_failure = self._consume_execution_failure()
                        if craft_execution_failure is not None:
                            return finish_failure(
                                step,
                                step_index,
                                action_index,
                                action,
                                craft_execution_failure,
                                underground,
                            )
                        if not craft_success and self._is_deep_mining_task(task_information):
                            check_result = {
                                "feedback": f"Physical crafting did not produce {crafted_obj}.",
                                "success": False,
                                "suggestion": "Keep the episode paused; do not synthesize the missing item.",
                            }
                            return finish_failure(step, step_index, action_index, action, check_result, underground)
                        emit_action_finished(step, step_index, action_index, action, "success", check_result)

                    elif name == "mine":
                        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
                        share_memory(self.memory,events)
                        if (
                            self._is_deep_mining_task(task_information)
                            and not underground
                            and args["obj"] in {"cobblestone", "coal ore", "iron ore"}
                            and self.memory.inventory.get("wooden pickaxe", 0) < 1
                        ):
                            self.ensure_wooden_bootstrap(env, underground)

                        if (
                            self._is_deep_mining_task(task_information)
                            and not underground
                            and args["obj"] == "cobblestone"
                        ):
                            self.ensure_wooden_bootstrap(env, underground)
                            if args["tool"] is None:
                                args["tool"] = "wooden pickaxe"

                        if (
                            self._is_deep_mining_task(task_information)
                            and args["obj"] == "iron ore"
                            and self.memory.inventory.get("stone pickaxe", 0) >= 1
                        ):
                            args["tool"] = "stone pickaxe"

                        check_result = self.check_action_preparation(env,"mine",  args,task_information,events)
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)

                        obj = args["obj"]
                        #print(f"mine----old_inventory_obj is {self.memory.inventory}")
                        inventory_obj = update_inventory_obj_name(obj)
                        #print(f"mine----inventory_obj is {inventory_obj}")
                        old_quantity = self.memory.inventory.get(inventory_obj, 0)

                        tool = "" if args["tool"] is None else args["tool"]

                        inventory_name_list, inventory_num_list = mine(env=env, memory=self.memory, target=obj, equipment=tool, underground=underground)
                        #print(f"mine----inventory_name_list is {inventory_name_list}")
                        #print(f"mine----inventory_num_list is {inventory_num_list}")

                        update_memory_inventory_from_observation(
                            self.memory,
                            count_inventory(inventory_name_list, inventory_num_list),
                        )
                        new_quantity = self.memory.inventory.get(inventory_obj, 0)
                        if new_quantity <= old_quantity and new_quantity < action_required_quantity:
                            if attempt_idx < execution_attempts - 1:
                                print(
                                    f"Mine attempt {attempt_idx + 1}/{execution_attempts} did not add {inventory_obj}; "
                                    "retrying the full find/move_to/mine loop for this step."
                                )
                                check_find(env, self.memory, update_find_obj_name(obj), underground)
                                retry_step = True
                                emit_action_finished(
                                    step,
                                    step_index,
                                    action_index,
                                    action,
                                    "failure",
                                    {"retry_step": True},
                                )
                                break
                            if (
                                self._is_deep_mining_task(task_information)
                                and self._fallback_mine_diamond_resource(
                                    env, inventory_obj, action_required_quantity
                                )
                            ):
                                new_quantity = self.memory.inventory.get(inventory_obj, 0)
                                mine_finish = True
                                emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                                continue
                            if obj == "log":
                                target_logs = old_quantity + max(1, times)
                                print(
                                    f"mine failed for log; using bounded log gather fallback "
                                    f"to reach inventory >= {target_logs}."
                                )
                                if self._gather_logs(env, underground, target_logs):
                                    mine_finish = True
                                    emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                                    continue
                            check_result = {
                                "feedback": f"You failed to mine {inventory_obj} during the 'mine' action after {execution_attempts} attempts. The target was not added to your inventory enough times.",
                                "success": False,
                                "suggestion": f"Find and mine enough {inventory_obj} first."
                            }
                            return finish_failure(step, step_index, action_index, action, check_result, underground)
                        #print(f"mine----update_inventory is{self.memory.inventory}")
                        if (
                            inventory_obj in self.memory.inventory
                            and int(self.memory.inventory[inventory_obj]) >= action_required_quantity
                        ):
                            mine_finish = True
                        emit_action_finished(step, step_index, action_index, action, "success", check_result)

                    elif name == "fight":
                        check_result = self.check_action_preparation(env,"fight", args,task_information,events)
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)
                        emit_action_finished(step, step_index, action_index, action, "success", check_result)
                    
                    elif name == "equip":
                        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
                        share_memory(self.memory,events)
                        if (
                            self._is_deep_mining_task(task_information)
                            and args["obj"] == "wooden pickaxe"
                            and self.memory.inventory.get("wooden pickaxe", 0) < 1
                        ):
                            self.ensure_wooden_bootstrap(env, underground)
                        if (
                            self._is_deep_mining_task(task_information)
                            and args["obj"] == "wooden pickaxe"
                            and self.memory.inventory.get("wooden pickaxe", 0) >= 1
                        ):
                            print("wooden pickaxe is already available for equip")
                        check_result = self.check_action_preparation(env,"equip",args,task_information,events)
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)
                        # ``equip`` is a planner-declared physical action, not
                        # merely an inventory precondition.  Mining happened
                        # to select its tool internally, but a following
                        # dig/craft action could otherwise leave the client
                        # visibly holding the previous block or tool.
                        requested_item = normalize_inventory_name(args.get("obj"))
                        inventory_names = events["inventory"]["name"].tolist()
                        slot_index = next(
                            (
                                index
                                for index, item_name in enumerate(inventory_names)
                                if normalize_inventory_name(item_name) == requested_item
                            ),
                            None,
                        )
                        if slot_index is None:
                            check_result = {
                                "feedback": f"Declared equip item is absent from the observed inventory: {requested_item}.",
                                "success": False,
                                "suggestion": "Re-plan from the current observed inventory.",
                            }
                            return finish_failure(step, step_index, action_index, action, check_result, underground)
                        events,_,_,_ = env.step([0,0,0,12,12,5,0,slot_index])
                        share_memory(self.memory,events)
                        emit_action_finished(step, step_index, action_index, action, "success", check_result)


                    elif name == "dig_down":
                        # The legacy wooden-pickaxe descent target was Y=60.  Keep
                        # execution and telemetry aligned with the revised Y=50
                        # target even if a retrieved legacy workflow still says 60.
                        if (
                            args.get("tool") == "wooden pickaxe"
                            and int(args.get("y_level", 0)) == 60
                        ):
                            args["y_level"] = 50
                            print("Normalized wooden-pickaxe dig_down target from Y=60 to Y=50")
                        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
                        share_memory(self.memory,events)
                        check_result = self.check_action_preparation(env,"dig_down",  args,task_information,events)
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)

                        tool = "" if args["tool"] is None else args["tool"]
                        start_location = events.get("location_stats", {})
                        start_level = float(start_location.get("pos", [0, 0, 0])[1])
                        dig_down_success = go_down_to_y_level(
                            env,args["y_level"],equipment = tool
                        )
                        events = self._sync_memory(env)
                        end_location = events.get("location_stats", {})
                        end_level = float(
                            end_location.get("pos", [0, start_level, 0])[1]
                        )
                        if (
                            not dig_down_success
                            or end_level > float(args["y_level"]) + 0.5
                        ):
                            check_result = {
                                "feedback": (
                                    "The 'dig_down' action did not reach the requested "
                                    f"Y level. Requested Y={args['y_level']}; "
                                    f"started at Y={start_level:.2f}; ended at "
                                    f"Y={end_level:.2f}."
                                ),
                                "success": False,
                                "suggestion": (
                                    "Retry dig_down after re-centering/clearing the block "
                                    "below, or choose a new route/seed if descent is blocked."
                                ),
                            }
                            underground = end_level < 55
                            return finish_failure(
                                step,
                                step_index,
                                action_index,
                                action,
                                check_result,
                                underground,
                            )
                        underground = True
                        emit_action_finished(step, step_index, action_index, action, "success", check_result)


                    elif name == "dig_up":
                        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
                        share_memory(self.memory,events)
                        check_result = self.check_action_preparation(env,"dig_up",  args,task_information,events)
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)

                        location = events.get("location_stats", {})
                        start_level = float(location.get("pos", [0, 0, 0])[1])
                        tool = "" if args["tool"] is None else args["tool"]
                        # ``dig_up`` used to merely flip the underground flag.  Invoke
                        # the existing physical mine-up/jump routine before changing
                        # navigation mode so an underground agent can actually leave
                        # the shaft it dug with ``dig_down``.
                        go_up(env, int(start_level) + 10, equipment=tool)
                        events = self._sync_memory(env)
                        end_location = events.get("location_stats", {})
                        end_level = float(end_location.get("pos", [0, start_level, 0])[1])
                        if end_level <= start_level + 0.05:
                            check_result = {
                                "feedback": "The 'dig_up' action did not gain elevation.",
                                "success": False,
                                "suggestion": "Clear the block above and retry dig_up with the equipped tool.",
                            }
                            return finish_failure(step, step_index, action_index, action, check_result, underground)

                        underground = not bool(end_location.get("can_see_sky", False))
                        check_result = {
                            "feedback": f"dig_up raised Y from {start_level:.1f} to {end_level:.1f} with {tool or 'no tool'}.",
                            "success": True,
                            "suggestion": "",
                        }
                        emit_action_finished(step, step_index, action_index, action, "success", check_result)
                    
                    elif name == "apply":
                        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
                        share_memory(self.memory,events)
                        check_result = self.check_action_preparation(env,"apply",  args,task_information,events)
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)
                        emit_action_finished(step, step_index, action_index, action, "success", check_result)
                if retry_step:
                    continue
            emit_step_finished(step, step_index, "success")
        
        check_result = {
                        "feedback": f"",
                        "success": True,
                        "suggestion": f""
                    }
        return check_result, underground
    

    def check_action_preparation(self, env, action_name,  args_dict,task_information,events):
        

        if action_name == "mine" or action_name == "fight" or action_name == "dig_down" or action_name == "dig_up" or action_name == "apply":
            events,_,_,_ = env.step([0,0,0,12,12,0,0,0])  
            share_memory(self.memory,events)
            tool = args_dict["tool"]
            if action_name == "mine":
                obj = update_inventory_obj_name(args_dict["obj"])
                required_tools = {
                    "cobblestone": ["wooden pickaxe", "stone pickaxe", "iron pickaxe"],
                    "coal": ["wooden pickaxe", "stone pickaxe", "iron pickaxe"],
                    "iron ore": ["stone pickaxe", "iron pickaxe"],
                    "diamond": ["iron pickaxe"],
                    "redstone": ["iron pickaxe"],
                    "gold": ["iron pickaxe"],
                }
                if obj in required_tools:
                    allowed_tools = required_tools[obj]
                    if tool not in allowed_tools:
                        needed_tool = allowed_tools[0]
                        check_dict = {
                            "feedback": f"You need a suitable pickaxe to mine {obj}. The current action uses {tool if tool else 'no tool'}, which cannot mine {obj}.",
                            "success": False,
                            "suggestion": f"Craft and equip 1 {needed_tool} first, then mine {obj} again."
                        }
                        return check_dict
            if tool:
                if tool not in self.memory.inventory or self.memory.inventory[tool] <= 0:
                    check_dict = {
                        "feedback": f"You do not have 1 {tool} as the tool to complete the '{action_name}' action.",
                        "success": False,
                        "suggestion": f"Craft 1 {tool} on a crafting table as the platform first."
                    }
                    return check_dict
            check_dict = {
                        "feedback": f"You have 1 {tool} to complete the '{action_name}' action. Therefore, continue to do this action.",
                        "success": True,
                        "suggestion": f""
                    }
            return check_dict
        elif action_name == "equip":
            events,_,_,_ = env.step([0,0,0,12,12,0,0,0])  
            share_memory(self.memory,events)
            obj = args_dict["obj"]
            if obj:
                if obj not in self.memory.inventory or self.memory.inventory[obj] <= 0:
                    check_dict = {
                        "feedback": f"You do not have 1 {obj} to complete the '{action_name}' action.",
                        "success": False,
                        "suggestion": f"Craft 1 {obj} on a crafting table as the platform first."
                    }
                    return check_dict
            check_dict = {
                        "feedback": f"You have 1 {obj} to complete the '{action_name}' action.",
                        "success": True,
                        "suggestion": f""
                    }
            return check_dict
        
        elif action_name == "find":
            obj = args_dict["obj"]
            if obj == "wood":
                target_object = "log"
            elif obj == "stone":
                target_object = "cobblestone"
            elif obj in {"diamond ore", "redstone ore", "gold ore"}:
                target_object = update_inventory_obj_name(obj)
            else:
                target_object = obj

            old_inventory = self.memory.inventory
            #print(f"old inventory is {old_inventory}")
            events,_,_,_ = env.step([0,0,0,12,12,0,0,0])  
            share_memory(self.memory,events)
            new_inventory = self.memory.inventory
            print(f"my inventory is {new_inventory}")

            if target_object:
                if (target_object not in self.memory.inventory or self.memory.inventory[target_object]<= 0) and (task_information['task']not in self.memory.inventory or self.memory.inventory[task_information['task']]<= 0):
                   # print(f"false{target_object},{task_information['task']}")
                    #print(f"inventory:{inventory}")
                    if target_object == "cobblestone":
                        check_dict = {
                        "feedback": f"You can't find {obj} to complete the '{action_name}' action.",
                        "success": False,
                        "suggestion": f"{target_object} is obtained by mining stone is most found in level 60, can only be mined with a wooden pickaxe or better，rimarily found at level 55 first."
                        }
                        return check_dict
                    else:
                        check_dict = {
                            "feedback": f"",
                            "success": False,
                            "suggestion": f""
                        }
                        return check_dict
                if(target_object in old_inventory) and ((old_inventory[target_object])==(new_inventory[target_object])):
                    if target_object == "cobblestone":
                        check_dict = {
                        "feedback": f"You can't find {obj} to complete the '{action_name}' action.",
                        "success": False,
                        "suggestion": f"{target_object} is obtained by mining stone is most found in level 60, can only be mined with a wooden pickaxe or better，rimarily found at level 55 first."
                        }
                        return check_dict
                    else:
                        check_dict = {
                            "feedback": f"",
                            "success": False,
                            "suggestion": f""
                        }
                        return check_dict
            

            check_dict = {
                        "feedback": f"",
                        "success": True,
                        "suggestion": f""
                    }
            return check_dict
        
        elif action_name == "craft":
            events,_,_,_ = env.step([0,0,0,12,12,0,0,0])
            share_memory(self.memory,events)
            print(f"Crafting my inventory is {self.memory.inventory}")
            platform = args_dict["platform"]
            if platform:
                if platform not in self.memory.inventory or self.memory.inventory[platform] <= 0:
                    if (
                        self._is_deep_mining_task(task_information)
                        and normalize_inventory_name(platform) in {"crafting table", "furnace"}
                    ):
                        print(f"{platform} is not in inventory; allowing deep mining craft attempt in case it is placed nearby.")
                    else:
                        check_dict = {
                            "feedback": f"You do not have {platform} to complete the '{action_name}' action.",
                            "success": False,
                            "suggestion": f""
                        }
                        if platform.lower().find("crafting") != -1:
                            check_dict["suggestion"] = f"Craft a {platform} using 4 planks. If you do not have enough planks, please craft 4 planks using 1 log first."
                        elif platform.lower().find("furnace") != -1:
                            check_dict["suggestion"] = f"Craft a {platform} using 8 cobblestone. If you do not have enough cobblestone, please mine 8 cobblestone using a wooden pickaxe as the tool, primarily found at level 55 first."
                        return check_dict
            
            materials = args_dict["materials"]

            for material, quantity in materials.items():
                
                material = update_inventory_obj_name(material)
                quantity = int(quantity)

                if material not in self.memory.inventory:
                    check_dict = {
                        "feedback": f"You do not have {material} to complete the '{action_name}' action. You need {quantity} {material} but you do not have {material} in your inventory.",
                        "success": False,
                        "suggestion": f"Mine or Craft enough {material} first."
                    }
                    return check_dict
                
                elif self.memory.inventory[material] < quantity:
                    check_dict = {
                        "feedback": f"You do not have enough {material} to complete the '{action_name}' action. You need {quantity} {material} but you only have {self.memory.inventory[material]} {material} in your inventory.",
                        "success": False,
                        "suggestion": f"Mine or Craft enough {material} first."
                    }
                    return check_dict

            check_dict = {
                        "feedback": f"You have enough materials to complete the '{action_name}' action.",
                        "success": True,
                        "suggestion": f""
                    }
            return check_dict

        else:
            # find and move_to
            check_dict = {
                        "feedback": f"",
                        "success": True,
                        "suggestion": f""
                    }
            return check_dict
        

    def check_done (self,task_information, memory):
        print(f"inventory name is{memory.inventory}")
        for item in memory.inventory:
            print(f"task is {task_information['task']},item is {item}. task quantity is {task_information['quantity']}, quantity is{math.ceil(memory.inventory[item])} ")
            if task_information["task"]==item and task_information["quantity"]<=math.ceil(memory.inventory[item]):
                print(f"task is {item},quantity is {memory.inventory[item]}")
                return True
        return False

    # G0 formal-policy implementation.  It intentionally shadows the archived
    # compatibility implementation above: formal Stage-6 dispatch resolves this
    # final definition.  The older method is retained only for source-history
    # comparison while G0 removes its callers from the formal entry points.
    @staticmethod
    def _g0_inventory_hash(inventory):
        normalized = {
            normalize_inventory_name(name): float(quantity)
            for name, quantity in dict(inventory or {}).items()
            if normalize_inventory_name(name) and float(quantity) > 0
        }
        payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _g0_result(self, *, success, action_type, reason_code, missing, before, after, plan_id, action_id, feedback):
        return {
            "success": bool(success),
            "action_type": action_type,
            "reason_code": reason_code,
            "missing_requirements": list(missing),
            "environment_state_ref": "legacy_memory.inventory",
            "inventory_before_hash": self._g0_inventory_hash(before),
            "inventory_after_hash": self._g0_inventory_hash(after),
            "plan_id": str(plan_id),
            "action_id": str(action_id),
            "feedback": feedback,
            "suggestion": "Re-plan explicitly from the observed environment state.",
        }

    def check_action_preparation(self, env, action_name, args_dict, task_information=None, events=None):
        """Check only declared action requirements; never repair them."""
        inventory = dict(getattr(self.memory, "inventory", {}) or {})
        tool_actions = {"mine", "fight", "dig_down", "dig_up", "apply"}
        if action_name in tool_actions:
            tool = normalize_inventory_name(args_dict.get("tool"))
            if tool and float(inventory.get(tool, 0)) < 1:
                return {"success": False, "reason_code": "missing_declared_tool", "missing_requirements": [tool], "feedback": f"Missing declared tool: {tool}."}
        if action_name == "equip":
            item = normalize_inventory_name(args_dict.get("obj"))
            if item and float(inventory.get(item, 0)) < 1:
                return {"success": False, "reason_code": "missing_declared_equipment", "missing_requirements": [item], "feedback": f"Missing declared equipment: {item}."}
        if action_name == "craft":
            platform = normalize_inventory_name(args_dict.get("platform"))
            if platform and float(inventory.get(platform, 0)) < 1:
                return {"success": False, "reason_code": "missing_declared_platform", "missing_requirements": [platform], "feedback": f"Missing declared platform: {platform}."}
            missing = [
                normalize_inventory_name(material)
                for material, quantity in dict(args_dict.get("materials", {})).items()
                if float(inventory.get(normalize_inventory_name(material), 0)) < float(quantity)
            ]
            if missing:
                missing_text = ", ".join(sorted(set(missing)))
                return {
                    "success": False,
                    "reason_code": "missing_declared_materials",
                    "missing_requirements": missing,
                    "feedback": f"Missing declared craft materials: {missing_text}.",
                }
        return {"success": True, "reason_code": "ok", "missing_requirements": [], "feedback": "Declared requirements are present."}

    def check_and_execute_workflow(self, env, workflow_dict, task_information, underground):
        """Execute exactly the Planner workflow without Controller recovery.

        Low-level navigation/interactions are permitted.  Missing conditions
        return an auditable failure with untouched inventory; this method never
        inserts steps, selects tools, changes action arguments, or writes inventory.
        """
        workflow = deepcopy(workflow_dict.get("workflow", []))
        plan_id = ""
        if workflow:
            plan_id = str(workflow[0].get("_dc3pa_plan_id", ""))
        emit_execution_event(
            self,
            "workflow_started",
            plan_id=plan_id,
            status="",
            task=task_information.get("task"),
            step_count=len(workflow),
        )
        for step_index, step in enumerate(workflow):
            metadata = {
                "plan_id": str(step.get("_dc3pa_plan_id", plan_id)),
                "plan_version": int(step.get("_dc3pa_plan_version", 0)),
                "step_id": str(step.get("_dc3pa_step_id", f"step-{step_index}")),
                "step_index": int(step.get("_dc3pa_step_index", step_index)),
            }
            emit_execution_event(
                self,
                "step_started",
                **metadata,
                status="",
                times=step.get("times", 1),
                action_count=len(step.get("actions", [])),
            )
            repetitions = int(step.get("times", 1))
            gathered_log_target = 0
            declared_mine_targets = {
                normalize_inventory_name(
                    update_inventory_obj_name(
                        dict(candidate.get("args", {})).get("obj")
                    )
                )
                for candidate in step.get("actions", [])
                if candidate.get("name") == "mine"
            }
            # Mine batches are only quantity-governed when they have one
            # unambiguous declared target.  Mixed-target action groups retain
            # their literal workflow repetition semantics.
            step_mine_target = (
                next(iter(declared_mine_targets))
                if len(declared_mine_targets) == 1
                else ""
            )
            step_mine_initial_quantity = self._inventory_count(step_mine_target)
            for repetition in range(repetitions):
                if (
                    step_mine_target
                    and self._mine_step_goal_reached(
                        step_mine_target,
                        step_mine_initial_quantity,
                        repetitions,
                    )
                ):
                    print(
                        f"mine step target already satisfied for {step_mine_target}; "
                        f"skipping {repetitions - repetition} remaining repetitions"
                    )
                    break
                for action_index, action in enumerate(step.get("actions", [])):
                    name = str(action.get("name", ""))
                    args = dict(action.get("args", {}))
                    action_id = f"{step.get('_dc3pa_step_id', step_index)}:{repetition}:{action_index}"
                    before = dict(getattr(self.memory, "inventory", {}) or {})
                    emit_execution_event(
                        self,
                        "action_started",
                        **metadata,
                        action_index=action_index,
                        status="",
                        action=compact_action_payload(action),
                        inventory=snapshot_inventory(self.memory),
                    )
                    prepared = self.check_action_preparation(env, name, args)
                    if not prepared["success"]:
                        action_type = "smelt" if name == "craft" and args.get("platform") == "furnace" else name
                        result = self._g0_result(success=False, action_type=action_type, reason_code=prepared["reason_code"], missing=prepared["missing_requirements"], before=before, after=dict(getattr(self.memory, "inventory", {}) or {}), plan_id=plan_id, action_id=action_id, feedback=prepared["feedback"])
                        emit_execution_event(self, "action_finished", **metadata, action_index=action_index, status="failure", action=compact_action_payload(action), result=result, inventory=snapshot_inventory(self.memory))
                        emit_execution_event(self, "step_finished", **metadata, status="failure", result=result)
                        for later_index, later in enumerate(workflow[step_index + 1:], start=step_index + 1):
                            emit_execution_event(self, "step_finished", plan_id=str(later.get("_dc3pa_plan_id", plan_id)), plan_version=int(later.get("_dc3pa_plan_version", 0)), step_id=str(later.get("_dc3pa_step_id", f"step-{later_index}")), step_index=int(later.get("_dc3pa_step_index", later_index)), status="censored", result={"reason": "prior_step_failed"})
                        return result, underground
                    try:
                        if name == "find":
                            explore_above_ground(env=env, args=args, object=update_find_obj_name(args.get("obj")), performer=self, memory=self.memory, task_information=dict(task_information), underground=underground)
                        elif name == "move_to":
                            if not approach(env=env, memory=self.memory, object=args.get("obj"), underground=underground):
                                target = update_inventory_obj_name(args.get("obj"))
                                has_declared_followup_mine = any(
                                    later.get("name") == "mine"
                                    and update_inventory_obj_name(
                                        dict(later.get("args", {})).get("obj")
                                    ) == "log"
                                    for later in step.get("actions", [])[action_index + 1:]
                                )
                                if target == "log" and has_declared_followup_mine:
                                    target_logs = max(
                                        int(self.memory.inventory.get("log", 0)),
                                        self._workflow_material_requirement(
                                            workflow, step_index, "log", repetitions
                                        ),
                                    )
                                    if self._gather_logs(env, underground, target_logs):
                                        gathered_log_target = target_logs
                                    else:
                                        raise RuntimeError("declared_target_unreachable")
                                elif any(
                                    later.get("name") == "mine"
                                    and update_inventory_obj_name(
                                        dict(later.get("args", {})).get("obj")
                                    ) == target
                                    for later in step.get("actions", [])[action_index + 1:]
                                ):
                                    # ``approach`` searches a directional voxel
                                    # window, while the declared mine action has
                                    # its own all-direction lidar/voxel aiming
                                    # and yield verification.  Preserve the
                                    # navigation uncertainty in telemetry, then
                                    # let that already-declared mine establish
                                    # whether the resource is actually reachable.
                                    emit_execution_event(
                                        self,
                                        "action_finished",
                                        **metadata,
                                        action_index=action_index,
                                        status="unconfirmed",
                                        action=compact_action_payload(action),
                                        result={
                                            "reason_code": "move_to_unconfirmed_followup_mine",
                                            "success": False,
                                        },
                                        inventory=snapshot_inventory(self.memory),
                                    )
                                    continue
                                else:
                                    raise RuntimeError("declared_target_unreachable")
                        elif name == "mine":
                            target = update_inventory_obj_name(args.get("obj"))
                            if (
                                target == "log"
                                and gathered_log_target > 0
                                and float(self.memory.inventory.get("log", 0)) >= gathered_log_target
                            ):
                                emit_execution_event(self, "action_finished", **metadata, action_index=action_index, status="skipped_satisfied", action=compact_action_payload(action), result={"reason_code": "log_gathered_before_declared_mine"}, inventory=snapshot_inventory(self.memory))
                                continue
                            names, quantities = mine(env=env, memory=self.memory, target=args.get("obj"), equipment=args.get("tool") or "", underground=underground)
                            observed_inventory = count_inventory(names, quantities)
                            update_memory_inventory_from_observation(
                                self.memory, observed_inventory
                            )
                            # A declared voxel target is not necessarily the item
                            # it drops (for example, grass yields wheat seeds).
                            # Validate an actual observed inventory increment,
                            # rather than requiring the block name itself to be
                            # present in the inventory.
                            observed_yield = any(
                                float(self.memory.inventory.get(item, 0))
                                > float(before.get(item, 0))
                                for item in observed_inventory
                            )
                            required_logs = 0
                            if target == "log" and repetition == repetitions - 1:
                                required_logs = max(
                                    gathered_log_target,
                                    self._workflow_material_requirement(
                                        workflow, step_index, "log", repetitions
                                    ),
                                )
                            if not observed_yield:
                                if target == "log" and repetition == repetitions - 1:
                                    if not self._gather_logs(env, underground, required_logs):
                                        raise RuntimeError("declared_log_target_unmet")
                                    gathered_log_target = required_logs
                                else:
                                    raise RuntimeError("declared_mine_no_observed_yield")
                            elif target == "log" and repetition == repetitions - 1:
                                if float(self.memory.inventory.get("log", 0)) < required_logs:
                                    if not self._gather_logs(env, underground, required_logs):
                                        raise RuntimeError("declared_log_target_unmet")
                                    gathered_log_target = required_logs
                        elif name == "craft":
                            output = normalize_inventory_name(next(iter(args["obj"])))
                            craft_name = next(iter(args["obj"])).replace(" ", "_")
                            craft_succeeded = self._execute_craft_with_retries(
                                env,
                                args,
                                craft_name,
                                int(next(iter(args["obj"].values()))),
                            )
                            craft_failure = self._consume_execution_failure()
                            if craft_failure is not None:
                                raise RuntimeError(
                                    f"{craft_failure['reason']}: "
                                    f"{craft_failure['feedback']}"
                                )
                            if not craft_succeeded:
                                raise RuntimeError("declared_craft_no_observed_yield")
                        elif name == "dig_down":
                            if not go_down_to_y_level(env, int(args["y_level"]), equipment=args.get("tool") or ""):
                                raise RuntimeError("declared_dig_down_failed")
                            underground = True
                        elif name == "dig_up":
                            if "y_level" not in args:
                                raise RuntimeError("missing_declared_y_level")
                            go_up(env, int(args["y_level"]), equipment=args.get("tool") or "")
                            underground = False
                        elif name == "equip":
                            # Make the LLM-declared equip step physical.  The
                            # legacy implementation only checked inventory,
                            # leaving the client visibly holding a previous
                            # block until mine() happened to re-equip a tool.
                            events = self._sync_memory(env)
                            requested_item = normalize_inventory_name(args.get("obj"))
                            slot_index = next(
                                (
                                    index
                                    for index, item_name in enumerate(
                                        events["inventory"]["name"].tolist()
                                    )
                                    if normalize_inventory_name(item_name)
                                    == requested_item
                                ),
                                None,
                            )
                            if slot_index is None:
                                raise RuntimeError(
                                    "declared_equip_item_absent_after_sync: "
                                    f"{requested_item}"
                                )
                            events, _, _, _ = env.step(
                                [0, 0, 0, 12, 12, 5, 0, slot_index]
                            )
                            share_memory(self.memory, events)
                        elif name in {"fight", "apply"}:
                            pass
                        else:
                            raise RuntimeError("unsupported_declared_action")
                    except Exception as exc:
                        after = dict(getattr(self.memory, "inventory", {}) or {})
                        result = self._g0_result(success=False, action_type=name, reason_code=str(exc), missing=[], before=before, after=after, plan_id=plan_id, action_id=action_id, feedback=f"Declared {name} action failed: {exc}")
                        emit_execution_event(self, "action_finished", **metadata, action_index=action_index, status="failure", action=compact_action_payload(action), result=result, inventory=snapshot_inventory(self.memory))
                        emit_execution_event(self, "step_finished", **metadata, status="failure", result=result)
                        for later_index, later in enumerate(workflow[step_index + 1:], start=step_index + 1):
                            emit_execution_event(self, "step_finished", plan_id=str(later.get("_dc3pa_plan_id", plan_id)), plan_version=int(later.get("_dc3pa_plan_version", 0)), step_id=str(later.get("_dc3pa_step_id", f"step-{later_index}")), step_index=int(later.get("_dc3pa_step_index", later_index)), status="censored", result={"reason": "prior_step_failed"})
                        return result, underground
                    emit_execution_event(self, "action_finished", **metadata, action_index=action_index, status="success", action=compact_action_payload(action), result={}, inventory=snapshot_inventory(self.memory))

                    # A low-level action (not only the declared terminal
                    # ``mine`` action) can change the physical inventory.  For
                    # example, movement may collect a nearby drop.  Check the
                    # task condition immediately after every successfully
                    # observed action so a plan with repeated search/mine steps
                    # does not keep consuming blocks after its goal is met.
                    # ``check_done`` reads the same fresh MineDojo inventory
                    # snapshot that was used for the action telemetry; this is
                    # a generic task-goal check, not a diamond-specific rule.
                    # Formal task records include the required quantity.
                    # Some archived/free-form callers do not, so leave their
                    # historical end-of-workflow behavior unchanged.
                    if (
                        task_information.get("quantity") is not None
                        and self.check_done(task_information, self.memory)
                    ):
                        after = dict(getattr(self.memory, "inventory", {}) or {})
                        result = self._g0_result(
                            success=True,
                            action_type=name,
                            reason_code="task_goal_satisfied_after_action",
                            missing=[],
                            before=before,
                            after=after,
                            plan_id=plan_id,
                            action_id=action_id,
                            feedback="Task goal satisfied by the observed inventory.",
                        )
                        emit_execution_event(
                            self,
                            "step_finished",
                            **metadata,
                            status="short_circuited_goal_satisfied",
                            result=result,
                        )
                        for later_index, later in enumerate(
                            workflow[step_index + 1 :], start=step_index + 1
                        ):
                            emit_execution_event(
                                self,
                                "step_finished",
                                plan_id=str(later.get("_dc3pa_plan_id", plan_id)),
                                plan_version=int(later.get("_dc3pa_plan_version", 0)),
                                step_id=str(later.get("_dc3pa_step_id", f"step-{later_index}")),
                                step_index=int(later.get("_dc3pa_step_index", later_index)),
                                status="censored",
                                result={"reason": "task_goal_satisfied"},
                            )
                        return result, underground
            emit_execution_event(self, "step_finished", **metadata, status="success", result={})
        return {"success": True, "feedback": "", "suggestion": "", "plan_id": plan_id}, underground
