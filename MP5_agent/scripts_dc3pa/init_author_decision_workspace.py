#!/usr/bin/env python3
"""Create an external author-decision workspace with empty templates."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


CSV_HEADERS = {
    "final_tasks.csv": ("task", "difficulty", "goal_status"),
    "final_seeds.csv": ("task", "seed", "seed_index"),
    "acquisition.csv": (
        "group_id", "task", "seed", "task_kind", "difficulty", "sequence_index"
    ),
    "development.csv": (
        "group_id", "task", "seed", "role", "difficulty", "goal_status"
    ),
    "phase_budgets.csv": (
        "phase", "maximum_episodes", "maximum_high_level_steps_per_episode",
        "maximum_llm_calls_per_episode", "maximum_replans_per_episode",
        "timeout_seconds_per_episode", "temperature", "top_p", "notes"
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise SystemExit("Workspace directory must be empty")

    for name, headers in CSV_HEADERS.items():
        with (output / name).open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerow(headers)

    settings = {
        "draft_only": True,
        "blueprint_name": "REPLACE_WITH_AUTHOR_APPROVED_NAME",
        "source_commit": "REPLACE_WITH_PINNED_SOURCE_COMMIT",
        "collector_mode": "single_chain_reactive",
        "collector_reads_growing_scene_memory": True,
        "controller_profile": "REPLACE_WITH_MATCHED_CONTROLLER_PROFILE",
        "planner_model_id": "REPLACE_WITH_EXACT_MODEL_AND_VERSION",
        "confidence_model_id": "REPLACE_WITH_EXACT_MODEL_AND_VERSION",
        "environment_search_space": {
            "top_k_values": [],
            "text_threshold_values": [],
            "match_threshold_values": [],
            "environment_scope": "current_context_only",
        },
        "notes": "DRAFT ONLY. Remove draft_only only after all decisions are filled.",
    }
    (output / "settings.DRAFT.json").write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output / "README.md").write_text(
        "# DC3PA author-decision workspace\n\n"
        "Fill every CSV and JSON outside Git. Do not invent or auto-generate "
        "final task lists, seeds, statistical margins, budgets, model IDs, or "
        "prompt content. Use one row per task–seed assignment. Final seeds must "
        "use indices 1 through 30 for each of the 50 tasks.\n",
        encoding="utf-8",
    )
    print(json.dumps({"workspace": str(output), "files": sorted(CSV_HEADERS)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
