#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.integration import ExecutionResult, Stage6ClosedLoopRunner, Stage6RuntimeConfig
from dc3pa.integration.state import StateSnapshot
from dc3pa.memory import SceneObservation
from dc3pa.reliability import ReliabilityContext


class StaticReasoning:
    def __init__(self, plan):
        self.plan_value = plan

    def plan(self, task, state, context=None):
        return self.plan_value


class DemoCognitivePlanner:
    def __init__(self, plan):
        self.plan = plan

    def plan_with_outcome(self, task, state, context=None):
        return SimpleNamespace(
            final_plan=self.plan,
            revision_count=1,
            evaluation_reports=(object(),),
            unresolved=(),
        )


class DemoStateProvider:
    def __init__(self):
        self.count = 0

    def snapshot(self, task_information, underground):
        self.count += 1
        task = task_information["task"]
        inventory = {"log": 1.0} if self.count >= 3 else {}
        image = np.zeros((4, 4, 3), dtype=np.uint8)
        return StateSnapshot(
            state=AgentState(task=task, inventory=inventory),
            reliability_context=ReliabilityContext(
                task_context=task, image=image, metadata={"underground": underground}
            ),
            scene=SceneObservation(
                description=f"demo snapshot {self.count}",
                task_context=task,
                inventory=inventory,
                position="surface",
                image=image,
            ),
        )


class DemoController:
    def __init__(self):
        self.calls = 0

    def execute(self, env, plan, task_information, underground):
        self.calls += 1
        success = self.calls >= 2
        return ExecutionResult(
            success=success,
            underground=underground,
            feedback="" if success else "target not found",
            suggestion="" if success else "re-plan with current observation",
            raw={"success": success, "feedback": "target not found" if not success else ""},
        )


class DemoGoal:
    def __init__(self, controller):
        self.controller = controller

    def is_done(self, task_information):
        return self.controller.calls >= 2


class DemoMemory:
    def __init__(self):
        self.episodes = []

    def record_success(self, episode):
        self.episodes.append(episode)
        return {"episode_id": episode.episode_id}


class DemoLegacyMemory:
    def __init__(self):
        self.plans = []

    def record_success(self, task_information, plan):
        self.plans.append(plan)


class DemoReflexion:
    def reflect(self, **kwargs):
        return "Use the updated scene and avoid repeating the failed search blindly."


def main() -> None:
    plan = Plan(
        task="log",
        steps=[PlanStep(actions=[Action("find", {"obj": "log"})])],
        source="demo_dc3pa",
    )
    controller = DemoController()
    multimodal_memory = DemoMemory()
    runtime = Stage6ClosedLoopRunner(
        env=object(),
        config=Stage6RuntimeConfig(mode="dc3pa", max_execution_attempts=2),
        reasoning_chain=StaticReasoning(plan),
        cognitive_planner=DemoCognitivePlanner(plan),
        controller=controller,
        state_provider=DemoStateProvider(),
        goal_checker=DemoGoal(controller),
        reflexion=DemoReflexion(),
        legacy_memory_sink=DemoLegacyMemory(),
        multimodal_memory_sink=multimodal_memory,
    )
    result = runtime.run_task({"task": "log", "quantity": 1})
    payload = result.to_dict()
    payload["demo_only"] = True
    payload["recorded_episode_count"] = len(multimodal_memory.episodes)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
