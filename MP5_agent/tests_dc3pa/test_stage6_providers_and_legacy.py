from __future__ import annotations

from types import SimpleNamespace

from dc3pa.contracts import AgentState
from dc3pa.integration.legacy import (
    LegacyGoalChecker,
    LegacyMP5ReasoningChain,
    LegacyReflexionAdapter,
    LegacyWorkflowMemorySink,
)
from dc3pa.integration.providers import ChatModelTextAdapter, extract_text_response


class LegacyPlanner:
    def get_workflow(self, message):
        assert message == ["prompt"]
        return {
            "workflow": [
                {"times": "1", "actions": [{"name": "find", "args": {"obj": "log"}}]}
            ]
        }


class LegacyMemory:
    inventory = {}

    def __init__(self):
        self.prompt_calls = []
        self.success_calls = []

    def generate_prompt_template(self, **kwargs):
        self.prompt_calls.append(kwargs)
        return ["prompt"]

    def add_successful_workflow(self, task, workflow, update_json=True):
        self.success_calls.append((task, workflow, update_json))
        return True


def test_legacy_reasoning_and_memory_adapters_match_current_mp5_shapes():
    memory = LegacyMemory()
    chain = LegacyMP5ReasoningChain(LegacyPlanner(), memory)
    plan = chain.plan(
        "log",
        AgentState(task="log"),
        {
            "task_information": {"task": "log"},
            "check_result": {},
            "underground": False,
        },
    )
    assert plan.task == "log"
    assert memory.prompt_calls[0]["task_information"] == {"task": "log"}
    LegacyWorkflowMemorySink(memory).record_success({"task": "log"}, plan)
    task, workflow, update = memory.success_calls[0]
    assert task == "log" and isinstance(workflow, list) and update is True


def test_goal_checker_supports_memory_keyword_and_reflect_failure():
    memory = object()

    class Controller:
        def check_done(self, task_information, memory=None):
            return task_information["task"] == "log" and memory is not None

    assert LegacyGoalChecker(Controller(), memory).is_done({"task": "log"})

    class Reflexion:
        def reflect_failure(self, task_information, workflow_dict, check_result, underground):
            assert underground is True
            return "repair"

    result = LegacyReflexionAdapter(Reflexion()).reflect(
        task_information={"task": "log"},
        previous_workflow={"workflow": []},
        check_result={"success": False},
        underground=True,
    )
    assert result == "repair"


def test_chat_model_adapter_supports_common_interfaces():
    assert extract_text_response(SimpleNamespace(content="ok")) == "ok"

    class InvokeModel:
        def invoke(self, prompt):
            return SimpleNamespace(content=prompt + "!")

    class PredictModel:
        def predict(self, prompt):
            return {"text": prompt + "?"}

    assert ChatModelTextAdapter(InvokeModel()).complete("x") == "x!"
    assert ChatModelTextAdapter(PredictModel()).complete("x") == "x?"
    assert ChatModelTextAdapter(lambda prompt: prompt.upper()).complete("x") == "X"
