from __future__ import annotations

import pytest
import requests
from langchain.schema import HumanMessage, SystemMessage

from dc3pa.providers import OpenAIResponsesChatAdapter, OpenAIResponsesModelProfile


class _Response:
    status_code = 200
    headers = {}

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "ok"}],
                }
            ],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "output_tokens_details": {"reasoning_tokens": 2},
            },
        }


class _Session:
    def __init__(self):
        self.calls = []

    def post(self, url, headers, json, timeout):
        self.calls.append((url, headers, json, timeout))
        return _Response()


class _FailureSession:
    def __init__(self):
        self.calls = 0

    def post(self, url, headers, json, timeout):
        self.calls += 1
        raise requests.ConnectionError("network unavailable")


def test_adapter_sends_responses_request_without_sampling_or_prompt_logging():
    session = _Session()
    usage = []
    adapter = OpenAIResponsesChatAdapter(
        profile=OpenAIResponsesModelProfile(),
        purpose="planning",
        api_key="test-key",
        session=session,
        usage_observer=usage.append,
        sleep=lambda _: None,
    )
    assert adapter.predict("hello") == "ok"
    assert len(session.calls) == 1
    url, headers, payload, timeout = session.calls[0]
    assert url.endswith("/v1/responses")
    assert payload["model"] == "gpt-5.1-2025-11-13"
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["store"] is False
    assert payload["max_output_tokens"] == 8192
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert usage[0].reasoning_tokens == 2


def test_adapter_accepts_langchain_messages_invoke_and_call_interfaces():
    session = _Session()
    adapter = OpenAIResponsesChatAdapter(
        profile=OpenAIResponsesModelProfile(),
        purpose="reflection",
        api_key="test-key",
        session=session,
        sleep=lambda _: None,
    )
    messages = [SystemMessage(content="system"), HumanMessage(content="user")]

    assert adapter.invoke(messages).content == "ok"
    assert adapter(messages).content == "ok"
    payload = session.calls[0][2]
    assert payload["input"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
    ]
    assert payload["max_output_tokens"] == 4096


def test_adapter_exhausts_profile_retries_and_preserves_failure():
    session = _FailureSession()
    adapter = OpenAIResponsesChatAdapter(
        profile=OpenAIResponsesModelProfile(maximum_retries=3),
        purpose="planning",
        api_key="test-key",
        session=session,
        sleep=lambda _: None,
    )

    with pytest.raises(RuntimeError, match="after 4 attempts"):
        adapter.predict("hello")
    assert session.calls == 4
