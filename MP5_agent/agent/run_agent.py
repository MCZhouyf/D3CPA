# -- coding: utf-8 --
from utils import *
from dc3pa_feature_flags import legacy_task_hacks_enabled
from planner import Planner
from reflexion import Reflexion
from controller import Controller
from work_memory import Work_Memory
from minedojo.sim import InventoryItem
import minedojo
import random
import argparse
import numpy as np
import traceback


MINE_DOJO_EXTRA_SPAWN_ITEMS = {
    "diamond_ore",
    "gold_ore",
    "iron_ore",
    "coal_ore",
    "pig",
    "cow",
    "bat",
    "cat",
    "chicken",
    "horse",
    "sheep",
    "zombie",
}

MINE_DOJO_TARGET_TO_SPAWN_ITEM = {
    "cobblestone": "stone",
    "diamond": "diamond_ore",
    "gold ore": "gold_ore",
    "iron ore": "iron_ore",
    "coal ore": "coal_ore",
    "pig": "pig",
    "cow": "cow",
    "bat": "bat",
    "cat": "cat",
    "chicken": "chicken",
    "horse": "horse",
    "sheep": "sheep",
    "zombie": "zombie",
}


class Evaluator:
    def __init__(self):
        self.mllm_url = args.mllm_url
        self.openai_key = args.openai_key
        self.task_target_name = self._load_task_target_name(args.task)
        self.env_target_name = os.environ.get("MP5_ENV_TARGET_NAME") or self._env_target_for_task(self.task_target_name)
        f_mkdir(f"../images"); f_remove("../video"); f_mkdir(f"../video")
        f_mkdir(f"../logs"); logging.basicConfig(filename=f'../logs/agent.log', filemode='w', level=logging.INFO, format='%(message)s')

            

            
        seed_override = os.environ.get("DC3PA_WORLD_SEED")
        seed = int(seed_override) if seed_override is not None else random.randint(1,1000000000000)
        random.seed(seed)
        np.random.seed(seed % (2 ** 32))
        vradius = 5
        log_info(seed)
        biome_string = "forest"
        self.every_task_max_retries = 20
        self.task_name=""
        self.min_episode=0

        self.env = minedojo.make(
            task_id="harvest", target_names=self.env_target_name,
            image_size=(512, 820), 
            target_quantities=100, seed=int(os.environ.get("DC3PA_SIM_SEED", 3)), 
            specified_biome = biome_string, 
            break_speed_multiplier = 100.0, 
            start_at_night = False, world_seed = seed, use_voxel = True, 
            voxel_size=dict(xmin=-vradius, ymin=-vradius, zmin=-vradius, xmax=vradius, ymax=vradius, zmax=vradius), # doesn't really matter
            use_lidar=True,
            lidar_rays=[
                    (np.pi * pitch / 180, np.pi * yaw / 180, 10) # ALERT: lidar range is now 10
                    for pitch in np.arange(-60, 60, 5)
                    for yaw in np.arange(-60, 60, 5)
            ],
            **self._extra_spawn_kwargs(self.env_target_name),
            )

    def _load_task_target_name(self, task_path):
        try:
            with open(task_path, "r") as f:
                task_list = json.load(f)
            if task_list:
                return task_list[-1]["task"]
        except Exception as exc:
            log_info(f"Failed to read task target from {task_path}: {exc}. Falling back to diamond.")
        return "diamond"

    def _env_target_for_task(self, task_target_name):
        # MineDojo's harvest meta task crashes for redstone here; MP5 still checks redstone itself.
        if task_target_name == "redstone":
            return "diamond"
        return task_target_name

    def _extra_spawn_kwargs(self, env_target_name):
        spawn_item = MINE_DOJO_TARGET_TO_SPAWN_ITEM.get(env_target_name, env_target_name)
        if spawn_item not in MINE_DOJO_EXTRA_SPAWN_ITEMS:
            log_info(
                f"Skipping MineDojo extra spawn for target={env_target_name}, "
                f"spawn_item={spawn_item}; unsupported by current MineDojo version."
            )
            return {}
        return {
            "spawn_rate": 1,
            "spawn_range_low": (-10, -10, -10),
            "spawn_range_high": (10, 10, 10),
        }

    def _fixed_workflow_for_task(self, task_information):
        if not legacy_task_hacks_enabled():
            return None
        if task_information.get("task") != "redstone":
            return None

        return {
            "workflow": [
                {"times": "4", "actions": [
                    {"name": "find", "args": {"obj": "log"}},
                    {"name": "move_to", "args": {"obj": "log"}},
                    {"name": "mine", "args": {"obj": "log", "tool": None}},
                ]},
                {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"planks": 16}, "materials": {"log": 4}, "platform": None}}]},
                {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"crafting table": 1}, "materials": {"planks": 4}, "platform": None}}]},
                {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"stick": 4}, "materials": {"planks": 2}, "platform": None}}]},
                {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"wooden pickaxe": 1}, "materials": {"planks": 3, "stick": 2}, "platform": "crafting table"}}]},
                {"times": "1", "actions": [{"name": "equip", "args": {"obj": "wooden pickaxe"}}]},
                {"times": "1", "actions": [{"name": "dig_down", "args": {"y_level": 60, "tool": "wooden pickaxe"}}]},
                {"times": "11", "actions": [
                    {"name": "find", "args": {"obj": "cobblestone"}},
                    {"name": "move_to", "args": {"obj": "cobblestone"}},
                    {"name": "mine", "args": {"obj": "cobblestone", "tool": "wooden pickaxe"}},
                ]},
                {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"furnace": 1}, "materials": {"cobblestone": 8}, "platform": "crafting table"}}]},
                {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"stone pickaxe": 1}, "materials": {"cobblestone": 3, "stick": 2}, "platform": "crafting table"}}]},
                {"times": "1", "actions": [{"name": "equip", "args": {"obj": "stone pickaxe"}}]},
                {"times": "1", "actions": [{"name": "dig_down", "args": {"y_level": 40, "tool": "stone pickaxe"}}]},
                {"times": "6", "actions": [
                    {"name": "find", "args": {"obj": "iron ore"}},
                    {"name": "move_to", "args": {"obj": "iron ore"}},
                    {"name": "mine", "args": {"obj": "iron ore", "tool": "stone pickaxe"}},
                ]},
                {"times": "3", "actions": [
                    {"name": "find", "args": {"obj": "coal ore"}},
                    {"name": "move_to", "args": {"obj": "coal ore"}},
                    {"name": "mine", "args": {"obj": "coal ore", "tool": "stone pickaxe"}},
                ]},
                {"times": "3", "actions": [{"name": "craft", "args": {"obj": {"iron ingot": 1}, "materials": {"iron ore": 1, "coal": 1}, "platform": "furnace"}}]},
                {"times": "1", "actions": [{"name": "craft", "args": {"obj": {"iron pickaxe": 1}, "materials": {"iron ingot": 3, "stick": 2}, "platform": "crafting table"}}]},
                {"times": "1", "actions": [{"name": "equip", "args": {"obj": "iron pickaxe"}}]},
                {"times": "1", "actions": [{"name": "dig_down", "args": {"y_level": 12, "tool": "iron pickaxe"}}]},
                {"times": "1", "actions": [
                    {"name": "find", "args": {"obj": "redstone ore"}},
                    {"name": "move_to", "args": {"obj": "redstone ore"}},
                    {"name": "mine", "args": {"obj": "redstone ore", "tool": "iron pickaxe"}},
                ]},
            ]
        }
    
    def single_task_evaluate(self):
        #执行单个任务的评估，运行goal_ratio 次，并计算成功率和平均剧集长度
        goal_ratio=1
        num_workers=0
        loops = goal_ratio
        succ_flag=False
        
        if num_workers == 0:
            succ_rate = 0
            episode_lengths = []
            for i in range(loops):
                try:
                    #self.reset(self.task)
                    #succ_flag, min_episode = self.eval_step()
                    if(self.eval_step()):
                        succ_rate+=1
                        succ_flag=True
                        episode_lengths.append(self.min_episode)
                    else:
                        succ_flag=False   
                except Exception as e:
                    print(e)
                    traceback.print_exc()
                print(f"Task {self.task_name} | Iteration {i+1} | Successful {succ_flag} | Episode length {self.min_episode} | Success rate {succ_rate/(i+1)}")
               
            print("success rate: ", succ_rate/loops)
            print("average episode length:", sum(episode_lengths)/(len(episode_lengths)+0.1))

                   
    def eval_step(self):
        
        
        self.env.reset()

        self.env.set_inventory([])
        #self.env.set_inventory([InventoryItem(slot=9, name="dirt", variant=None, quantity=6),  InventoryItem(slot=3, name="furnace", variant=None, quantity=1),InventoryItem(slot=17, name="coal", variant=None, quantity=3)])
        #self.env.set_inventory([InventoryItem(slot=9, name="dirt", variant=None, quantity=6),  InventoryItem(slot=0, name="wooden_pickaxe", variant=None, quantity=1),  InventoryItem(slot=1, name="stone_pickaxe", variant=None, quantity=1),  InventoryItem(slot=3, name="carfting table", variant=None, quantity=1),  InventoryItem(slot=3, name="furnace", variant=None, quantity=1),InventoryItem(slot=17, name="coal", variant=None, quantity=3)])
        
        events, _, _, _ = self.env.step([0,0,0,12,6,0,0,0])

       
        underground = False
        model_name=args.gpt_model_name

        #memory = Memory(openai_key=self.openai_key, use_history_workflow=True)
        disable_memory = os.environ.get("MP5_DISABLE_MEMORY", "").lower() in {"1", "true", "yes", "on"}
        memory = Work_Memory(
            openai_key=self.openai_key,
            model_name=model_name,
            use_history_workflow=not disable_memory,
        )
        reflexion = Reflexion(openai_key=self.openai_key, memory=memory, model_name=model_name)
        planner = Planner(openai_key=self.openai_key, memory=memory, model_name=model_name)
        
   
        # sync the memory
        share_memory(memory=memory, events=events)
        self.min_episode=0

        with open(args.task, 'r') as f:
            task_list = json.load(f)
            #print(f"{task_list}")
            for task_id, task_information in enumerate(task_list[::-1]):

                self.every_task_max_retries = 30
                check_result = {}
                previous_workflow = None
                reflection = ""
                self.task_name=task_information["task"]
                while self.every_task_max_retries >= 0:
                    log_info('every_task_max_retries : ', self.every_task_max_retries)
                    memory.reset_current_environment_information()

                    log_info(f"My inventory: {memory.inventory}")
                    
                    if self.every_task_max_retries == 0:
                        log_info("************Failed to complete this task. Consider updating your prompt.************\n\n")
                        return False

                    ## Stage1: Workflow Decision
                    log_info('Stage1: Workflow Decision')
                    if check_result:
                        reflection = reflexion.reflect_failure(
                            task_information=task_information,
                            workflow_dict=previous_workflow,
                            check_result=check_result,
                            underground=underground,
                        )
                        log_info(f"Reflection Summary: {reflection}")
                    else:
                        reflection = ""

                    workflow_dict = self._fixed_workflow_for_task(task_information)
                    if workflow_dict:
                        log_info(f"Using fixed workflow for task {task_information['task']}")
                    else:
                        message =memory.generate_prompt_template(
                            env=self.env,
                            task_information=task_information,
                            underground=underground,
                            check_result=check_result,
                            previous_workflow=previous_workflow,
                            reflection=reflection,
                        )
                        workflow_dict =planner.get_workflow(message)
                    if not isinstance(workflow_dict, dict) or not workflow_dict.get("workflow"):
                        log_info("Planner did not return a valid workflow. Retrying the task loop.")
                        check_result = {
                            "feedback": "Planner failed to return a valid workflow because the model response was empty, invalid, or the relay request failed.",
                            "success": False,
                            "suggestion": "Retry planning from the current state. Keep the plan concrete and return a valid JSON object with a non-empty workflow field.",
                        }
                        self.every_task_max_retries -= 1
                        continue
                    previous_workflow = workflow_dict
                    self.min_episode += 1
                    ## Stage2: Interface & Update Inventory
                    print('Stage2: Interface & Update Inventory')
                    controller = Controller(memory=memory, checker=reflexion)
                    check_result, underground = controller.check_and_execute_workflow(env=self.env, workflow_dict=workflow_dict, task_information=task_information, underground=underground)
                    # Fail halfway through
                    if not check_result["success"]:
                        log_info(f"Action Preparation Failure: {check_result}")
                        self.every_task_max_retries -= 1
                        continue

                    # Stage3: Check the final task result
                    print('Stage3: Check the final task result')
                    flage_success = controller.check_done(task_information=task_information,memory=memory)

                    ## Stage4: Validation
                    print('Stage4: Validation')
                    if flage_success:
                       # Success: Put successful Workflow into Memory
                        #memory.add_successful_workflow(task_information["task"], task_information["description"], workflow_dict["workflow"], True)
                        memory.add_successful_workflow(task_information["task"], workflow_dict["workflow"], True)
                        break
                    else:
                        # Failure: Do not have sufficient materials, Feedback
                        check_result = {
                            "feedback": f"The workflow finished but the task '{task_information['task']}' is still incomplete. Current inventory: {memory.inventory}",
                            "success": False,
                            "suggestion": "Re-plan from the current inventory and include any missing intermediate steps, tools, or materials."
                        }
                        self.every_task_max_retries -= 1
                        continue
        
        memory.reset_all()
        log_info("############ Successfully Finish All Tasks ############")
        return True

'''
    def check_done (self,task_information, memory):
        print(f"inventory name is{memory.inventory}")
        for item in memory.inventory:
            #print(f"task is {task_information['task']},item is {item}. task quantity is {task_information['quantity']}, quantity is{math.ceil(memory.inventory[item])} ")
            if task_information["task"]==item and task_information["quantity"]<=math.ceil(memory.inventory[item]):
                #print(f"task is {item},quantity is {memory.inventory[item]}")
                return True
        return False
'''
    

                
    
    #single_task_evaluate()


def main():
    evalutor =Evaluator()
    evalutor.single_task_evaluate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    
    # 1. mllm_url
    parser.add_argument(
        "--mllm_url",
        type=str,
        default='',
    )
    # 2. openai_key
    parser.add_argument(
        "--openai_key",
        type=str,
        default=os.environ.get("OPENAI_API_KEY", ""),
    )
    # 3. gpt_model_name
    parser.add_argument(
        "--gpt_model_name",
        type=str,
        default=os.environ.get("GPT_MODEL_NAME", ""),
    )
    # 4. answer_method
    parser.add_argument(
        "--answer_method",
        type=str,
        default='active',
    )
    # 5. answer_model
    parser.add_argument(
        "--answer_model",
        type=str,
        default='mllm',
    )
    # 5. task
    parser.add_argument(
        "--task",
        type=str,
        default=os.environ.get("TASK_FILE", ""),
    )
    args = parser.parse_args()

    if not args.openai_key:
        parser.error("openai_key is required, set --openai_key or OPENAI_API_KEY")
    if not args.gpt_model_name:
        parser.error("gpt_model_name is required, set --gpt_model_name or GPT_MODEL_NAME")
    if not args.task:
        parser.error("task is required, set --task or TASK_FILE")

    main()
