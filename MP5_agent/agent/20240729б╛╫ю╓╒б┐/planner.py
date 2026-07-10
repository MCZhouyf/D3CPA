# -- coding: utf-8 --
from utils import *
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
#from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.schema import HumanMessage, SystemMessage
from work_memory import Work_Memory


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
        os.environ["OPENAI_API_KEY"] = openai_key

        openai.api_base ="https://api.xiaoai.plus/v1"

        self.llm = ChatOpenAI(
            model_name=model_name,
            base_url="https://api.xiaoai.plus/v1",
            temperature=temperature
        )

        self.memory = memory
        assert  self.memory is not None, "Please input memory"
    
    def get_workflow(self, message, max_retries=5):

        if max_retries == 0:
            log_info("************Failed to get workflow. Consider updating your prompt.************\n\n")
            return {}

        try:   
            #print(f"{message[1]}")
            workflow_dict = self.llm(message).content
            print(f"Plan are finished")
            log_info(f"Create Workflow Result: {workflow_dict}")
            return fix_and_parse_json(workflow_dict)
        except Exception as e:
            log_info(f"Error arises in Plan Workflow part: {e} Trying again!\n\n")
            self.memory.reset_current_environment_information()

            return self.get_workflow(
                message, 
                max_retries=max_retries - 1
            )
        



