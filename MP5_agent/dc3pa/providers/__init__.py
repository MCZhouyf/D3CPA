"""Optional LLM provider adapters for reproducible paper runs."""

from .model_profile import (
    GPT51_SNAPSHOT,
    OpenAIResponsesModelProfile,
)
from .openai_responses import (
    AdapterMessage,
    OpenAIResponsesChatAdapter,
    ResponseUsage,
    extract_output_text,
    normalize_input,
)

__all__ = [
    "AdapterMessage",
    "GPT51_SNAPSHOT",
    "OpenAIResponsesChatAdapter",
    "OpenAIResponsesModelProfile",
    "ResponseUsage",
    "extract_output_text",
    "normalize_input",
]
