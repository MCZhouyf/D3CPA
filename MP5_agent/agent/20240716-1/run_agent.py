# -- coding: utf-8 --
from utils import *
from planner import Planner
from reflexion import Reflexion
from controller import Controller
from work_memory import Work_Memory
from minedojo.sim import InventoryItem
import minedojo
import random
import argparse
import numpy as np


class Evaluator:
    def __init__(self):
        self.mllm_url = args.mllm_url
        self.openai_key = args.openai_key
        f_mkdir(f"../images"); f_remove("../video"); f_mkdir(f"../video")
        f_mkdir(f"../logs"); logging.basicConfig(filename=f'../logs/agent.log', filemode='w', level=logging.INFO, format='%(message)s')

            

            
        seed = random.randint(1,1000000000000)
        vradius = 5
        log_info(seed)
        biome_string = "forest"
        self.every_task_max_retries = 20
        self.task_name=""
        self.min_episode=0

        self.env = minedojo.make(
            task_id="harvest", target_names="diamond",
            image_size=(512, 820), 
            target_quantities=100, seed=3, 
            specified_biome = biome_string, 
            spawn_rate=1, 
            break_speed_multiplier = 100.0, 
            spawn_range_low=(-10, -10, -10), spawn_range_high=(10, 10, 10), 
            start_at_night = False, world_seed = seed, use_voxel = True, 
            voxel_size=dict(xmin=-vradius, ymin=-vradius, zmin=-vradius, xmax=vradius, ymax=vradius, zmax=vradius), # doesn't really matter
            use_lidar=True,
            lidar_rays=[
                    (np.pi * pitch / 180, np.pi * yaw / 180, 10) # ALERT: lidar range is now 10
                    for pitch in np.arange(-60, 60, 5)
                    for yaw in np.arange(-60, 60, 5)
            ]
            )
    
    def single_task_evaluate(self):
        #执行单个任务的评估，运行goal_ratio 次，并计算成功率和平均剧集长度
        goal_ratio=10
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
                print(f"Task {self.task_name} | Iteration {i+1} | Successful {succ_flag} | Episode length {self.min_episode} | Success rate {succ_rate/(i+1)}")
               
            print("success rate: ", succ_rate/loops)
            print("average episode length:", sum(episode_lengths)/(len(episode_lengths)))

                   
    def eval_step(self):
        
        
        self.env.reset()

        #self.env.set_inventory([InventoryItem(slot=9, name="dirt", variant=None, quantity=6), InventoryItem(slot=0, name="wooden_pickaxe", variant=None, quantity=1), InventoryItem(slot=17, name="coal", variant=None, quantity=3)])
        self.env.set_inventory([InventoryItem(slot=9, name="dirt", variant=None, quantity=6), InventoryItem(slot=17, name="coal", variant=None, quantity=3)])
        
        events, _, _, _ = self.env.step([0,0,0,12,6,0,0,0])

       
        underground = False
        model_name=args.gpt_model_name

        #memory = Memory(openai_key=self.openai_key, use_history_workflow=True)
        memory = Work_Memory(openai_key=self.openai_key, model_name=model_name,use_history_workflow=False)
        reflexion = Reflexion(openai_key=self.openai_key, memory=memory, model_name=model_name)
        planner = Planner(openai_key=self.openai_key, memory=memory, model_name=model_name)
        
   
        # sync the memory
        share_memory(memory=memory, events=events)
        self.min_episode=0

        with open(args.task, 'r') as f:
            task_list = json.load(f)
            print(f"{task_list}")
            for task_id, task_information in enumerate(task_list[::-1]):

                self.every_task_max_retries = 20
                check_result = {}
                self.task_name=task_information["task"]
                while self.every_task_max_retries >= 0:
                    log_info('every_task_max_retries : ', self.every_task_max_retries)
                    memory.reset_current_environment_information()

                    log_info(f"My inventory: {memory.inventory}")
                    
                    if self.every_task_max_retries == 0:
                        log_info("************Failed to complete this task. Consider updating your prompt.************\n\n")
                        return False

                    ## Stage1: Workflow Decision
                    if(self.min_episode%3==0 or self.min_episode==0):
                        log_info('Stage1: Workflow Decision')
                    #Generate prompt template
                        message =memory.generate_prompt_template(env=self.env, task_information=task_information, underground=underground, check_result=check_result)
                    #workflow_dict = planner.get_workflow(task_information=task_information, underground=underground, check_result=check_result)
                        workflow_dict =planner.get_workflow(message)
                        print('GET ', workflow_dict)
                    self.min_episode=+1
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
                    flage_success = self.check_done(task_information=task_information,memory=memory)

                    ## Stage4: Validation
                    print('Stage4: Validation')
                    if flage_success:
                        # Success: Put successful Workflow into Memory
                        #memory.add_successful_workflow(task_information["task"], task_information["description"], workflow_dict["workflow"], True)
                        memory.add_successful_workflow(task_information["task"], workflow_dict["workflow"], True)
                        break
                    else:
                        # Failure: Do not have sufficient materials, Feedback
                        self.every_task_max_retries -= 1
                        continue
        
        memory.reset_all()
        log_info("############ Successfully Finish All Tasks ############")
        return True


    def check_done (self,task_information, memory):
        print(f"inventory name is{memory.inventory}")
        for item in memory.inventory:
            #print(f"task is {task_information['task']},item is {item}. task quantity is {task_information['quantity']}, quantity is{math.ceil(memory.inventory[item])} ")
            if task_information["task"]==item and task_information["quantity"]<=math.ceil(memory.inventory[item]):
                #print(f"task is {item},quantity is {memory.inventory[item]}")
                return True
        return False

    

                
    
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
        required=True,
    )
    # 3. gpt_model_name
    parser.add_argument(
        "--gpt_model_name",
        type=str,
        required=True,
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
        required=True,
    )
    args = parser.parse_args()

    main()
