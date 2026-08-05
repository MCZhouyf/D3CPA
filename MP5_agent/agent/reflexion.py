from utils import *

class Reflexion:
    def __init__(
        self,
        openai_key,
        memory,
        model_name="gpt-4-0613",
        temperature=0
    ):
        api_base = os.environ.get("OPENAI_API_BASE", "https://api.xiaoai.plus/v1")
        os.environ["OPENAI_API_KEY"] = openai_key
        openai.api_base = api_base

        temperature = float(os.environ.get("DC3PA_LLM_TEMPERATURE", temperature))
        self.llm = ChatOpenAI(
            model_name=model_name,
            openai_api_base=api_base,
            openai_api_key=openai_key,
            temperature=temperature,
            request_timeout=float(os.environ.get("DC3PA_LLM_REQUEST_TIMEOUT", "180")),
            max_retries=int(os.environ.get("DC3PA_LLM_MAX_RETRIES", "1")),
            max_tokens=int(os.environ.get("DC3PA_LLM_MAX_TOKENS", "4096")),
            model_kwargs={"top_p": float(os.environ.get("DC3PA_LLM_TOP_P", "1.0"))},
        )
        self.memory = memory


        assert memory is not None, "Please input memory"

    def reflect_failure(self, task_information, workflow_dict, check_result, underground):
        workflow = workflow_dict.get("workflow", []) if isinstance(workflow_dict, dict) else []
        inventory = dict(self.memory.inventory)
        position = "underground" if underground else "ground"

        fallback_reflection = (
            f"Task '{task_information['task']}' failed after executing a workflow from position={position} "
            f"with inventory={inventory}. Failure reason: {check_result.get('feedback', '')}. "
            f"Suggested repair: {check_result.get('suggestion', '')}. "
            "In the next workflow, keep all already useful completed steps, avoid repeating the failed action "
            "without adding the missing prerequisite, and reorder the plan so required tools/platforms/materials "
            "are prepared before the blocked action."
        )

        try:
            messages = [
                SystemMessage(
                    content=(
                        "You are a Minecraft planning critic. Summarize the concrete mistake in the previous "
                        "workflow and give short repair guidance for the next planning round."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Task: {task_information}\n"
                        f"Position: {position}\n"
                        f"Inventory: {inventory}\n"
                        f"Previous workflow: {workflow}\n"
                        f"Failure feedback: {check_result.get('feedback', '')}\n"
                        f"Failure suggestion: {check_result.get('suggestion', '')}\n\n"
                        "Return 3-5 concise sentences that identify the specific planning mistake, "
                        "the missing prerequisite or ordering issue, and what the next workflow must do differently."
                    )
                ),
            ]
            reflection = self.llm(messages).content.strip()
            return reflection or fallback_reflection
        except Exception as e:
            log_info(f"Reflexion failed, falling back to deterministic summary: {e}")
            return fallback_reflection

    
