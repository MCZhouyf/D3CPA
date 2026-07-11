from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.integration import ExecutionResult
from dc3pa.integration.state import StateSnapshot
from dc3pa.memory import SceneObservation
from dc3pa.reliability import ReliabilityContext


def simple_plan(task: str = "log", source: str = "test") -> Plan:
    return Plan(
        task=task,
        source=source,
        steps=[PlanStep(actions=[Action("find", {"obj": task})])],
    )


class StaticPlanSource:
    def __init__(self, plan: Plan):
        self.plan_value = plan
        self.calls = []

    def plan(self, task, state, context=None):
        self.calls.append((task, state, dict(context or {})))
        return self.plan_value


class RaisingPlanSource:
    def __init__(self, exception=RuntimeError("planner down")):
        self.exception = exception
        self.calls = 0

    def plan(self, task, state, context=None):
        self.calls += 1
        raise self.exception


class FakeCognitivePlanner:
    def __init__(self, plan: Plan, *, unresolved=(), revision_count=0, evaluations=0):
        self.plan = plan
        self.unresolved = tuple(unresolved)
        self.revision_count = revision_count
        self.evaluations = evaluations
        self.calls = []

    def plan_with_outcome(self, task, state, context=None):
        self.calls.append((task, state, context))
        return SimpleNamespace(
            final_plan=self.plan,
            unresolved=self.unresolved,
            revision_count=self.revision_count,
            evaluation_reports=tuple(object() for _ in range(self.evaluations)),
        )


class RaisingCognitivePlanner:
    def __init__(self, exception=RuntimeError("provider down")):
        self.exception = exception

    def plan_with_outcome(self, task, state, context=None):
        raise self.exception


class FakeStateProvider:
    def __init__(self, task="log", *, image=True, fail_after=None):
        self.task = task
        self.calls = 0
        self.fail_after = fail_after
        self.image = image

    def snapshot(self, task_information, underground):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("snapshot failed")
        array = np.zeros((3, 4, 3), dtype=np.uint8) if self.image else None
        inventory = {"log": float(max(0, self.calls - 1))}
        return StateSnapshot(
            state=AgentState(
                task=self.task,
                inventory=inventory,
                metadata={"underground": underground},
            ),
            reliability_context=ReliabilityContext(
                task_context=self.task,
                image=array,
                metadata={"underground": underground},
            ),
            scene=SceneObservation(
                description=f"scene-{self.calls}",
                task_context=self.task,
                inventory=inventory,
                position="underground" if underground else "surface",
                image=array,
            ),
        )


class FakeController:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def execute(self, env, plan, task_information, underground):
        self.calls.append((env, plan, dict(task_information), underground))
        value = self.results.pop(0)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, bool):
            return ExecutionResult(
                success=value,
                underground=underground,
                feedback="" if value else "failed",
                suggestion="retry" if not value else "",
                raw={"success": value, "feedback": "failed" if not value else ""},
            )
        return value


class FakeGoal:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def is_done(self, task_information):
        self.calls += 1
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return bool(value)


class FakeReflexion:
    def __init__(self):
        self.calls = []

    def reflect(self, **kwargs):
        self.calls.append(kwargs)
        return "fix the failed step"


class FakeLegacyMemorySink:
    def __init__(self, exception=None):
        self.calls = []
        self.exception = exception

    def record_success(self, task_information, plan):
        self.calls.append((dict(task_information), plan))
        if self.exception is not None:
            raise self.exception
        return True


class FakeMultimodalMemorySink:
    def __init__(self, exception=None):
        self.episodes = []
        self.exception = exception

    def record_success(self, episode):
        self.episodes.append(episode)
        if self.exception is not None:
            raise self.exception
        return {"episode_id": episode.episode_id}
