# -- coding: utf-8 --
import traceback
import time
from utils import *
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
        assert  self.memory is not None, "Please input memory"

    def _is_non_retryable_llm_error(self, error):
        # openai<1 exposed exception classes through ``openai.error`` while
        # current SDKs export them at the module root.  G0 must classify an
        # auth/quota refusal deterministically under either supported client.
        error_namespace = getattr(openai, "error", openai)
        candidates = (
            getattr(error_namespace, "AuthenticationError", None),
            getattr(error_namespace, "PermissionError", None),
            getattr(openai, "AuthenticationError", None),
            getattr(openai, "PermissionDeniedError", None),
        )
        non_retryable_types = tuple(
            candidate for candidate in candidates if isinstance(candidate, type)
        )
        if isinstance(error, non_retryable_types):
            return True
        message = str(error).lower()
        non_retryable_markers = (
            "quota",
            "insufficient",
            "forbidden",
            "unauthorized",
            "invalid api key",
            "incorrect api key",
            "request rate exceeds",
            "tpm limit",
        )
        return any(marker in message for marker in non_retryable_markers)

    def get_workflow(self, message, max_retries=2):

        if max_retries == 0:
            log_info("************Failed to get workflow. Consider updating your prompt.************\n\n")
            return {}

        try:   
            #print(f"{message[1]}")
            log_info("Planner LLM request started")
            if os.environ.get("DC3PA_G1_COMPACT_JSON", "").lower() in {"1", "true", "yes", "on"}:
                message = [
                    SystemMessage(
                        content=(
                            "Return only one complete, valid JSON object. Do not use Markdown fences, "
                            "do not add prose, and keep whitespace minimal. The object must contain a "
                            "non-empty workflow array; finish all brackets before ending the response."
                        )
                    ),
                    *list(message),
                ]
            workflow_dict = self.llm(message).content
            log_info("Planner LLM request finished")
            print(f"Plan are finished")
            log_info(f"Create Workflow Result: {workflow_dict}")
            workflow_dict = fix_and_parse_json(workflow_dict)
            return workflow_dict
        except Exception as e:
            log_info(f"Error arises in Plan Workflow part: {e} Trying again!\n\n")
            log_info(traceback.format_exc())
            if self._is_non_retryable_llm_error(e):
                log_info("Planner LLM error is not retryable; failing fast.")
                raise
            self.memory.reset_current_environment_information()
            wait_seconds = min(2 ** (5 - max_retries), 12)
            log_info(f"Planner retry backoff: sleeping {wait_seconds} seconds before retry.")
            time.sleep(wait_seconds)

            return self.get_workflow(
                message, 
                max_retries=max_retries - 1
            )
        
