from __future__ import annotations

import base64
import os
from pathlib import Path

from agent.utils.percipient_mllm import ChatOpenAIVision


def test_chat_openai_vision_uses_openai_api_base(monkeypatch, tmp_path: Path):
    image_path = tmp_path / "tiny.jpg"
    image_path.write_bytes(base64.b64decode("/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAVEQEBAAAAAAAAAAAAAAAAAAAAAf/aAAwDAQACEAMQAAAB6gD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Ap//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2Q=="))

    monkeypatch.setenv("OPENAI_API_BASE", "https://xiaoai.plus/v1")

    captured = {}

    class FakeResponse:
        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, headers=None, json=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("agent.utils.percipient_mllm.requests.post", fake_post)
    monkeypatch.setattr(
        "agent.utils.percipient_mllm.load_prompt",
        lambda name: f"prompt:{name}",
    )

    model = ChatOpenAIVision("active", "gpt-4-turbo", "test-key")
    result = model.query("describe", str(image_path))

    assert result == "ok"
    assert captured["url"] == "https://xiaoai.plus/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "gpt-4-turbo"


def test_chat_openai_vision_defaults_to_official_api_when_base_is_unset(monkeypatch, tmp_path: Path):
    image_path = tmp_path / "tiny.jpg"
    image_path.write_bytes(base64.b64decode("/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAVEQEBAAAAAAAAAAAAAAAAAAAAAf/aAAwDAQACEAMQAAAB6gD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Ap//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2Q=="))

    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    captured = {}

    class FakeResponse:
        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, headers=None, json=None):
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr("agent.utils.percipient_mllm.requests.post", fake_post)
    monkeypatch.setattr(
        "agent.utils.percipient_mllm.load_prompt",
        lambda name: f"prompt:{name}",
    )

    model = ChatOpenAIVision("caption", "gpt-4-turbo", "test-key")
    model.query("describe", str(image_path))

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
