from __future__ import annotations

import numpy as np

from dc3pa.contracts import Action, Plan, PlanStep
from dc3pa.memory.exemplar_store import SceneExemplar
from dc3pa.reliability import ReliabilityContext
from dc3pa.reliability.environment_v2 import EnvironmentReliabilityStrategyV2


class _Store:
    def __init__(self, exemplars):
        self._exemplars = tuple(exemplars)

    def all(self, task_name=None):
        return list(self._exemplars)


class _TextEncoder:
    def encode_text(self, text):
        return np.asarray([1.0, 0.0], dtype=np.float32)


class _Memory:
    image_encoder = None
    text_encoder = _TextEncoder()

    def __init__(self, exemplars):
        self.exemplars = _Store(exemplars)


def _plan() -> Plan:
    return Plan(
        task="obtain cobblestone",
        steps=[
            PlanStep(
                actions=[Action("mine", {"obj": "cobblestone", "tool": "wooden_pickaxe"})],
                metadata={"local_subgoal": "mine cobblestone"},
            )
        ],
    )


def _exemplar() -> SceneExemplar:
    return SceneExemplar(
        episode_id="episode-1",
        task_name="obtain cobblestone",
        description="mine cobblestone",
        task_context="",
        inventory={},
        position="surface",
        step_id="step-1",
        image_vector=np.asarray([1.0, 0.0], dtype=np.float32),
        text_vector=np.asarray([1.0, 0.0], dtype=np.float32),
        metadata={"action_key": "mine:cobblestone"},
        exemplar_id="exemplar-1",
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_current_context_scope_requires_explicit_step_ownership():
    strategy = EnvironmentReliabilityStrategyV2(
        _Memory([_exemplar()]), scope="current_context_only"
    )
    score = strategy.score(
        _plan(),
        0,
        object(),
        ReliabilityContext(image_vector=np.asarray([1.0, 0.0])),
    )
    assert not score.available
    assert score.evidence["status"] == "future_context_unavailable"
    assert "not specified" in score.reason
