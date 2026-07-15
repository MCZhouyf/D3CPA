from __future__ import annotations

import numpy as np
import pytest

from dc3pa.contracts import Action, Plan, PlanStep
from dc3pa.memory.exemplar_store import SceneExemplar
from dc3pa.reliability.contracts import DimensionScore, ReliabilityContext
from dc3pa.reliability.environment_v2 import (
    EnvironmentReliabilityStrategyV2,
    EnvironmentShadowStrategy,
    canonical_action_key,
    validate_environment_impl,
    validate_environment_scope,
)


class _Store:
    def __init__(self, exemplars):
        self._exemplars = list(exemplars)

    def all(self, task_name=None):
        if task_name is None:
            return list(self._exemplars)
        return [item for item in self._exemplars if item.task_name == task_name]


class _TextEncoder:
    def encode_text(self, text):
        text = str(text).lower()
        if "mine" in text and "cobblestone" in text:
            return np.asarray([1.0, 0.0], dtype=np.float32)
        if "find" in text and "tree" in text:
            return np.asarray([0.0, 1.0], dtype=np.float32)
        return np.asarray([0.5, 0.5], dtype=np.float32)


class _Memory:
    image_encoder = None
    text_encoder = _TextEncoder()

    def __init__(self, exemplars):
        self.exemplars = _Store(exemplars)


def _exemplar(
    exemplar_id,
    action,
    image_vector,
    text_vector,
    description="mine cobblestone",
):
    return SceneExemplar(
        episode_id=f"episode-{exemplar_id}",
        task_name="obtain cobblestone",
        description=description,
        task_context="",
        inventory={},
        position="",
        step_id=f"step-{exemplar_id}",
        image_vector=np.asarray(image_vector, dtype=np.float32),
        text_vector=np.asarray(text_vector, dtype=np.float32),
        metadata={"action": action},
        exemplar_id=exemplar_id,
        created_at="2026-01-01T00:00:00+00:00",
    )


def _mine_plan(two_steps=False):
    steps = [
        PlanStep(
            actions=[
                Action(name="mine", args={"obj": "cobblestone", "tool": "wooden_pickaxe"})
            ],
            metadata={"local_subgoal": "mine cobblestone"},
        )
    ]
    if two_steps:
        steps.append(
            PlanStep(
                actions=[
                    Action(name="mine", args={"obj": "cobblestone", "tool": "wooden_pickaxe"})
                ],
                metadata={"local_subgoal": "mine cobblestone again"},
            )
        )
    return Plan(task="obtain cobblestone", steps=steps)


def test_environment_mode_validation_is_closed():
    assert validate_environment_impl("legacy_v1") == "legacy_v1"
    assert validate_environment_impl("shadow_v2") == "shadow_v2"
    assert validate_environment_scope("current_context_only") == "current_context_only"
    with pytest.raises(ValueError):
        validate_environment_impl("top10")
    with pytest.raises(ValueError):
        validate_environment_scope("all")


def test_canonical_action_key_is_stable():
    action = Action(
        name="mine", args={"obj": "cobblestone", "tool": "wooden_pickaxe"}
    )
    assert canonical_action_key(action) == "mine:cobblestone"
    craft = Action(
        name="craft",
        args={
            "obj": {"wooden_pickaxe": 1},
            "materials": {"planks": 3, "stick": 2},
            "platform": "crafting_table",
        },
    )
    assert canonical_action_key(craft) == "craft:wooden_pickaxe"


def test_topk_is_deterministic_and_uses_actual_candidate_count():
    exemplars = [
        _exemplar("a", {"name": "mine", "args": {"obj": "cobblestone"}}, [1, 0], [1, 0]),
        _exemplar("b", {"name": "mine", "args": {"obj": "cobblestone"}}, [0.8, 0.2], [1, 0]),
        _exemplar("c", {"name": "mine", "args": {"obj": "cobblestone"}}, [0.7, 0.3], [1, 0]),
        _exemplar("d", {"name": "mine", "args": {"obj": "cobblestone"}}, [-1, 0], [1, 0]),
    ]
    strategy = EnvironmentReliabilityStrategyV2(
        _Memory(exemplars),
        top_k=3,
        text_threshold=0.5,
        match_threshold=0.1,
        scope="legacy_all_steps",
    )
    result = strategy.score(
        _mine_plan(),
        0,
        object(),
        ReliabilityContext(image_vector=np.asarray([1.0, 0.0])),
    )
    assert result.available
    assert len(result.evidence["matches"]) == 3
    assert [item["exemplar_id"] for item in result.evidence["matches"]] == ["a", "b", "c"]
    assert result.evidence["relevant_candidate_count"] == 4


def test_action_filter_prevents_visually_similar_wrong_action_from_winning():
    wrong = _exemplar(
        "tree",
        {"name": "find", "args": {"obj": "tree"}},
        [1, 0],
        [0, 1],
        description="find tree",
    )
    right = _exemplar(
        "stone",
        {"name": "mine", "args": {"obj": "cobblestone"}},
        [0.8, 0.2],
        [1, 0],
    )
    strategy = EnvironmentReliabilityStrategyV2(
        _Memory([wrong, right]),
        top_k=3,
        text_threshold=0.5,
        match_threshold=0.1,
        scope="legacy_all_steps",
    )
    result = strategy.score(
        _mine_plan(),
        0,
        object(),
        ReliabilityContext(image_vector=np.asarray([1.0, 0.0])),
    )
    assert result.available
    assert [match["exemplar_id"] for match in result.evidence["matches"]] == ["stone"]


def test_unknown_and_mismatch_are_not_conflated():
    unknown_strategy = EnvironmentReliabilityStrategyV2(
        _Memory(
            [
                _exemplar(
                    "tree",
                    {"name": "find", "args": {"obj": "tree"}},
                    [1, 0],
                    [0, 1],
                    description="find tree",
                )
            ]
        ),
        scope="legacy_all_steps",
    )
    unknown = unknown_strategy.score(
        _mine_plan(),
        0,
        object(),
        ReliabilityContext(image_vector=np.asarray([1.0, 0.0])),
    )
    assert not unknown.available
    assert unknown.evidence["status"] == "unknown"
    assert unknown.evidence["neutral_compatibility_for_future_fusion"] == 0.5

    mismatch_strategy = EnvironmentReliabilityStrategyV2(
        _Memory(
            [
                _exemplar(
                    "opposite",
                    {"name": "mine", "args": {"obj": "cobblestone"}},
                    [-1, 0],
                    [1, 0],
                )
            ]
        ),
        text_threshold=0.5,
        match_threshold=0.5,
        scope="legacy_all_steps",
    )
    mismatch = mismatch_strategy.score(
        _mine_plan(),
        0,
        object(),
        ReliabilityContext(image_vector=np.asarray([1.0, 0.0])),
    )
    assert mismatch.available
    assert mismatch.evidence["status"] == "mismatch"
    assert mismatch.probability == pytest.approx(0.0)


def test_current_context_scope_rejects_future_plan_step():
    strategy = EnvironmentReliabilityStrategyV2(
        _Memory(
            [
                _exemplar(
                    "stone",
                    {"name": "mine", "args": {"obj": "cobblestone"}},
                    [1, 0],
                    [1, 0],
                )
            ]
        ),
        scope="current_context_only",
    )
    score = strategy.score(
        _mine_plan(two_steps=True),
        1,
        object(),
        ReliabilityContext(
            image_vector=np.asarray([1.0, 0.0]),
            metadata={"environment_step_index": 0},
        ),
    )
    assert not score.available
    assert score.evidence["status"] == "future_context_unavailable"


def test_shadow_never_changes_legacy_dimension_score():
    legacy_score = DimensionScore(
        dimension="environment",
        probability=0.77,
        available=True,
        reason="legacy",
        evidence={"legacy": True},
    )

    class _Legacy:
        def score(self, *args, **kwargs):
            return legacy_score

    candidate = EnvironmentReliabilityStrategyV2(
        _Memory([]), scope="legacy_all_steps"
    )
    shadow = EnvironmentShadowStrategy(_Legacy(), candidate)
    result = shadow.score(
        _mine_plan(),
        0,
        object(),
        ReliabilityContext(image_vector=np.asarray([1.0, 0.0])),
    )
    assert result.probability == 0.77
    assert result.reason == "legacy"
    assert result.evidence["legacy"] is True
    assert result.evidence["shadow_v2"]["status"] == "unknown"
