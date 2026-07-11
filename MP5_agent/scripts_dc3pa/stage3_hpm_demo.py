#!/usr/bin/env python3
"""Offline Stage-3 smoke demo; no MineDojo or network access is required."""

from __future__ import annotations

import sys
from pathlib import Path

_MP5_ROOT = Path(__file__).resolve().parents[1]
if str(_MP5_ROOT) not in sys.path:
    sys.path.insert(0, str(_MP5_ROOT))

import argparse
import json
import tempfile

import numpy as np

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.memory import (
    CallableTextEncoder,
    MultimodalMemory,
    SceneObservation,
    SuccessfulEpisode,
)
from dc3pa.reliability import (
    CallableConfidenceProvider,
    HybridProbabilityConfig,
    ReliabilityContext,
    build_hybrid_probability_model,
)


def build_reference_plan() -> Plan:
    return Plan(
        task="obtain cobblestone",
        plan_id="reference-plan",
        steps=[
            PlanStep(
                step_id="reference-mine",
                actions=[
                    Action(
                        "mine",
                        {"obj": "cobblestone", "tool": "wooden_pickaxe"},
                    )
                ],
            )
        ],
    )


def run(memory_root: Path) -> dict:
    reference = build_reference_plan()
    with MultimodalMemory(
        memory_root,
        text_encoder=CallableTextEncoder(
            lambda text: np.asarray([1.0, 0.0], dtype=np.float32)
        ),
    ) as memory:
        memory.record_success(
            SuccessfulEpisode(
                episode_id="reference-episode",
                task_name=reference.task,
                plan=reference,
                scenes=[
                    SceneObservation(
                        description="stone wall in reach",
                        task_context=reference.task,
                        inventory={"wooden_pickaxe": 1},
                        position="surface",
                        image_vector=np.asarray([1.0, 0.0], dtype=np.float32),
                        text_vector=np.asarray([1.0, 0.0], dtype=np.float32),
                    )
                ],
            )
        )
        candidate = Plan(
            task=reference.task,
            plan_id="candidate-plan",
            steps=[
                PlanStep(
                    step_id="candidate-mine",
                    actions=[
                        Action(
                            "mine",
                            {"obj": "cobblestone", "tool": "wooden_pickaxe"},
                        )
                    ],
                )
            ],
        )
        model = build_hybrid_probability_model(
            memory,
            CallableConfidenceProvider(
                lambda request: {
                    "confidence": 0.9,
                    "reason": "The action is plausible if its tool prerequisite is met.",
                }
            ),
            HybridProbabilityConfig(
                visual_similarity_weight=0.7,
                memory_weight_growth=0.02,
            ),
        )
        result = model.score_step(
            candidate,
            0,
            AgentState(task=candidate.task, inventory={}),
            ReliabilityContext(
                task_context=candidate.task,
                image_vector=np.asarray([1.0, 0.0], dtype=np.float32),
            ),
        )
        assert result.scores["knowledge"].probability == 0.0
        assert result.scores["model"].probability == 0.9
        assert result.scores["environment"].probability == 1.0
        assert result.hard_conflict
        return result.to_dict()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-root", type=Path)
    args = parser.parse_args()
    if args.memory_root is not None:
        result = run(args.memory_root)
    else:
        with tempfile.TemporaryDirectory(prefix="dc3pa-stage3-") as directory:
            result = run(Path(directory))
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
