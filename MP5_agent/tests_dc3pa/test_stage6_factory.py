from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from dc3pa.integration import (
    Stage6RuntimeConfig,
    build_legacy_state_provider,
    build_stage6_runtime,
)
from dc3pa.memory import MultimodalMemory


class Env:
    def __init__(self):
        self.calls = 0

    def step(self, action):
        self.calls += 1
        return {"rgb": [[[0, 0, 0]]]}, 0, False, {}


class LegacyMemory:
    inventory = {}
    llm = lambda self, prompt: '{"confidence": 0.9, "reason": "ok"}'

    def generate_prompt_template(self, **kwargs):
        return ["prompt"]

    def add_successful_workflow(self, *args, **kwargs):
        return True


class Planner:
    def get_workflow(self, message):
        return {
            "workflow": [
                {"times": "1", "actions": [{"name": "find", "args": {"obj": "log"}}]}
            ]
        }


class Controller:
    def check_and_execute_workflow(self, **kwargs):
        return {"success": True}, False

    def check_done(self, task_information, memory=None):
        return True


def test_state_provider_updates_legacy_memory_callback():
    env = Env()
    memory = LegacyMemory()
    calls = []
    provider = build_legacy_state_provider(
        env=env,
        legacy_memory=memory,
        share_memory=lambda target, observation: calls.append((target, observation)),
    )
    snapshot = provider.snapshot({"task": "log"}, False)
    assert env.calls == 1 and calls
    assert snapshot.state.task == "log"


def test_track_e_state_provider_encodes_current_rgb_before_planning():
    env = Env()
    memory = LegacyMemory()

    class Encoder:
        def __init__(self):
            self.images = []

        def encode_image(self, image):
            self.images.append(np.asarray(image).copy())
            return np.asarray([0.25, 0.75], dtype=np.float32)

    encoder = Encoder()
    provider = build_legacy_state_provider(
        env=env,
        legacy_memory=memory,
        share_memory=lambda target, observation: None,
        image_encoder=encoder,
    )
    snapshot = provider.snapshot({"task": "log"}, False)
    assert len(encoder.images) == 1
    assert snapshot.reliability_context.image_vector.tolist() == [0.25, 0.75]


def test_track_e_state_provider_rejects_invalid_image_vector():
    class InvalidEncoder:
        def encode_image(self, image):
            return np.asarray([[float("nan")]])

    provider = build_legacy_state_provider(
        env=Env(),
        legacy_memory=LegacyMemory(),
        share_memory=lambda target, observation: None,
        image_encoder=InvalidEncoder(),
    )
    with pytest.raises(ValueError, match="invalid vector"):
        provider.snapshot({"task": "log"}, False)


def test_factory_builds_reasoning_only_without_model_or_multimodal_memory():
    env = Env()
    memory = LegacyMemory()
    provider = build_legacy_state_provider(
        env=env,
        legacy_memory=memory,
        share_memory=lambda target, observation: None,
    )
    bundle = build_stage6_runtime(
        env=env,
        runtime_config=Stage6RuntimeConfig(mode="reasoning_only", max_execution_attempts=1),
        legacy_planner=Planner(),
        legacy_controller=Controller(),
        legacy_memory=memory,
        state_provider=provider,
    )
    result = bundle.runtime.run_task({"task": "log"})
    assert result.success
    assert bundle.cognitive_planner is None


def test_factory_requires_real_dependencies_in_dc3pa_mode(tmp_path):
    env = Env()
    memory = LegacyMemory()
    provider = build_legacy_state_provider(
        env=env,
        legacy_memory=memory,
        share_memory=lambda target, observation: None,
    )
    with pytest.raises(ValueError, match="multimodal_memory"):
        build_stage6_runtime(
            env=env,
            runtime_config=Stage6RuntimeConfig(mode="dc3pa"),
            legacy_planner=Planner(),
            legacy_controller=Controller(),
            legacy_memory=memory,
            state_provider=provider,
            chat_model=memory.llm,
        )
    with MultimodalMemory(tmp_path / "memory") as mm:
        bundle = build_stage6_runtime(
            env=env,
            runtime_config=Stage6RuntimeConfig(mode="dc3pa"),
            legacy_planner=Planner(),
            legacy_controller=Controller(),
            legacy_memory=memory,
            state_provider=provider,
            multimodal_memory=mm,
            chat_model=memory.llm,
        )
        assert bundle.cognitive_planner is not None


def test_cached_state_provider_does_not_step_environment():
    env = Env()
    memory = LegacyMemory()
    initial = {"rgb": [[[0, 0, 0]]]}
    provider = build_legacy_state_provider(
        env=env,
        legacy_memory=memory,
        share_memory=lambda target, observation: None,
        refresh_environment=False,
        initial_observation=initial,
    )
    snapshot = provider.snapshot({"task": "log"}, False)
    assert env.calls == 0
    assert snapshot.reliability_context.image is not None
