#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
MP5_ROOT = SCRIPT_DIR.parent
if str(MP5_ROOT) not in sys.path:
    sys.path.insert(0, str(MP5_ROOT))

from dc3pa.contracts import Plan
from dc3pa.memory import HashingTextEncoder, MultimodalMemory, SceneObservation, SuccessfulEpisode


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline Stage-2 memory smoke demo")
    parser.add_argument("--memory-dir", required=True)
    args = parser.parse_args()
    plan = Plan.from_dict(
        {
            "workflow": [
                {
                    "times": "1",
                    "actions": [
                        {
                            "name": "craft",
                            "args": {
                                "obj": {"wooden pickaxe": 1},
                                "materials": {"planks": 3, "stick": 2},
                                "platform": "crafting table"
                            }
                        }
                    ]
                },
                {
                    "times": "1",
                    "actions": [
                        {"name": "mine", "args": {"obj": "cobblestone", "tool": "wooden pickaxe"}}
                    ]
                }
            ]
        },
        task="cobblestone",
    )
    with MultimodalMemory(
        args.memory_dir, text_encoder=HashingTextEncoder(dimensions=64)
    ) as memory:
        result = memory.record_success(
            SuccessfulEpisode(
                task_name="cobblestone",
                plan=plan,
                scenes=[
                    SceneObservation(
                        description="Stone is visible and a wooden pickaxe is equipped.",
                        task_context="obtain cobblestone",
                        inventory={"wooden pickaxe": 1},
                        position="ground",
                    )
                ],
            )
        )
        matches = memory.retrieve_scenes("mine stone for cobblestone", top_k=3)
        output = {
            "record_result": result,
            "cobblestone_prerequisites": [
                edge.to_dict() for edge in memory.dependencies.prerequisites_for("cobblestone")
            ],
            "matches": [
                {
                    "description": match.exemplar.description,
                    "combined_score": match.combined_score,
                    "visual_similarity": match.visual_similarity,
                    "text_similarity": match.text_similarity,
                }
                for match in matches
            ],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
