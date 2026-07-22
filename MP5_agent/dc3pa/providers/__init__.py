"""Optional LLM provider adapters for reproducible paper runs."""

from .model_profile import (
    GPT51_MODEL_ID,
    OpenAIResponsesModelProfile,
)
from .openai_responses import (
    AdapterMessage,
    OpenAIResponsesChatAdapter,
    ProviderTransportError,
    ResponseUsage,
    SafeResponseMetadata,
    TextResponseWithMetadata,
    extract_output_text,
    normalize_input,
)

__all__ = [
    "AdapterMessage",
    "GPT51_MODEL_ID",
    "OpenAIResponsesChatAdapter",
    "OpenAIResponsesModelProfile",
    "ProviderTransportError",
    "ResponseUsage",
    "SafeResponseMetadata",
    "TextResponseWithMetadata",
    "extract_output_text",
    "normalize_input",
]
