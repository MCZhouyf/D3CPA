from utils import *

class Reflexion:
    def __init__(
        self,
        openai_key,
        memory,
        model_name="gpt-4-0613",
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


        assert memory is not None, "Please input memory"


    