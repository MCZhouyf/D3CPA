from dc3pa.contracts import AgentState
from dc3pa.integration.controller import LegacyControllerAdapter
from dc3pa.planner.legacy_adapter import LegacyPlannerAdapter
from dc3pa.planner.passthrough import PassthroughCognitiveControlPlanner


class FakePlanner:
    def get_workflow(self, message):
        assert message == {"task": "log"}
        return {
            "workflow": [
                {
                    "times": "1",
                    "actions": [
                        {"name": "find", "args": {"obj": "log"}}
                    ],
                }
            ]
        }


class FakeController:
    def check_and_execute_workflow(self, **kwargs):
        assert kwargs["workflow_dict"]["workflow"][0]["times"] == "1"
        return {"success": True, "feedback": "", "suggestion": ""}, False


def test_passthrough_planner_preserves_legacy_behavior():
    adapter = LegacyPlannerAdapter(
        FakePlanner(), lambda task, state, context: {"task": task}
    )
    planner = PassthroughCognitiveControlPlanner(adapter)
    plan = planner.create_plan("log", AgentState(task="log"))
    assert plan.task == "log"
    assert plan.steps[0].actions[0].name == "find"


def test_controller_adapter_converts_plan_back_to_legacy():
    planner = LegacyPlannerAdapter(FakePlanner(), lambda task, state, context: {"task": task})
    plan = planner.plan("log", AgentState(task="log"))
    result = LegacyControllerAdapter(FakeController()).execute(
        env=object(), plan=plan, task_information={"task": "log"}, underground=False
    )
    assert result.success is True
