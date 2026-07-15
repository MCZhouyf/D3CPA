from __future__ import annotations

import numpy as np

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.memory import CallableTextEncoder, MultimodalMemory, SceneObservation, SuccessfulEpisode
from dc3pa.reliability import (
    CallableConfidenceProvider,
    HybridProbabilityConfig,
    ReliabilityContext,
    build_hybrid_probability_model,
)


def _plan() -> Plan:
    return Plan(
        task="obtain cobblestone",
        steps=[
            PlanStep(
                actions=[
                    Action(
                        "mine",
                        {"obj": "cobblestone", "tool": "wooden_pickaxe"},
                    )
                ],
                metadata={"local_subgoal": "mine cobblestone"},
            )
        ],
    )


def test_shadow_v2_returns_exact_legacy_environment_score(tmp_path):
    plan = _plan()
    provider = CallableConfidenceProvider(
        lambda request: {"confidence": 0.5, "reason": "offline test"}
    )
    text_encoder = CallableTextEncoder(lambda text: np.asarray([1.0, 0.0]))
    with MultimodalMemory(tmp_path / "memory", text_encoder=text_encoder) as memory:
        memory.record_success(
            SuccessfulEpisode(
                task_name=plan.task,
                plan=plan,
                scenes=[
                    SceneObservation(
                        description="mine cobblestone",
                        task_context="obtain cobblestone",
                        inventory={},
                        position="surface",
                        image_vector=np.asarray([0.0, 1.0]),
                        text_vector=np.asarray([1.0, 0.0]),
                        metadata={
                            "action": {"name": "mine", "args": {"obj": "cobblestone"}},
                            "action_key": "mine:cobblestone",
                        },
                    )
                ],
            )
        )
        legacy = build_hybrid_probability_model(
            memory,
            provider,
            HybridProbabilityConfig(environment_impl="legacy_v1"),
        )
        shadow = build_hybrid_probability_model(
            memory,
            provider,
            HybridProbabilityConfig(
                environment_impl="shadow_v2",
                environment_scope="current_context_only",
            ),
        )
        context = ReliabilityContext(
            task_context="obtain cobblestone",
            image_vector=np.asarray([1.0, 0.0]),
            metadata={"environment_step_index": 0},
        )
        state = AgentState(task=plan.task)
        legacy_score = legacy.environment.score(plan, 0, state, context)
        shadow_score = shadow.environment.score(plan, 0, state, context)

    assert shadow_score.probability == legacy_score.probability
    assert shadow_score.available == legacy_score.available
    assert shadow_score.hard_conflict == legacy_score.hard_conflict
    assert shadow_score.evidence["shadow_v2"]["status"] in {"matched", "mismatch"}
