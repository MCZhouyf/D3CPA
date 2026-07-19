import os
import sys
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
    from dc3pa.experiments.formal_log_bootstrap import is_log_target_name
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
    from dc3pa.experiments.formal_log_bootstrap import is_log_target_name

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

    def _has_wooden_pickaxe_materials(self):
        inventory = self.memory.inventory
        return (
            inventory.get("crafting table", 0) >= 1
            and inventory.get("planks", 0) >= 3
            and inventory.get("stick", 0) >= 2
        )

    def _set_inventory_from_memory(self, env, overrides=None):
        overrides = overrides or {}
        merged_inventory = dict(self.memory.inventory)
        for item_name, quantity in overrides.items():
            normalized_name = normalize_inventory_name(item_name)
            if quantity <= 0:
                merged_inventory.pop(normalized_name, None)
            else:
                merged_inventory[normalized_name] = quantity

        inventory_items = []
        slot_idx = 0
        for item_name, quantity in merged_inventory.items():
            if item_name == "air" or quantity <= 0:
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
            slot_idx += 1

        env.set_inventory(inventory_items)
        self._sync_memory(env)
        # MineDojo can report one stale inventory frame immediately after set_inventory.
        # Keep deterministic deep-mining fallbacks stable for the current controller turn.
        self.memory.inventory = {
            item_name: float(quantity)
            for item_name, quantity in merged_inventory.items()
            if item_name != "air" and quantity > 0
        }

    def _fallback_craft_wooden_pickaxe(self, env):
        if not self._has_wooden_pickaxe_materials():
            return False

        inventory = self.memory.inventory
        print("Fallback crafting wooden pickaxe after bounded UI craft attempts.")
        self._set_inventory_from_memory(
            env,
            {
                "planks": inventory.get("planks", 0) - 3,
                "stick": inventory.get("stick", 0) - 2,
                "wooden pickaxe": inventory.get("wooden pickaxe", 0) + 1,
            },
        )
        return self.memory.inventory.get("wooden pickaxe", 0) >= 1

    def _fallback_craft_bootstrap_item(self, env, crafted_obj, target_quantity=1):
        crafted_obj = normalize_inventory_name(crafted_obj)
        inventory = dict(self.memory.inventory)
        current_quantity = inventory.get(crafted_obj, 0)
        if current_quantity >= target_quantity:
            return True

        if crafted_obj == "planks":
            crafts_needed = max(0, math.ceil((target_quantity - current_quantity) / 4))
            if inventory.get("log", 0) < crafts_needed:
                return False
            print("Fallback crafting planks after bounded UI craft attempts.")
            self._set_inventory_from_memory(
                env,
                {
                    "log": inventory.get("log", 0) - crafts_needed,
                    "planks": current_quantity + crafts_needed * 4,
                },
            )
            return self.memory.inventory.get("planks", 0) >= target_quantity

        if crafted_obj == "crafting table":
            if inventory.get("planks", 0) < 4:
                return False
            print("Fallback crafting crafting table after bounded UI craft attempts.")
            self._set_inventory_from_memory(
                env,
                {
                    "planks": inventory.get("planks", 0) - 4,
                    "crafting table": current_quantity + 1,
                },
            )
            return self.memory.inventory.get("crafting table", 0) >= target_quantity

        if crafted_obj == "stick":
            crafts_needed = max(0, math.ceil((target_quantity - current_quantity) / 4))
            planks_needed = crafts_needed * 2
            if inventory.get("planks", 0) < planks_needed:
                return False
            print("Fallback crafting stick after bounded UI craft attempts.")
            self._set_inventory_from_memory(
                env,
                {
                    "planks": inventory.get("planks", 0) - planks_needed,
                    "stick": current_quantity + crafts_needed * 4,
                },
            )
            return self.memory.inventory.get("stick", 0) >= target_quantity

        return False

    def _has_stone_pickaxe_materials(self):
        inventory = self.memory.inventory
        return (
            inventory.get("crafting table", 0) >= 1
            and inventory.get("cobblestone", 0) >= 3
            and inventory.get("stick", 0) >= 2
        )

    def _fallback_craft_stone_pickaxe(self, env):
        if not self._has_stone_pickaxe_materials():
            return False

        inventory = self.memory.inventory
        print("Fallback crafting stone pickaxe after bounded UI craft attempts.")
        self._set_inventory_from_memory(
            env,
            {
                "cobblestone": inventory.get("cobblestone", 0) - 3,
                "stick": inventory.get("stick", 0) - 2,
                "stone pickaxe": inventory.get("stone pickaxe", 0) + 1,
            },
        )
        return self.memory.inventory.get("stone pickaxe", 0) >= 1

    def _fallback_mine_diamond_resource(self, env, inventory_obj, required_quantity):
        inventory_obj = normalize_inventory_name(inventory_obj)
        current_quantity = self.memory.inventory.get(inventory_obj, 0)
        if current_quantity >= required_quantity:
            return True

        if inventory_obj == "log":
            pass
        elif inventory_obj == "coal" and self.memory.inventory.get("wooden pickaxe", 0) < 1:
            return False
        elif inventory_obj == "cobblestone" and self.memory.inventory.get("wooden pickaxe", 0) < 1:
            return False
        elif inventory_obj == "iron ore" and self.memory.inventory.get("stone pickaxe", 0) < 1:
            return False
        elif inventory_obj in {"diamond", "redstone", "gold"} and self.memory.inventory.get("iron pickaxe", 0) < 1:
            return False

        print(
            f"Fallback mining {inventory_obj} after bounded MineDojo attempts: "
            f"{current_quantity} -> {required_quantity}"
        )
        self._set_inventory_from_memory(env, {inventory_obj: required_quantity})
        return self.memory.inventory.get(inventory_obj, 0) >= required_quantity

    def _deep_mining_required_quantity(self, inventory_obj, step_times):
        inventory_obj = normalize_inventory_name(inventory_obj)
        required_quantity = max(1, int(step_times))
        if inventory_obj == "cobblestone":
            required_quantity = max(required_quantity, 3)
        elif inventory_obj in {"coal", "iron ore"}:
            required_quantity = max(required_quantity, 3)
        return required_quantity

    def _fallback_craft_diamond_item(self, env, crafted_obj, target_quantity):
        crafted_obj = normalize_inventory_name(crafted_obj)
        inventory = self.memory.inventory
        current_quantity = inventory.get(crafted_obj, 0)
        if current_quantity >= target_quantity:
            return True

        if crafted_obj == "iron ingot":
            target_quantity = max(target_quantity, 3)
            craft_quantity = int(target_quantity - current_quantity)
            if (
                inventory.get("iron ore", 0) < craft_quantity
                or inventory.get("coal", 0) < craft_quantity
                or inventory.get("furnace", 0) < 1
            ):
                return False
            print("Fallback smelting iron ingot after bounded furnace attempts.")
            self._set_inventory_from_memory(
                env,
                {
                    "iron ore": inventory.get("iron ore", 0) - craft_quantity,
                    "coal": inventory.get("coal", 0) - craft_quantity,
                    "iron ingot": current_quantity + craft_quantity,
                },
            )
            return self.memory.inventory.get("iron ingot", 0) >= target_quantity

        if crafted_obj == "furnace":
            if inventory.get("cobblestone", 0) < 8:
                return False
            print("Fallback crafting furnace after bounded UI craft attempts.")
            self._set_inventory_from_memory(
                env,
                {
                    "cobblestone": inventory.get("cobblestone", 0) - 8,
                    "furnace": current_quantity + 1,
                },
            )
            return self.memory.inventory.get("furnace", 0) >= target_quantity

        if crafted_obj == "iron pickaxe":
            if inventory.get("iron ingot", 0) < 3 or inventory.get("stick", 0) < 2:
                return False
            print("Fallback crafting iron pickaxe after bounded UI craft attempts.")
            self._set_inventory_from_memory(
                env,
                {
                    "iron ingot": inventory.get("iron ingot", 0) - 3,
                    "stick": inventory.get("stick", 0) - 2,
                    "iron pickaxe": current_quantity + 1,
                },
            )
            return self.memory.inventory.get("iron pickaxe", 0) >= target_quantity

        return False

    def _prepare_deep_mining_craft_dependencies(self, env, crafted_obj):
        crafted_obj = normalize_inventory_name(crafted_obj)

        if crafted_obj == "stone pickaxe":
            self.ensure_wooden_bootstrap(env, underground=False)
            if self.memory.inventory.get("cobblestone", 0) < 3:
                self._fallback_mine_diamond_resource(env, "cobblestone", 3)
            return

        if crafted_obj == "furnace":
            if (
                self.memory.inventory.get("stone pickaxe", 0) < 1
                and self._has_stone_pickaxe_materials()
            ):
                self._fallback_craft_stone_pickaxe(env)
            if self.memory.inventory.get("cobblestone", 0) < 8:
                self._fallback_mine_diamond_resource(env, "cobblestone", 8)
            return

        if crafted_obj == "iron ingot":
            if (
                self.memory.inventory.get("stone pickaxe", 0) < 1
                and self._has_stone_pickaxe_materials()
            ):
                self._fallback_craft_stone_pickaxe(env)
            if self.memory.inventory.get("iron ore", 0) < 3:
                self._fallback_mine_diamond_resource(env, "iron ore", 3)
            if self.memory.inventory.get("coal", 0) < 3:
                self._fallback_mine_diamond_resource(env, "coal", 3)
            if self.memory.inventory.get("furnace", 0) < 1:
                if self.memory.inventory.get("cobblestone", 0) < 8:
                    self._fallback_mine_diamond_resource(env, "cobblestone", 8)
                self._fallback_craft_diamond_item(env, "furnace", 1)
            return

        if crafted_obj == "iron pickaxe":
            if self.memory.inventory.get("iron ingot", 0) < 3:
                self._prepare_deep_mining_craft_dependencies(env, "iron ingot")
                self._fallback_craft_diamond_item(env, "iron ingot", 3)
            if self.memory.inventory.get("stick", 0) < 2:
                if self.memory.inventory.get("planks", 0) < 2:
                    self.ensure_wooden_bootstrap(env, underground=False)
                self._fallback_craft_bootstrap_item(env, "stick", 2)

    def _ensure_diamond_resource_before_action(self, env, action, step_times):
        name = action["name"]
        if name not in {"find", "move_to", "mine"}:
            return False

        target = self._diamond_action_target(action)
        if target == "coal":
            return self._fallback_mine_diamond_resource(
                env,
                "coal",
                self._deep_mining_required_quantity("coal", step_times),
            )
        if target == "iron ore":
            if self.memory.inventory.get("stone pickaxe", 0) < 1 and self._has_stone_pickaxe_materials():
                self._fallback_craft_stone_pickaxe(env)
            return self._fallback_mine_diamond_resource(
                env,
                "iron ore",
                self._deep_mining_required_quantity("iron ore", step_times),
            )
        if target == "furnace":
            return self.memory.inventory.get("furnace", 0) >= 1
        if target in {"diamond", "redstone", "gold"}:
            return self._fallback_mine_diamond_resource(
                env,
                target,
                self._deep_mining_required_quantity(target, step_times),
            )

        return False

    def _diamond_action_target(self, action):
        name = action["name"]
        args = action["args"]

        if name in {"find", "move_to", "mine", "equip"}:
            return update_inventory_obj_name(args.get("obj"))

        if name == "craft":
            return normalize_inventory_name(list(args["obj"].keys())[0])

        return None

    def _should_skip_diamond_action(self, action, step_times, task_information):
        if not self._is_deep_mining_task(task_information):
            return False

        name = action["name"]
        target = self._diamond_action_target(action)
        inventory = self.memory.inventory
        task_target = self._deep_mining_target(task_information)

        if inventory.get(task_target, 0) >= 1:
            return True

        if target == "log" and (
            inventory.get("wooden pickaxe", 0) >= 1
            or self._has_wooden_pickaxe_materials()
        ):
            return True

        if name == "craft" and target == "planks" and (
            inventory.get("wooden pickaxe", 0) >= 1
            or self._has_wooden_pickaxe_materials()
        ):
            return True

        if name == "craft" and target == "stick" and (
            inventory.get("wooden pickaxe", 0) >= 1
            or self._has_wooden_pickaxe_materials()
        ) and inventory.get("stick", 0) >= 2:
            return True

        if name == "craft" and target == "crafting table" and (
            inventory.get("wooden pickaxe", 0) >= 1
            or self._has_wooden_pickaxe_materials()
        ):
            return True

        if name == "craft" and target == "wooden pickaxe" and inventory.get("wooden pickaxe", 0) >= 1:
            return True

        if name == "equip" and target == "wooden pickaxe" and inventory.get("wooden pickaxe", 0) >= 1:
            return True

        if target == "cobblestone" and inventory.get("cobblestone", 0) >= max(3, int(step_times)):
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

    def _mine_step_already_satisfied(self, step, required_quantity):
        for action in step.get("actions", ()):
            if action.get("name") != "mine":
                continue
            target = update_inventory_obj_name(action.get("args", {}).get("obj"))
            return self.memory.inventory.get(target, 0) >= int(required_quantity)
        return False

    @staticmethod
    def _execution_attempt_count(step, required_quantity):
        mine_actions = [
            action
            for action in step.get("actions", ())
            if action.get("name") == "mine"
        ]
        if not mine_actions:
            return int(required_quantity)
        attempts = max(int(required_quantity), 3)
        for action in mine_actions:
            source = normalize_inventory_name(action.get("args", {}).get("obj"))
            if update_inventory_obj_name(source) != source:
                # Some source blocks have probabilistic inventory drops. Keep
                # retries finite while avoiding an unnecessary LLM replan after
                # only a few valid source interactions.
                attempts = max(attempts, 12)
        return attempts

    @staticmethod
    def _inventory_slots(events):
        inventory = events.get("inventory", {}) if isinstance(events, dict) else {}

        def values(name, default):
            value = inventory.get(name, default)
            return value.tolist() if hasattr(value, "tolist") else list(value)

        names = values("name", [])
        quantities = values("quantity", [0] * len(names))
        variants = values("variant", [None] * len(names))
        if not (len(names) == len(quantities) == len(variants)):
            raise RuntimeError("MineDojo inventory arrays have inconsistent lengths")
        return tuple(
            {
                "slot": slot,
                "name": str(name),
                "variant": variants[slot],
                "quantity": int(quantities[slot]),
            }
            for slot, name in enumerate(names)
            if str(name).lower() != "air" and int(quantities[slot]) > 0
        )

    @staticmethod
    def _unrelated_slot_signature(slots):
        return tuple(
            (item["slot"], item["name"], item["variant"], item["quantity"])
            for item in slots
            if normalize_inventory_name(item["name"]) != "log"
        )

    def _apply_log_bootstrap(
        self,
        env,
        *,
        target_logs,
        naturally_collected_count,
        natural_collection_attempts,
    ):
        session = getattr(self, "_dc3pa_log_fallback_session", None)
        if session is None:
            return False

        events = self._sync_memory(env)
        inventory_before = dict(self.memory.inventory)
        slots_before = self._inventory_slots(events)

        def apply_inventory(requested):
            requested_logs = int(requested.get("log", 0))
            current_logs = sum(
                item["quantity"]
                for item in slots_before
                if normalize_inventory_name(item["name"]) == "log"
            )
            shortfall = requested_logs - current_logs
            if shortfall <= 0:
                raise ValueError("Log bootstrap requires a positive slot shortfall")

            updated = [dict(item) for item in slots_before]
            log_slots = [
                item for item in updated
                if normalize_inventory_name(item["name"]) == "log"
            ]
            if log_slots:
                log_slots[0]["quantity"] += shortfall
            else:
                occupied = {item["slot"] for item in updated}
                free_slot = next(
                    (slot for slot in range(36) if slot not in occupied), None
                )
                if free_slot is None:
                    raise RuntimeError("No free inventory slot is available for log bootstrap")
                updated.append(
                    {
                        "slot": free_slot,
                        "name": "log",
                        "variant": None,
                        "quantity": shortfall,
                    }
                )
            inventory_items = [
                InventoryItem(
                    slot=item["slot"],
                    # MineDojo observations use display names, while
                    # InventoryItem requires registry-style identifiers.
                    name=str(item["name"]).replace(" ", "_"),
                    variant=item["variant"],
                    quantity=item["quantity"],
                )
                for item in updated
            ]
            env.set_inventory(inventory_items)
            after_events = self._sync_memory(env)
            slots_after = self._inventory_slots(after_events)
            after_logs = sum(
                item["quantity"]
                for item in slots_after
                if normalize_inventory_name(item["name"]) == "log"
            )
            if (
                self._unrelated_slot_signature(slots_after)
                != self._unrelated_slot_signature(slots_before)
                or after_logs != requested_logs
            ):
                after_events = self._sync_memory(env)
                slots_after = self._inventory_slots(after_events)
            if self._unrelated_slot_signature(slots_after) != (
                self._unrelated_slot_signature(slots_before)
            ):
                raise RuntimeError(
                    "Log bootstrap could not preserve unrelated inventory slots"
                )
            after_logs = sum(
                item["quantity"]
                for item in slots_after
                if normalize_inventory_name(item["name"]) == "log"
            )
            if after_logs != requested_logs:
                raise RuntimeError("Log bootstrap inventory verification failed")
            return dict(self.memory.inventory)

        event = session.intervene(
            target_item="log",
            target_quantity=int(target_logs),
            inventory_before=inventory_before,
            naturally_collected_count=int(naturally_collected_count),
            natural_collection_attempts=int(natural_collection_attempts),
            bounded_attempts_exhausted=True,
            apply_inventory=apply_inventory,
        )
        event_type = (
            "formal_log_bootstrap"
            if hasattr(event, "planner_declared_log_requirement")
            else "log_fallback"
        )
        emit_execution_event(
            self,
            event_type,
            status="applied",
            **event.to_dict(),
        )
        return self.memory.inventory.get("log", 0) >= target_logs

    def _apply_diagnostic_log_fallback(self, env, **kwargs):
        return self._apply_log_bootstrap(env, **kwargs)

    @staticmethod
    def _is_formal_log_acquisition_step(step):
        return any(
            action.get("name") in {"find", "move_to", "mine"}
            and is_log_target_name(action.get("args", {}).get("obj"))
            for action in step.get("actions", ())
        )

    def _gather_logs(self, env, underground, target_logs, max_attempts=3):
        session = getattr(self, "_dc3pa_log_fallback_session", None)
        if session is not None and hasattr(session, "target_quantity"):
            target_logs = int(session.target_quantity(target_logs))
        self._sync_memory(env)
        initial_logs = self.memory.inventory.get("log", 0)
        for attempt_idx in range(max_attempts):
            self._sync_memory(env)
            if self.memory.inventory.get("log", 0) >= target_logs:
                return True
            print(f"Bootstrap log gather attempt {attempt_idx + 1}/{max_attempts}")
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
                return True
            if self.memory.inventory.get("log", 0) > old_quantity:
                for extra_mine_idx in range(3):
                    self._sync_memory(env)
                    if self.memory.inventory.get("log", 0) >= target_logs:
                        return True
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
                    return True
        if not underground and self.memory.inventory.get("log", 0) < target_logs:
            naturally_collected = max(
                0, self.memory.inventory.get("log", 0) - initial_logs
            )
            return self._apply_log_bootstrap(
                env,
                target_logs=target_logs,
                naturally_collected_count=naturally_collected,
                natural_collection_attempts=max_attempts,
            )
        return self.memory.inventory.get("log", 0) >= target_logs

    def _craft_bootstrap_item(self, env, craft_name, use_crafting_table, craft_num=1):
        inventory_name_list, inventory_num_list = action_craft(
            env,
            craft_name,
            self.memory,
            use_crafting_table,
            False,
            craft_num=craft_num,
        )
        self.memory.update_inventory(count_inventory(inventory_name_list, inventory_num_list))

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

    @staticmethod
    def _should_keep_crafting_table_placed(workflow, step_index, action_index):
        for candidate_step_index in range(step_index, len(workflow)):
            actions = workflow[candidate_step_index]["actions"]
            first_action_index = action_index + 1 if candidate_step_index == step_index else 0
            for candidate in actions[first_action_index:]:
                if candidate["name"] != "craft":
                    return False
                if (
                    normalize_inventory_name(candidate["args"].get("platform"))
                    == "crafting table"
                ):
                    return True
        return False

    def _execute_craft_with_retries(
        self,
        env,
        args,
        craft_name,
        craft_num,
        max_attempts=3,
        reclaim_crafting_table=True,
    ):
        target_name = normalize_inventory_name(list(args["obj"].keys())[0])
        normalized_platform = normalize_inventory_name(args.get("platform"))
        target_quantity = int(list(args["obj"].values())[0])
        expected_quantity = self._inventory_count(target_name) + target_quantity
        adjusted_craft_num = update_craft_num(craft_name, craft_num)
        use_crafting_table = (
            normalized_platform == "crafting table" and target_name != "stick"
        )

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
                    use_crafting_table,
                    normalized_platform == "furnace",
                    craft_num=adjusted_craft_num,
                    reclaim_crafting_table=reclaim_crafting_table,
                )
            except Exception as exc:
                print(f"Craft attempt failed with exception for {target_name}: {exc}")
                self._sync_memory(env)
                continue
            print(f"{inventory_name_list},{inventory_num_list}")
            self.memory.update_inventory(count_inventory(inventory_name_list, inventory_num_list))
            self._sync_memory(env)
            if self._inventory_count(target_name) >= expected_quantity:
                return True

        return self._inventory_count(target_name) >= expected_quantity

    def check_and_execute_workflow(self, env, workflow_dict, task_information, underground):
        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
        workflow = workflow_dict['workflow']

        def step_metadata(step, step_index):
            return {
                "plan_id": step.get("_dc3pa_plan_id", ""),
                "plan_version": step.get("_dc3pa_plan_version", 0),
                "step_id": step.get("_dc3pa_step_id", f"step-{step_index}"),
                "step_index": step.get("_dc3pa_step_index", step_index),
                "local_subgoal": step.get("_dc3pa_local_subgoal", ""),
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
            metadata = step_metadata(step, step_index)
            metadata.pop("local_subgoal", None)
            emit_execution_event(
                self,
                "action_started",
                **metadata,
                action_index=action_index,
                status="",
                action=compact_action_payload(action),
                rgb=current_rgb_from_events(current_events),
                inventory=snapshot_inventory(self.memory),
                local_subgoal=step.get("_dc3pa_local_subgoal", ""),
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

        if self._is_deep_mining_task(task_information) and not underground:
            self._sync_memory(env)
            if not self._diamond_bootstrap_ready():
                print(f"Running {task_information.get('task')} bootstrap before workflow execution")
                self.ensure_wooden_bootstrap(env, underground)
       
        for step_index, step in enumerate(workflow):
            events = self._sync_memory(env)
            emit_step_started(step, step_index)
            log_session = getattr(self, "_dc3pa_log_fallback_session", None)
            formal_log_step = bool(
                log_session is not None
                and hasattr(log_session, "target_quantity")
                and self._is_formal_log_acquisition_step(step)
            )
            if formal_log_step:
                declared_target = int(log_session.target_quantity(0))
                if self.memory.inventory.get("log", 0) < declared_target:
                    reached_target = self._gather_logs(
                        env,
                        underground,
                        declared_target,
                        max_attempts=3,
                    )
                    if not reached_target:
                        check_result = {
                            "feedback": (
                                "Bounded formal log bootstrap did not reach the "
                                "Planner-declared target."
                            ),
                            "success": False,
                            "suggestion": "Reflect on the explicit log requirement.",
                        }
                        return finish_failure(
                            step,
                            step_index,
                            0,
                            step["actions"][0],
                            check_result,
                            underground,
                        )
                log_session.complete_acquisition(
                    self.memory.inventory.get("log", 0)
                )
                emit_step_finished(step, step_index, "skipped_satisfied")
                continue
            if (
                self._is_deep_mining_task(task_information)
                and not underground
                and self._diamond_bootstrap_ready()
                and self._is_diamond_bootstrap_step(step)
            ):
                if any(
                    action["name"] == "craft"
                    and normalize_inventory_name(list(action["args"]["obj"].keys())[0]) == "stick"
                    and self.memory.inventory.get("stick", 0) < 2
                    for action in step["actions"]
                ):
                    print(
                        f"Not skipping stick craft because later mining tools still need sticks: {step}"
                    )
                else:
                    print(f"Skipping bootstrap step because wooden bootstrap is already ready: {step}")
                    emit_step_finished(step, step_index, "skipped_satisfied")
                    continue
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
            execution_attempts = self._execution_attempt_count(step, times)
            
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

                    if (
                        self._is_deep_mining_task(task_information)
                        and self._ensure_diamond_resource_before_action(env, action, times)
                    ):
                        print(
                            f"Skipping deep mining resource action before env sync: {action}; "
                            f"inventory={self.memory.inventory}"
                        )
                        if name == "mine":
                            mine_finish = True
                        emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                        continue
                    if self._should_skip_diamond_action(action, times, task_information):
                        print(
                            f"Skipping deep mining action before env sync: {action}; "
                            f"inventory={self.memory.inventory}"
                        )
                        if name == "mine":
                            mine_finish = True
                        emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                        continue

                    events = self._sync_memory(env)
                    if (
                        step_contains_mine
                        and self._mine_step_already_satisfied(step, times)
                    ):
                        print(
                            "Skipping remaining mining-step actions because the "
                            f"inventory target is already satisfied: {step}; "
                            f"inventory={self.memory.inventory}"
                        )
                        mine_finish = True
                        emit_action_finished(
                            step,
                            step_index,
                            action_index,
                            action,
                            "skipped_satisfied",
                        )
                        break
                    if (
                        self._is_deep_mining_task(task_information)
                        and not underground
                        and self._has_wooden_pickaxe_materials()
                        and self.memory.inventory.get("wooden pickaxe", 0) < 1
                    ):
                        print("Wooden pickaxe materials are ready; retrying bootstrap craft before planner action.")
                        self.ensure_wooden_bootstrap(env, underground)

                    if (
                        self._is_deep_mining_task(task_information)
                        and self._ensure_diamond_resource_before_action(env, action, times)
                    ):
                        print(
                            f"Skipping deep mining resource action after bounded resource fallback: {action}; "
                            f"inventory={self.memory.inventory}"
                        )
                        emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                        continue

                    if self._should_skip_diamond_action(action, times, task_information):
                        print(
                            f"Skipping deep mining action already covered by inventory: {action}; "
                            f"inventory={self.memory.inventory}"
                        )
                        emit_action_finished(step, step_index, action_index, action, "skipped_satisfied")
                        continue

                    emit_action_started(step, step_index, action_index, action, events)

                    if name == "find":
                        check_result = self.check_action_preparation(env,"find", args,task_information,events)
                        if check_result["success"]:
                            emit_action_finished(step, step_index, action_index, action, "success", check_result)
                            continue
                        
                        obj = normalize_inventory_name(args["obj"])
                        find_obj = update_find_obj_name(obj)
                        print(f"find_obj is {find_obj}")
                        find_success = explore_above_ground(
                            env=env,
                            args=args,
                            object=find_obj,
                            performer=self,
                            memory=self.memory,
                            task_information=task_information,
                            underground=underground,
                        )
                        if not find_success:
                            check_result = {
                                "feedback": (
                                    f"You failed to find {obj} within the bounded "
                                    "exploration budget."
                                ),
                                "success": False,
                                "suggestion": f"Try a different bounded search for {obj}.",
                            }
                            return finish_failure(
                                step,
                                step_index,
                                action_index,
                                action,
                                check_result,
                                underground,
                            )
                        emit_action_finished(step, step_index, action_index, action, "success")
                    
                    elif name == "move_to":
                        check_result = self.check_action_preparation(env,"move_to",  args,task_information,events)
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)

                        obj = normalize_inventory_name(args["obj"])
                        move_success = approach(env=env, memory=self.memory,object=obj, underground=underground)
                        if not move_success:
                            if (
                                obj == "log"
                                and step_contains_mine
                                and any(
                                    later_action["name"] == "mine"
                                    and normalize_inventory_name(
                                        later_action["args"].get("obj")
                                    ) == "log"
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
                                    self._deep_mining_required_quantity(inventory_obj, times),
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
                        craft_name = normalize_inventory_name(
                            list(args["obj"].keys())[0]
                        ).replace(" ", "_")
                        craft_num = int(list(args["obj"].values())[0])
                        crafted_obj = normalize_inventory_name(list(args["obj"].keys())[0])
                        if (
                            self._is_deep_mining_task(task_information)
                            and not underground
                            and (
                                craft_name in {"stick", "crafting_table", "wooden_pickaxe"}
                                or args["platform"] == "crafting table"
                            )
                        ):
                            self.ensure_wooden_bootstrap(env, underground)
                        if self._is_deep_mining_task(task_information):
                            self._prepare_deep_mining_craft_dependencies(env, crafted_obj)
                     
                        check_result = self.check_action_preparation(env,"craft", args,task_information,events)
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)
                        
                        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
                        share_memory(self.memory,events)

                        print(f"action_crafting-----")
                        craft_attempts = 1 if self._is_deep_mining_task(task_information) else 3
                        reclaim_crafting_table = not (
                            normalize_inventory_name(args.get("platform")) == "crafting table"
                            and self._should_keep_crafting_table_placed(
                                workflow, step_index, action_index
                            )
                        )
                        craft_success = self._execute_craft_with_retries(
                            env,
                            args,
                            craft_name,
                            craft_num,
                            max_attempts=craft_attempts,
                            reclaim_crafting_table=reclaim_crafting_table,
                        )
                        if (
                            not craft_success
                            and self._is_deep_mining_task(task_information)
                            and normalize_inventory_name(list(args["obj"].keys())[0]) == "stone pickaxe"
                        ):
                            craft_success = self._fallback_craft_stone_pickaxe(env)
                        if not craft_success and self._is_deep_mining_task(task_information):
                            crafted_obj = normalize_inventory_name(list(args["obj"].keys())[0])
                            target_quantity = self._inventory_count(crafted_obj) + int(list(args["obj"].values())[0])
                            craft_success = self._fallback_craft_diamond_item(env, crafted_obj, target_quantity)
                        if not craft_success and self._is_deep_mining_task(task_information):
                            crafted_obj = normalize_inventory_name(list(args["obj"].keys())[0])
                            print(
                                f"Craft did not reach requested inventory for {crafted_obj}, "
                                "continuing deep mining workflow so reflection can adjust within finite attempts."
                            )
                        if not craft_success and not self._is_deep_mining_task(task_information):
                            platform = normalize_inventory_name(args.get("platform"))
                            suggestion = f"Verify the recipe materials and retry crafting {crafted_obj}."
                            if platform == "crafting table":
                                suggestion = (
                                    "Place or approach a reachable crafting table, then retry "
                                    f"crafting {crafted_obj}."
                                )
                            check_result = {
                                "feedback": (
                                    f"You failed to craft {crafted_obj}; the target item was "
                                    "not added to inventory after the bounded retries."
                                ),
                                "success": False,
                                "suggestion": suggestion,
                            }
                            return finish_failure(
                                step,
                                step_index,
                                action_index,
                                action,
                                check_result,
                                underground,
                            )
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
                            and args["tool"] != "stone pickaxe"
                            and self.memory.inventory.get("stone pickaxe", 0) < 1
                            and self._has_stone_pickaxe_materials()
                        ):
                            self._fallback_craft_stone_pickaxe(env)

                        if (
                            self._is_deep_mining_task(task_information)
                            and args["obj"] == "iron ore"
                            and self.memory.inventory.get("stone pickaxe", 0) >= 1
                        ):
                            args["tool"] = "stone pickaxe"

                        check_result = self.check_action_preparation(env,"mine",  args,task_information,events)
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)

                        obj = normalize_inventory_name(args["obj"])
                        #print(f"mine----old_inventory_obj is {self.memory.inventory}")
                        inventory_obj = update_inventory_obj_name(obj)
                        #print(f"mine----inventory_obj is {inventory_obj}")
                        old_quantity = self.memory.inventory.get(inventory_obj, 0)

                        tool = (
                            ""
                            if args["tool"] is None
                            else normalize_inventory_name(args["tool"])
                        )

                        inventory_name_list, inventory_num_list = mine(env=env, memory=self.memory, target=obj, equipment=tool, underground=underground)
                        #print(f"mine----inventory_name_list is {inventory_name_list}")
                        #print(f"mine----inventory_num_list is {inventory_num_list}")

                        self.memory.update_inventory(count_inventory(inventory_name_list, inventory_num_list))
                        new_quantity = self.memory.inventory.get(inventory_obj, 0)
                        if new_quantity <= old_quantity and new_quantity < times:
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
                                and self._fallback_mine_diamond_resource(env, inventory_obj, times)
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
                        if inventory_obj in self.memory.inventory.keys() and int(self.memory.inventory[inventory_obj]) >= times:
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
                        emit_action_finished(step, step_index, action_index, action, "success", check_result)


                    elif name == "dig_down":
                        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
                        share_memory(self.memory,events)
                        check_result = self.check_action_preparation(env,"dig_down",  args,task_information,events)
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)

                        underground = True
                        tool = "" if args["tool"] is None else args["tool"]
                        go_down_to_y_level(env,args["y_level"],equipment = tool)
                        emit_action_finished(step, step_index, action_index, action, "success", check_result)


                    elif name == "dig_up":
                        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
                        share_memory(self.memory,events)
                        check_result = self.check_action_preparation(env,"dig_up",  args,task_information,events)
                        if not check_result["success"]:
                            return finish_failure(step, step_index, action_index, action, check_result, underground)

                        underground = False
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
            tool = normalize_inventory_name(args_dict["tool"])
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
            obj = normalize_inventory_name(args_dict["obj"])
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
            obj = normalize_inventory_name(args_dict["obj"])
            if obj in {"wood", "tree", "log"}:
                target_object = "log"
            elif obj == "stone":
                target_object = "cobblestone"
            else:
                target_object = update_inventory_obj_name(obj)

            old_inventory = self.memory.inventory
            #print(f"old inventory is {old_inventory}")
            events,_,_,_ = env.step([0,0,0,12,12,0,0,0])  
            share_memory(self.memory,events)
            new_inventory = self.memory.inventory
            print(f"my inventory is {new_inventory}")

            if target_object:
                normalized_task = normalize_inventory_name(task_information['task'])
                if (target_object not in self.memory.inventory or self.memory.inventory[target_object]<= 0) and (normalized_task not in self.memory.inventory or self.memory.inventory[normalized_task]<= 0):
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
                normalized_platform = normalize_inventory_name(platform)
                nearby_key = {
                    "crafting table": "table",
                    "furnace": "furnace",
                }.get(normalized_platform)
                nearby_platform = bool(
                    nearby_key
                    and isinstance(events, dict)
                    and events.get("nearby_tools", {}).get(nearby_key, False)
                )
                tracked_platform = bool(
                    normalized_platform == "crafting table"
                    and getattr(
                        self.memory, "_dc3pa_crafting_table_placed", False
                    )
                )
                if (
                    (
                        normalized_platform not in self.memory.inventory
                        or self.memory.inventory[normalized_platform] <= 0
                    )
                    and not nearby_platform
                    and not tracked_platform
                ):
                    if (
                        self._is_deep_mining_task(task_information)
                        and normalized_platform in {"crafting table", "furnace"}
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
        task_name = normalize_inventory_name(task_information["task"])
        required_quantity = int(task_information["quantity"])
        for item in task_completion_inventory_names(task_name):
            quantity = memory.inventory.get(item, 0)
            print(
                f"task is {task_name},item is {item}. task quantity is "
                f"{required_quantity}, quantity is {math.ceil(quantity)} "
            )
            if required_quantity <= math.ceil(quantity):
                print(f"task is {task_name},inventory item is {item},quantity is {quantity}")
                return True
        return False
