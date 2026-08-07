# -- coding: utf-8 --
import traceback
import time
import os
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
        self._api_base = os.environ.get("OPENAI_API_BASE", "https://api.xiaoai.plus/v1")
        temperature = float(os.environ.get("DC3PA_LLM_TEMPERATURE", temperature))
        self._llm_options = {
            "model_name": model_name,
            "openai_api_base": self._api_base,
            "temperature": temperature,
            "request_timeout": float(os.environ.get("DC3PA_LLM_REQUEST_TIMEOUT", "180")),
            "max_retries": int(os.environ.get("DC3PA_LLM_MAX_RETRIES", "1")),
            "max_tokens": int(os.environ.get("DC3PA_LLM_MAX_TOKENS", "4096")),
            "model_kwargs": {"top_p": float(os.environ.get("DC3PA_LLM_TOP_P", "1.0"))},
        }
        configured_keys = [
            candidate.strip()
            for candidate in os.environ.get("DC3PA_LLM_API_KEYS", "").split(",")
            if candidate.strip()
        ]
        if not configured_keys:
            configured_keys = [openai_key]
        # Preserve order while avoiding redundant requests with the same key.
        self._api_keys = tuple(dict.fromkeys(configured_keys))
        self._active_key_index = 0
        self.llm = self._build_llm(self._api_keys[self._active_key_index])

        self.memory = memory
        assert  self.memory is not None, "Please input memory"

    def _build_llm(self, api_key):
        """Build one serial client without exposing credential material."""
        os.environ["OPENAI_API_KEY"] = api_key
        openai.api_base = self._api_base
        return ChatOpenAI(openai_api_key=api_key, **self._llm_options)

    def _rotate_api_key(self):
        """Select the next configured relay key after a transport-side failure."""
        keys = getattr(self, "_api_keys", ())
        if len(keys) < 2:
            return False
        next_index = (getattr(self, "_active_key_index", 0) + 1) % len(keys)
        if next_index == getattr(self, "_active_key_index", 0):
            return False
        self._active_key_index = next_index
        self.llm = self._build_llm(keys[next_index])
        log_info(
            "Planner relay transport failure: switched to the next configured API key "
            f"({next_index + 1}/{len(keys)}; credential redacted)."
        )
        return True

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
        )
        return any(marker in message for marker in non_retryable_markers)

    def _is_relay_transport_error(self, error):
        """Whether retrying with another key can help the same serial request."""
        if self._is_non_retryable_llm_error(error):
            return False
        error_namespace = getattr(openai, "error", openai)
        candidates = (
            getattr(error_namespace, "APIConnectionError", None),
            getattr(error_namespace, "APITimeoutError", None),
            getattr(error_namespace, "RateLimitError", None),
            getattr(openai, "APIConnectionError", None),
            getattr(openai, "APITimeoutError", None),
            getattr(openai, "RateLimitError", None),
        )
        transport_types = tuple(candidate for candidate in candidates if isinstance(candidate, type))
        if isinstance(error, transport_types):
            return True
        message = str(error).lower()
        return any(marker in message for marker in (
            "connection error", "connection reset", "connect timeout", "read timeout",
            "timed out", "rate limit", "too many requests", "429", "502", "503", "504",
        ))

    def get_workflow(self, message, max_retries=None):
        if max_retries is None:
            max_retries = int(os.environ.get("DC3PA_LLM_PLANNER_MAX_RETRIES", "8"))
        max_retries = max(1, int(max_retries))
        request_message = message

        for attempt in range(1, max_retries + 1):
            try:
                log_info("Planner LLM request started")
                if os.environ.get("DC3PA_G1_COMPACT_JSON", "").lower() in {"1", "true", "yes", "on"}:
                    request_message = [
                        SystemMessage(
                            content=(
                                "Return only one complete, valid JSON object. Do not use Markdown fences, "
                                "do not add prose, and keep whitespace minimal. The object must contain a "
                                "non-empty workflow array; finish all brackets before ending the response."
                            )
                        ),
                        *list(message),
                    ]
                workflow_dict = self.llm(request_message).content
                log_info("Planner LLM request finished")
                print("Plan are finished")
                log_info(f"Create Workflow Result: {workflow_dict}")
                return fix_and_parse_json(workflow_dict)
            except Exception as error:
                log_info(f"Error arises in Plan Workflow part: {error} Trying again!\n\n")
                log_info(traceback.format_exc())
                if self._is_non_retryable_llm_error(error):
                    log_info("Planner LLM error is not retryable; failing fast.")
                    raise
                self.memory.reset_current_environment_information()
                if self._is_relay_transport_error(error):
                    self._rotate_api_key()
                if attempt == max_retries:
                    break
                wait_seconds = min(2 ** (attempt - 1), 60)
                log_info(
                    f"Planner retry {attempt}/{max_retries}: sleeping {wait_seconds} seconds before retry."
                )
                time.sleep(wait_seconds)

        log_info("************Failed to get workflow after serial relay retries.************\n\n")
        return {}
        
