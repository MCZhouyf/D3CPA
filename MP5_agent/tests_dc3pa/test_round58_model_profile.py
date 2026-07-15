from __future__ import annotations

from dc3pa.providers import GPT51_MODEL_ID, OpenAIResponsesModelProfile


def test_profile_uses_author_selected_model_low_effort_and_no_storage():
    profile = OpenAIResponsesModelProfile().with_id()
    assert profile.model == GPT51_MODEL_ID == "gpt-5.1"
    assert profile.reasoning_effort == "low"
    assert profile.store is False
    assert profile.token_cap_for("planning") == 8192
    assert profile.profile_id == OpenAIResponsesModelProfile().with_id().profile_id
