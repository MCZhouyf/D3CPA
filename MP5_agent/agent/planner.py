# -- coding: utf-8 --
import traceback
import time
from utils import *
from dc3pa_feature_flags import legacy_task_hacks_enabled
from langchain.schema import HumanMessage, SystemMessage


class Planner:
    def __init__(
        self,
        openai_key,
        memory,
        model_name="gpt-4-0613",
        #model_name="gpt-4-0613",
        #model_name="gpt-4-0613",
        temperature=0
    ):
        api_base = os.environ.get("OPENAI_API_BASE", "https://api.xiaoai.plus/v1")
        os.environ["OPENAI_API_KEY"] = openai_key

        openai.api_base = api_base

        self.llm = ChatOpenAI(
            model_name=model_name,
            openai_api_base=api_base,
            openai_api_key=openai_key,
            temperature=temperature,
            request_timeout=60,
        )

        self.memory = memory
        assert  self.memory is not None, "Please input memory"

    def _workflow_mentions_mine(self, workflow, obj_name, tool_name=None):
        for step in workflow:
            for action in step.get("actions", []):
                if action.get("name") != "mine":
                    continue
                args = action.get("args", {})
                if args.get("obj") != obj_name:
                    continue
                if tool_name is None or args.get("tool") == tool_name:
                    return True
        return False

    def _workflow_mentions_craft_or_equip(self, workflow, item_name):
        for step in workflow:
            for action in step.get("actions", []):
                args = action.get("args", {})
                if action.get("name") == "equip" and args.get("obj") == item_name:
                    return True
                if action.get("name") == "craft" and item_name in args.get("obj", {}):
                    return True
        return False

    def _inject_prerequisite_steps(self, workflow_dict):
        if not legacy_task_hacks_enabled():
            return workflow_dict
        workflow = workflow_dict.get("workflow", [])
        if not workflow:
            return workflow_dict

        needs_wooden_pickaxe = self._workflow_mentions_mine(workflow, "cobblestone")
        has_wooden_pickaxe_plan = self._workflow_mentions_craft_or_equip(workflow, "wooden pickaxe")

        if needs_wooden_pickaxe and not has_wooden_pickaxe_plan:
            prerequisite_steps = [
                {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"planks": 4}, "materials": {"log": 1}, "platform": None}}]},
                {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"stick": 4}, "materials": {"planks": 2}, "platform": "crafting table"}}]},
                {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"wooden pickaxe": 1}, "materials": {"planks": 3, "stick": 2}, "platform": "crafting table"}}]},
                {"times": "1", "actions": [{"name": "equip", "args": {"obj": "wooden pickaxe"}}]},
            ]
            insert_at = 0
            for idx, step in enumerate(workflow):
                if self._workflow_mentions_mine([step], "cobblestone"):
                    insert_at = idx
                    break
            workflow = workflow[:insert_at] + prerequisite_steps + workflow[insert_at:]
            workflow_dict["workflow"] = workflow

        return workflow_dict
    
    def get_workflow(self, message, max_retries=5):

        if max_retries == 0:
            log_info("************Failed to get workflow. Consider updating your prompt.************\n\n")
            return {}

        try:   
            #print(f"{message[1]}")
            log_info("Planner LLM request started")
            workflow_dict = self.llm(message).content
            log_info("Planner LLM request finished")
            print(f"Plan are finished")
            log_info(f"Create Workflow Result: {workflow_dict}")
            workflow_dict = fix_and_parse_json(workflow_dict)
            return self._inject_prerequisite_steps(workflow_dict)
        except Exception as e:
            log_info(f"Error arises in Plan Workflow part: {e} Trying again!\n\n")
            log_info(traceback.format_exc())
            self.memory.reset_current_environment_information()
            wait_seconds = min(2 ** (5 - max_retries), 12)
            log_info(f"Planner retry backoff: sleeping {wait_seconds} seconds before retry.")
            time.sleep(wait_seconds)

            return self.get_workflow(
                message, 
                max_retries=max_retries - 1
            )
        
