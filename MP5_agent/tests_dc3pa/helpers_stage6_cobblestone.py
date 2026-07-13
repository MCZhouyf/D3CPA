from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.evaluation import CallableEvaluationProvider, StructuredEvaluationChain
from dc3pa.integration import ExecutionResult, Stage6ClosedLoopRunner, Stage6RuntimeConfig
from dc3pa.integration.state import StateSnapshot, task_context_from_information
from dc3pa.memory import MultimodalMemory, SceneObservation, SuccessfulEpisode
from dc3pa.observability import JsonlTraceWriter
from dc3pa.planner import AdaptiveCognitiveControlPlanner
from dc3pa.reliability import (
    AdaptiveTriggerConfig,
    CallableConfidenceProvider,
    DualChainConfig,
    ReliabilityContext,
    build_hybrid_probability_model,
)

TASK_INFORMATION = {
    "task": "cobblestone",
    "quantity": 4,
    "tool": "wooden pickaxe",
}

INITIAL_INVENTORY = {
    "planks": 3.0,
    "stick": 2.0,
    "crafting table": 1.0,
}

HAPPY_PATH_SCENARIO = "happy"
ACCEPT_CONFLICT_SCENARIO = "accept_conflict"
GOAL_FALSE_SCENARIO = "goal_false"


def _craft_pickaxe_action() -> Action:
    return Action(
        "craft",
        {
            "obj": {"wooden pickaxe": 1},
            "materials": {"planks": 3, "stick": 2},
            "platform": "crafting table",
        },
    )


def _equip_pickaxe_action() -> Action:
    return Action("equip", {"obj": "wooden pickaxe"})


def _mine_cobblestone_action() -> Action:
    return Action(
        "mine",
        {
            "obj": "cobblestone",
            "tool": "wooden pickaxe",
        },
    )


def _step_summary(step: PlanStep) -> Dict[str, Any]:
    action = step.actions[0]
    payload = {"name": action.name, "times": step.times}
    if action.name == "craft":
        payload["obj"] = next(iter(action.args["obj"]))
    else:
        payload["obj"] = action.args.get("obj")
    return payload


def _plan_action_sequence(plan: Plan) -> list[Dict[str, Any]]:
    return [_step_summary(step) for step in plan.steps]


def _mine_step(plan: Plan) -> PlanStep:
    for step in plan.steps:
        for action in step.actions:
            if action.name == "mine" and action.args.get("obj") == "cobblestone":
                return step
    raise AssertionError("No cobblestone mine step found")


def _reliability_for_step(outcome: Any, step: PlanStep, plan_id: str) -> Dict[str, Any]:
    matches = [
        item
        for item in outcome.reliability_results
        if item.plan_id == plan_id and item.step_id == step.step_id
    ]
    if not matches:
        raise AssertionError(f"No reliability result found for step_id={step.step_id}")
    return matches[-1].to_dict()


def _trace_records(path: Path) -> list[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {
                "plan_id",
                "parent_plan_id",
                "previous_plan_id",
                "step_id",
                "edit_id",
                "episode_id",
                "exemplar_id",
                "timestamp",
                "created_at",
                "duration_seconds",
            }:
                continue
            result[key] = _normalize(item)
        return result
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def stable_projection(payload: Mapping[str, Any]) -> Dict[str, Any]:
    diagnostics = dict(payload["diagnostics"])
    return _normalize(
        {
            "task": payload["task"],
            "mode": payload["mode"],
            "success": payload["success"],
            "reactive_replan_count": payload["reactive_replan_count"],
            "pre_execution_revision_count": payload["pre_execution_revision_count"],
            "evaluation_count": payload["evaluation_count"],
            "planning_fallback_count": payload["planning_fallback_count"],
            "pre_execution_block_count": payload["pre_execution_block_count"],
            "controller_execution_count": payload["controller_execution_count"],
            "memory_recorded": payload["memory_recorded"],
            "failure_reason": payload["failure_reason"],
            "final_plan": payload["final_plan"],
            "trace_event_types": diagnostics["trace_event_types"],
            "controller_received_plan": diagnostics["controller_received_plan"],
            "initial_mine_reliability": diagnostics["initial_mine_reliability"],
            "final_mine_reliability": diagnostics["final_mine_reliability"],
            "trigger_observations": diagnostics["trigger_observations"],
            "final_inventory": diagnostics["final_inventory"],
            "memory_episode_counts": diagnostics["memory_episode_counts"],
            "scene_exemplar_counts": diagnostics["scene_exemplar_counts"],
            "final_action_sequence": diagnostics["final_action_sequence"],
            "unresolved": diagnostics["unresolved"],
        }
    )


def validate_happy_payload(payload: Mapping[str, Any]) -> None:
    diagnostics = payload["diagnostics"]
    assert payload["task"] == "cobblestone"
    assert payload["mode"] == "dc3pa"
    assert payload["success"] is True
    assert payload["reactive_replan_count"] == 0
    assert payload["pre_execution_revision_count"] == 1
    assert payload["evaluation_count"] >= 1
    assert payload["planning_fallback_count"] == 0
    assert payload["pre_execution_block_count"] == 0
    assert payload["controller_execution_count"] == 1
    assert payload["memory_recorded"] is True
    assert payload["failure_reason"] == ""

    assert diagnostics["initial_plan"]["version"] == 1
    assert diagnostics["final_plan"]["version"] == 2
    assert diagnostics["final_plan"]["parent_plan_id"] == diagnostics["initial_plan"]["plan_id"]
    assert diagnostics["controller_received_plan"]["plan_id"] == diagnostics["final_plan"]["plan_id"]
    assert diagnostics["controller_received_plan"]["version"] == 2

    initial_knowledge = diagnostics["initial_mine_reliability"]["scores"]["knowledge"]
    assert initial_knowledge["available"] is True
    assert initial_knowledge["probability"] == 0.0
    assert initial_knowledge["hard_conflict"] is True
    missing = initial_knowledge["evidence"]["missing"]
    assert any(
        item["item"] == "wooden pickaxe"
        and item["relation_type"] == "tool"
        and item["required"] == 1.0
        and item["available"] == 0.0
        for item in missing
    )
    initial_environment = diagnostics["initial_mine_reliability"]["scores"]["environment"]
    assert initial_environment["available"] is False
    assert diagnostics["initial_mine_reliability"]["probability"] is None or 0.0 <= diagnostics["initial_mine_reliability"]["probability"] <= 1.0

    assert any(
        item["hard_conflict"] is True
        and item["low_confidence"] is True
        and item["next_interval"] == 1
        for item in diagnostics["trigger_observations"]
    )

    final_knowledge = diagnostics["final_mine_reliability"]["scores"]["knowledge"]
    assert final_knowledge["available"] is True
    assert final_knowledge["probability"] == 1.0
    assert final_knowledge["hard_conflict"] is False

    final_sequence = diagnostics["final_action_sequence"]
    assert {"name": "find", "obj": "cobblestone", "times": 1} in final_sequence
    assert any(item["name"] == "find" and item["obj"] == "log" for item in final_sequence)
    assert any(item["name"] == "craft" and item["obj"] == "planks" for item in final_sequence)
    pickaxe_index = final_sequence.index(
        {"name": "craft", "obj": "wooden pickaxe", "times": 1}
    )
    equip_index = final_sequence.index(
        {"name": "equip", "obj": "wooden pickaxe", "times": 1}
    )
    mine_index = final_sequence.index(
        {"name": "mine", "obj": "cobblestone", "times": 4}
    )
    assert pickaxe_index < equip_index < mine_index
    assert any(
        item["name"] == "craft" and item["obj"] == "planks"
        for item in final_sequence[:pickaxe_index]
    )
    assert diagnostics["final_inventory"]["cobblestone"] >= 4.0
    assert diagnostics["memory_episode_counts"] == {"before": 1, "after": 2}
    assert diagnostics["scene_exemplar_counts"] == {"before": 0, "after": 2}
    assert diagnostics["latest_episode_scene_count"] == 2

    required_events = [
        "planning_started",
        "reasoning_plan_created",
        "reliability_window_evaluated",
        "evaluation_report",
        "plan_revised",
        "cognitive_control_complete",
        "dc3pa_planning_outcome",
        "plan_ready_for_controller",
        "controller_completed",
        "multimodal_memory_recorded",
        "task_succeeded",
    ]
    positions = {name: diagnostics["trace_event_types"].index(name) for name in required_events}
    assert positions == dict(sorted(positions.items(), key=lambda item: item[1]))


def validate_accept_conflict_payload(payload: Mapping[str, Any]) -> None:
    diagnostics = payload["diagnostics"]
    assert payload["success"] is False
    assert payload["pre_execution_block_count"] >= 1
    assert payload["controller_execution_count"] == 0
    assert payload["memory_recorded"] is False
    assert payload["failure_reason"] == "unresolved_dc3pa_plan"
    assert diagnostics["controller_call_count"] == 0
    assert any(item["reason"] == "accepted_despite_hard_conflict" for item in diagnostics["unresolved"])
    assert diagnostics["memory_episode_counts"] == {"before": 1, "after": 1}


def validate_goal_false_payload(payload: Mapping[str, Any]) -> None:
    diagnostics = payload["diagnostics"]
    assert payload["success"] is False
    assert payload["controller_execution_count"] == 1
    assert payload["memory_recorded"] is False
    assert payload["failure_reason"] == "goal_not_achieved"
    assert diagnostics["controller_received_plan"]["plan_id"] == diagnostics["final_plan"]["plan_id"]
    assert diagnostics["memory_episode_counts"] == {"before": 1, "after": 1}
    assert diagnostics["final_inventory"].get("cobblestone", 0.0) < 4.0


@dataclass
class ControlledCobblestoneWorld:
    inventory: Dict[str, float]
    position: str = "surface"

    @classmethod
    def create(cls) -> "ControlledCobblestoneWorld":
        return cls(inventory=dict(INITIAL_INVENTORY))

    def snapshot_inventory(self) -> Dict[str, float]:
        return dict(self.inventory)


class ControlledStateProvider:
    def __init__(self, world: ControlledCobblestoneWorld):
        self.world = world
        self.snapshots = 0

    def snapshot(self, task_information: Mapping[str, Any], underground: bool) -> StateSnapshot:
        self.snapshots += 1
        inventory = self.world.snapshot_inventory()
        task = str(task_information["task"])
        task_context = task_context_from_information(task_information)
        description = (
            f"controlled cobblestone test scene {self.snapshots}; "
            f"position={self.world.position}; inventory={inventory}"
        )
        return StateSnapshot(
            state=AgentState(
                task=task,
                inventory=inventory,
                position=self.world.position,
                metadata={"underground": bool(underground), "source": "controlled_test"},
            ),
            reliability_context=ReliabilityContext(
                task_context=task_context,
                image=None,
                image_vector=None,
                metadata={"underground": bool(underground), "source": "controlled_test"},
            ),
            scene=SceneObservation(
                description=description,
                task_context=task_context,
                inventory=inventory,
                position=self.world.position,
                metadata={"underground": bool(underground), "source": "controlled_test"},
            ),
        )


class ControlledGoalChecker:
    def __init__(self, world: ControlledCobblestoneWorld):
        self.world = world
        self.calls = 0

    def is_done(self, task_information: Mapping[str, Any]) -> bool:
        self.calls += 1
        return float(self.world.inventory.get("cobblestone", 0.0)) >= float(
            task_information.get("quantity", 0)
        )


class ControlledReasoningChain:
    def __init__(self):
        self.calls: list[Dict[str, Any]] = []
        self.plans: list[Plan] = []

    def plan(
        self,
        task: str,
        state: AgentState,
        context: Optional[Mapping[str, Any]] = None,
    ) -> Plan:
        plan = Plan(
            task=task,
            source="controlled_reasoning",
            steps=[
                PlanStep(actions=[Action("find", {"obj": "cobblestone"})]),
                PlanStep(actions=[_mine_cobblestone_action()], times=4),
            ],
        )
        self.calls.append(
            {
                "task": task,
                "inventory": dict(state.inventory),
                "context_keys": sorted(dict(context or {}).keys()),
            }
        )
        self.plans.append(plan)
        return plan


class ControlledEvaluationResponder:
    def __init__(self, scenario: str):
        self.scenario = scenario
        self.prompts: list[Dict[str, Any]] = []
        self.responses: list[Dict[str, Any]] = []

    @staticmethod
    def _prompt_payload(prompt: str) -> Dict[str, Any]:
        marker = "INPUT:\n"
        if marker not in prompt:
            raise AssertionError("Evaluation prompt did not contain INPUT payload")
        return json.loads(prompt.split(marker, 1)[1])

    def __call__(self, prompt: str) -> Mapping[str, Any]:
        payload = self._prompt_payload(prompt)
        self.prompts.append(payload)
        plan = payload["plan"]
        mine_step = None
        for step in plan["steps"]:
            for action in step["actions"]:
                if action["name"] == "mine" and action["args"].get("obj") == "cobblestone":
                    mine_step = step
                    break
            if mine_step is not None:
                break
        if mine_step is None:
            raise AssertionError("No mine step found in evaluation prompt")

        if self.scenario == ACCEPT_CONFLICT_SCENARIO:
            response = {
                "plan_id": plan["plan_id"],
                "plan_version": plan["version"],
                "summary": "provider incorrectly accepted the hard conflict",
                "issues": [
                    {
                        "step_id": mine_step["step_id"],
                        "dimension": "knowledge",
                        "severity": "critical",
                        "diagnosis": "missing wooden pickaxe before mining",
                        "evidence": {"expected": "wooden pickaxe"},
                    }
                ],
                "accepted": True,
                "request_replan": False,
            }
            self.responses.append(response)
            return response

        response = {
            "plan_id": plan["plan_id"],
            "plan_version": plan["version"],
            "summary": "insert missing craft and equip steps before mining",
            "issues": [
                {
                    "step_id": mine_step["step_id"],
                    "dimension": "knowledge",
                    "severity": "critical",
                    "diagnosis": "missing wooden pickaxe before mining cobblestone",
                    "evidence": {"required_tool": "wooden pickaxe"},
                }
            ],
            "edits": [
                {
                    "operation": "insert_before",
                    "target_step_id": mine_step["step_id"],
                    "steps": [
                        PlanStep(actions=[_craft_pickaxe_action()]).to_dict(),
                        PlanStep(actions=[_equip_pickaxe_action()]).to_dict(),
                    ],
                    "rationale": "craft and equip the wooden pickaxe before mining",
                }
            ],
            "accepted": False,
            "request_replan": False,
        }
        self.responses.append(response)
        return response


class ControlledController:
    def __init__(self, world: ControlledCobblestoneWorld, scenario: str):
        self.world = world
        self.scenario = scenario
        self.calls: list[Plan] = []

    @staticmethod
    def _action_positions(plan: Plan) -> Dict[str, int]:
        positions: Dict[str, int] = {}
        for index, step in enumerate(plan.steps):
            for action in step.actions:
                key = action.name
                if action.name in {"craft", "mine", "equip"}:
                    if action.name == "craft":
                        obj = next(iter(action.args["obj"]))
                    else:
                        obj = action.args.get("obj")
                    key = f"{action.name}:{obj}"
                positions.setdefault(key, index)
        return positions

    def _validate_revised_plan(self, plan: Plan) -> None:
        if plan.version < 2:
            raise AssertionError("Controller received unrevised plan version")
        if not plan.parent_plan_id:
            raise AssertionError("Controller expected revised plan with parent_plan_id")
        positions = self._action_positions(plan)
        if not (
            positions["craft:wooden pickaxe"]
            < positions["equip:wooden pickaxe"]
            < positions["mine:cobblestone"]
        ):
            raise AssertionError("Controller received invalid craft/equip/mine order")

    def _apply_plan_material_effects(self, plan: Plan) -> None:
        for step in plan.steps:
            for action in step.actions:
                if action.name == "mine" and action.args.get("obj") == "log":
                    self.world.inventory["log"] = self.world.inventory.get("log", 0.0) + float(step.times)
                elif action.name == "craft":
                    materials = action.args["materials"]
                    for item, quantity in materials.items():
                        self.world.inventory[item] = self.world.inventory.get(item, 0.0) - float(quantity) * step.times
                    obj, quantity = next(iter(action.args["obj"].items()))
                    self.world.inventory[obj] = self.world.inventory.get(obj, 0.0) + float(quantity) * step.times

    def execute(
        self,
        env: Any,
        plan: Plan,
        task_information: Dict[str, Any],
        underground: bool,
    ) -> ExecutionResult:
        del env, task_information
        self.calls.append(plan)
        self._validate_revised_plan(plan)
        self._apply_plan_material_effects(plan)

        if self.world.inventory.get("wooden pickaxe", 0.0) < 1.0:
            raise AssertionError("Controller world lacked crafted wooden pickaxe")
        if self.scenario == HAPPY_PATH_SCENARIO:
            self.world.inventory["cobblestone"] = self.world.inventory.get(
                "cobblestone", 0.0
            ) + 4.0
        return ExecutionResult(
            success=True,
            underground=underground,
            feedback="controlled execution finished",
            suggestion="",
            raw={"success": True, "scenario": self.scenario},
        )


def _seed_successful_episode(memory: MultimodalMemory) -> Dict[str, Any]:
    seed_plan = Plan(
        task="cobblestone",
        source="controlled_seed",
        steps=[
            PlanStep(actions=[_craft_pickaxe_action()]),
            PlanStep(actions=[_equip_pickaxe_action()]),
            PlanStep(actions=[_mine_cobblestone_action()], times=4),
        ],
    )
    result = memory.record_success(
        SuccessfulEpisode(task_name="cobblestone", plan=seed_plan, scenes=())
    )
    prerequisites = [
        edge.to_dict() for edge in memory.dependencies.prerequisites_for("cobblestone")
    ]
    if not any(
        edge["prerequisite"] == "wooden pickaxe"
        and edge["target"] == "cobblestone"
        and edge["relation_type"] == "tool"
        and edge["quantity"] == 1.0
        for edge in prerequisites
    ):
        raise AssertionError("Seed episode did not create the wooden pickaxe prerequisite")
    if memory.successful_episode_count() != 1:
        raise AssertionError("Seed episode count mismatch")
    return {"result": result, "prerequisites": prerequisites}


def run_controlled_cobblestone_scenario(
    root_dir: str | Path,
    *,
    scenario: str = HAPPY_PATH_SCENARIO,
) -> Dict[str, Any]:
    root = Path(root_dir)
    root.mkdir(parents=True, exist_ok=True)
    trace_path = root / "trace.jsonl"
    world = ControlledCobblestoneWorld.create()
    state_provider = ControlledStateProvider(world)
    goal_checker = ControlledGoalChecker(world)
    reasoning = ControlledReasoningChain()
    evaluator = ControlledEvaluationResponder(scenario)
    trace_writer = JsonlTraceWriter(trace_path)

    with MultimodalMemory(root / "memory") as memory:
        seed = _seed_successful_episode(memory)
        episodes_before = memory.successful_episode_count()
        exemplars_before = len(memory.exemplars.all(task_name="cobblestone"))
        confidence_requests: list[Dict[str, Any]] = []

        def confidence_function(request: Any) -> Mapping[str, Any]:
            confidence_requests.append(
                {
                    "plan_id": request.plan.plan_id,
                    "plan_version": request.plan.version,
                    "step_index": request.step_index,
                    "step_id": request.step.step_id,
                }
            )
            return {
                "confidence": 0.95,
                "reason": "controlled high-confidence response",
            }

        reliability_model = build_hybrid_probability_model(
            memory,
            CallableConfidenceProvider(confidence_function),
        )
        cognitive_planner = AdaptiveCognitiveControlPlanner(
            reasoning,
            reliability_model,
            StructuredEvaluationChain(CallableEvaluationProvider(evaluator)),
            trigger_config=AdaptiveTriggerConfig(
                threshold=0.8,
                initial_interval=3,
                window_size=3,
                minimum_interval=1,
                maximum_interval=64,
                increase_step=1,
                decrease_step=1,
            ),
            dual_chain_config=DualChainConfig(
                confidence_threshold=0.8,
                max_revision_rounds=2,
                evaluate_when_unavailable=True,
            ),
            trace_writer=trace_writer,
        )
        controller = ControlledController(world, scenario)
        config = Stage6RuntimeConfig(
            mode="dc3pa",
            max_execution_attempts=2 if scenario != GOAL_FALSE_SCENARIO else 1,
            unresolved_plan_policy="block",
            planner_failure_policy="reasoning_only",
            require_goal_check=True,
            record_legacy_workflow_memory=False,
            record_multimodal_memory=True,
            capture_initial_scene=True,
            capture_final_scene=True,
        )
        runtime = Stage6ClosedLoopRunner(
            env=world,
            config=config,
            reasoning_chain=reasoning,
            controller=controller,
            state_provider=state_provider,
            goal_checker=goal_checker,
            cognitive_planner=cognitive_planner,
            multimodal_memory_sink=memory,
            trace_writer=trace_writer,
        )
        result = runtime.run_task(TASK_INFORMATION, underground=False)
        outcome = cognitive_planner.last_outcome
        if outcome is None:
            raise AssertionError("Cognitive planner did not record a planning outcome")

        initial_plan = outcome.initial_plan
        final_plan = outcome.final_plan
        initial_mine = _mine_step(initial_plan)
        final_mine = _mine_step(final_plan)
        episodes_after = memory.successful_episode_count()
        exemplars_after = len(memory.exemplars.all(task_name="cobblestone"))
        trace_records = _trace_records(trace_path)
        trace_event_types = [item["event_type"] for item in trace_records]
        latest_episode = None
        if result.memory_recorded:
            episodes = memory.connection.execute(
                "SELECT episode_id FROM episodes WHERE success=1 ORDER BY rowid DESC LIMIT 1"
            ).fetchall()
            if episodes:
                latest_episode = str(episodes[0]["episode_id"])
        latest_episode_scene_count = 0
        if latest_episode is not None:
            row = memory.connection.execute(
                "SELECT COUNT(*) AS count FROM scene_exemplars WHERE episode_id=?",
                (latest_episode,),
            ).fetchone()
            latest_episode_scene_count = int(row["count"])

        payload = result.to_dict()
        payload["diagnostics"] = {
            "initial_plan": initial_plan.to_dict(),
            "final_plan": final_plan.to_dict(),
            "final_action_sequence": _plan_action_sequence(final_plan),
            "initial_mine_reliability": _reliability_for_step(
                outcome, initial_mine, initial_plan.plan_id
            ),
            "final_mine_reliability": _reliability_for_step(
                outcome, final_mine, final_plan.plan_id
            ),
            "trigger_observations": [
                item.to_dict() for item in outcome.trigger_observations
            ],
            "trace_event_types": trace_event_types,
            "runtime_event_types": [event.event_type for event in result.events],
            "controller_received_plan": (
                {
                    "plan_id": controller.calls[-1].plan_id,
                    "version": controller.calls[-1].version,
                    "parent_plan_id": controller.calls[-1].parent_plan_id,
                }
                if controller.calls
                else {"plan_id": "", "version": 0, "parent_plan_id": None}
            ),
            "controller_call_count": len(controller.calls),
            "final_inventory": dict(world.inventory),
            "memory_episode_counts": {"before": episodes_before, "after": episodes_after},
            "scene_exemplar_counts": {
                "before": exemplars_before,
                "after": exemplars_after,
            },
            "latest_episode_scene_count": latest_episode_scene_count,
            "seed_prerequisites_for_cobblestone": seed["prerequisites"],
            "evaluation_responses": evaluator.responses,
            "confidence_requests": confidence_requests,
            "unresolved": list(outcome.unresolved),
            "planning_outcome_revision_count": outcome.revision_count,
        }
        return payload


def run_controlled_cobblestone_script(
    *,
    scenario: str = HAPPY_PATH_SCENARIO,
    temp_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    if temp_root is not None:
        return run_controlled_cobblestone_scenario(temp_root, scenario=scenario)
    with tempfile.TemporaryDirectory(prefix="dc3pa_stage6_cobble_") as tmp:
        return run_controlled_cobblestone_scenario(tmp, scenario=scenario)
