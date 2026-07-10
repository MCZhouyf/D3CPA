from utils import *
from re import T
import minedojo
import random
import string
import numpy as np
from PIL import Image
import math
import pickle
from minedojo.sim import InventoryItem
import numpy as np
from minedojo.sim.mc_meta import mc as MC
import pdb
from langchain.schema import HumanMessage, SystemMessage
from langchain.vectorstores import Chroma
from langchain.embeddings.openai import OpenAIEmbeddings
from PIL import Image
import numpy as np
import os
import cv2
from skimage.metrics import structural_similarity as ssim
import datetime 
class Work_Memory:
    
    def __init__(
        self,
        openai_key,
        model_name="gpt-4-0613",
        ckpt_dir="./",
        ckpt_id=0,
        use_history_workflow=True,
        retrieval_top_k=2,
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

        ## Long Memory
        self.inventory = {}
        ## Short Memory
        self.current_environment_information = []
        self.feedback = []

        os.environ["OPENAI_API_KEY"] = openai_key
        openai.api_base = api_base
        self.llm = ChatOpenAI(
            model_name=model_name,
            openai_api_base=api_base,
            openai_api_key=openai_key,
            temperature=temperature,
            request_timeout=60,
        )

        self.retrieval_top_k = retrieval_top_k
        self.ckpt_dir = ckpt_dir
        self.ckpt_id = ckpt_id
        self.vectordb_dir = f"{self.ckpt_dir}/memory/workflow_vectordb_{self.ckpt_id}"
        self.embedding_available = os.environ.get("MP5_ENABLE_WORKFLOW_EMBEDDINGS", "").lower() in {"1", "true", "yes", "on"}

        #将json中的内容存到向量数据库中，add_successful_workflow()
        if use_history_workflow:
            log_info(f"***********Loading Workflow from {ckpt_dir}memory***********")
            self.workflows = load_json(f"{ckpt_dir}/memory/workflows_{self.ckpt_id}.json")
            self.episodic_memory_vectordb = None
            if self.embedding_available:
                try:
                    self._rebuild_workflow_vectordb(api_base, openai_key)
                except Exception as e:
                    log_info(f"Workflow vectordb rebuild failed, falling back to JSON-only memory: {e}")
                    self.embedding_available = False
                    self.episodic_memory_vectordb = None
            else:
                log_info("Workflow embeddings disabled; using JSON-only workflow memory.")

        else:
            self.workflows = {}
            self.episodic_memory_vectordb = None
            if self.embedding_available:
                try:
                    f_mkdir(self.vectordb_dir)
                    self.episodic_memory_vectordb = Chroma(
                        collection_name=f"workflow_vectordb_{self.ckpt_id}",
                        embedding_function=OpenAIEmbeddings(
                            openai_api_base=api_base,
                            openai_api_key=openai_key,
                        ),
                        persist_directory=self.vectordb_dir,
                    )
                except Exception as e:
                    log_info(f"Workflow vectordb init failed, falling back to JSON-only memory: {e}")
                    self.embedding_available = False
                    self.episodic_memory_vectordb = None
        print(f"***********use_history:{use_history_workflow}***********")

        if self.embedding_available:
            assert self.episodic_memory_vectordb._collection.count() == len(self.workflows), (
                f"workflows's vectordb is not synced with workflows_{self.ckpt_id}.json.\n"
                f"There are {self.episodic_memory_vectordb._collection.count()} workflows in vectordb but {len(self.workflows)} workflows in workflows_{self.ckpt_id}.json.\n"
                f"Did you set use_history_workflow=False when initializing the manager?\n"
                f"You may need to manually delete the workflow_vectordb directory for running from scratch."
            )

    def _rebuild_workflow_vectordb(self, api_base, openai_key):
        if os.path.exists(self.vectordb_dir):
            f_remove(self.vectordb_dir)
        f_mkdir(self.vectordb_dir)
        self.episodic_memory_vectordb = Chroma(
            collection_name=f"workflow_vectordb_{self.ckpt_id}",
            embedding_function=OpenAIEmbeddings(
                openai_api_base=api_base,
                openai_api_key=openai_key,
            ),
            persist_directory=self.vectordb_dir,
        )
        for task_name, value in self.workflows.items():
            self.add_successful_workflow(task_name, value["successful_workflow"], update_json=False)


    
    #Prompt template  task_information=task_information, underground=underground, check_result=check_result
    def generate_prompt_template(self,env,task_information,underground,check_result, previous_workflow=None, reflection=None):
        try:
            task_prompt = load_prompt("task_prompt")
            task_information_string = dict_to_prompt(task_information)
            current_environment_information=""
            
            
            if underground:
                current_environment_information += "- position: underground\n"
            else:
                current_environment_information += "- position: ground\n"
            
            
            reference_plan_string = list_dict_to_prompt(self.get_episodic_memroy(task_information["task"]))

            prompt_template = load_prompt("prompt_template").format(
                task_information=task_information_string, 
                current_environment_information=current_environment_information,
                inventory=self.inventory,
                reference_plan=reference_plan_string
            )
            #print (f"check_result{check_result}!!!!!!!!!!!!!!!!!!!!")

            if len(check_result) == 0:
                prompt_template += "\nPlan your workflow. Remember to follow the response format."
            else:
                previous_workflow_string = str(previous_workflow) if previous_workflow else "None"
                reflection_string = reflection if reflection else "None"
                prompt_template += f"""The previous workflow failed. 
                The reason for the failure: {check_result["feedback"]}.
                A suggested recommendations: {check_result["suggestion"]}. 
                Previous failed workflow: {previous_workflow_string}.
                Reflection for re-planning: {reflection_string}.
                re-plan your workflow. Remember to follow the response format."""

               # print(f"prompt_template is{prompt_template}")

            messages = [
                SystemMessage(content=task_prompt),
                HumanMessage(content=prompt_template)
            ]
            return messages
       
           # print("5555555555555")
        except Exception as e:
            log_info(f"Error arises in Plan Workflow part: {e} Trying again!\n\n")
            self.reset_current_environment_information()
        #self.get_visual_memory(env=env, name="visual_memory")
        
    
    # A function which allows the agent to do nothing for 'duration' timesteps.
    def sleep(self,env, duration = 1):
        for i in range (duration):
            _,_,_,_ = env.step([0,0,0,12,12,0,0,0])
            _,_,_,_ = env.step([0,0,0,12,12,0,0,0])
            _,_,_,_ = env.step([0,0,0,12,12,0,0,0])
            _,_,_,_ = env.step([0,0,0,12,12,0,0,0])
            events,_,_,_ = env.step([0,0,0,12,12,0,0,0])
        return events
    
    #GET the visual memory
    def get_visual_memory(self,env,name):

        events  = self.sleep(env)
        rgb_frame = events["rgb"]
        file_path = f"../visual_buff/{name}.jpg"
        image = Image.fromarray(rgb_frame.transpose(1,2,0))
        print(f"Got Visual memory")
        image.save(file_path)

        
    
    #GET the Episodic memory,retival vector 
    def get_episodic_memroy(self, query):
        if not self.embedding_available or self.episodic_memory_vectordb is None:
            workflows = []
            for task_name, value in list(self.workflows.items())[: self.retrieval_top_k]:
                workflows.append(
                    {
                        "task_name": task_name,
                        "workflow": str(value.get("successful_workflow", [])),
                    }
                )
            if workflows:
                log_info(
                    f"Workflow Memory using JSON-only fallback: "
                    f"{', '.join([workflow['task_name'] for workflow in workflows])}"
                )
            return workflows

        k = min(self.episodic_memory_vectordb._collection.count(), self.retrieval_top_k)
        if k == 0:
            #print("memory_seach empty!!!!!!!!!!!!!!")
            return []
        log_info(f"Workflow Memory retrieving for {k} workflows")
        docs_and_scores = self.episodic_memory_vectordb.similarity_search_with_score(query, k=k)
       # print (f"search is {docs_and_scores}")
        log_info(
            f"Workflow Memory is seaching workflows: "
            f"{', '.join([doc.metadata['task_name'] for doc, _ in docs_and_scores])}"
        )
        
        workflows = []
        for doc, _ in docs_and_scores:
            #print(f"2222222222222")
            workflows.append(
                {
                    "task_name": doc.metadata["task_name"],
                    "workflow": doc.metadata["task_plan"]
                }
            )
            #print(f"search successful memory:{workflows}")
        return workflows
    


    def add_successful_workflow(self, task_name, successful_workflow, update_json=True):
        #删除已有记录
        if self.embedding_available and self.episodic_memory_vectordb is not None and task_name in self.workflows:
            self.episodic_memory_vectordb._collection.delete(ids=[task_name])
            '''
            vdb.add_texts(
        ids=[task["task_name"]],
        texts=[task["plan"]],
        metadatas=[{"task_name": task["task_name"], "plan": task["plan"], "tips": task["tips"], "image": task["image_path"]}]
            

        self.episodic_memory_vectordb.add_texts(
            texts=[task_description],
            ids=[task_name],
            metadatas=[{"task_name": task_name,"task_plan":successful_workflow,"inventory":self.inventory, "biom":"forest","image":"", "time":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}],
        )
        '''
        
        if self.embedding_available and self.episodic_memory_vectordb is not None:
            self.episodic_memory_vectordb.add_texts(
                texts=[str(successful_workflow)],
                ids=[task_name],
                metadatas=[{"task_name": task_name, "task_plan":str(successful_workflow),"inventory":str(self.inventory), "biom":"forest","image":"", "time":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}],
            )
        

        if update_json:
            self.workflows[task_name] = {
                "task_name": "",
                "successful_workflow": successful_workflow,
            }

            if self.embedding_available and self.episodic_memory_vectordb is not None:
                assert self.episodic_memory_vectordb._collection.count() == len(
                    self.workflows
                ), f"workflow_vectordb is not synced with workflows_{self.ckpt_id}.json"

            dump_json(self.workflows, f"{self.ckpt_dir}/memory/workflows_{self.ckpt_id}.json")

        #self.workflow_vectordb.persist()

        log_info(f"Adding a successful workflow about '{task_name}' to the memory.")

        return True
    

    def update_inventory(self, new_inventory):
        self.inventory = new_inventory
    
    def reset_inventory(self):
        self.inventory = {}

    def reset_workflows(self):
        self.workflows = {}

    def reset_current_environment_information(self):
        self.current_environment_information = []

    def reset_feedback(self):
        self.feedback = []

    def reset_all(self):
        self.reset_inventory()
        self.reset_workflows()
        self.reset_current_environment_information()
        self.reset_feedback()
        #Clear Successful Workflow Memory in Chroma
        #self.workflow_vectordb.delete_collection()
    
    
    
    

       
