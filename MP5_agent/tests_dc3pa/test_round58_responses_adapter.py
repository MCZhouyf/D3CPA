from __future__ import annotations

import pytest
import requests

from dc3pa.providers import OpenAIResponsesChatAdapter, OpenAIResponsesModelProfile


class SystemMessage:
    def __init__(self, content):
        self.content = content


class HumanMessage:
    def __init__(self, content):
        self.content = content


class _Response:
    status_code = 200
    headers = {}

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "id": "response-secret-identifier",
            "model": "gpt-5.1",
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


class _WrongModelResponse(_Response):
    def json(self):
        payload = super().json()
        payload["model"] = "gpt-4-turbo"
        return payload


class _WrongModelSession(_Session):
    def post(self, url, headers, json, timeout):
        self.calls.append((url, headers, json, timeout))
        return _WrongModelResponse()


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
    assert payload["model"] == "gpt-5.1"
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


def test_public_metadata_interface_exposes_only_safe_response_facts():
    observed = []
    adapter = OpenAIResponsesChatAdapter(
        profile=OpenAIResponsesModelProfile(),
        purpose="planning",
        api_key="test-key",
        session=_Session(),
        metadata_observer=observed.append,
        sleep=lambda _: None,
    )

    response = adapter.invoke_with_metadata("sensitive prompt")

    assert response.text == "ok"
    assert response.metadata.returned_model == "gpt-5.1"
    assert response.metadata.reasoning_effort == "low"
    assert response.metadata.response_id_sha256
    assert response.metadata.request_text_logged is False
    assert response.metadata.response_text_logged is False
    assert observed == [response.metadata]
    assert "sensitive prompt" not in repr(response.metadata)
    assert "response-secret-identifier" not in repr(response.metadata)


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


def test_adapter_fails_closed_if_provider_does_not_confirm_selected_model():
    session = _WrongModelSession()
    adapter = OpenAIResponsesChatAdapter(
        profile=OpenAIResponsesModelProfile(maximum_retries=0),
        purpose="planning",
        api_key="test-key",
        session=session,
        sleep=lambda _: None,
    )

    with pytest.raises(RuntimeError, match="after 1 attempts") as exc_info:
        adapter.predict("hello")
    assert "selected model identifier" in str(exc_info.value.__cause__)
