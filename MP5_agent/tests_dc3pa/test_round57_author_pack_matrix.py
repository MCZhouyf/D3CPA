from __future__ import annotations

import pytest

from dc3pa.experiments.author_decisions import build_final_exclusion


def test_compiler_builds_strict_50_by_30_matrix():
    tasks = []
    seeds = []
    for difficulty in ("basic", "easy", "medium", "hard", "complex"):
        for index in range(10):
            task = f"{difficulty}-task-{index}"
            tasks.append(
                {
                    "task": task,
                    "difficulty": difficulty,
                    "goal_status": (
                        "experience_covered"
                        if index < 5
                        else "final_heldout_terminal_goal"
                    ),
                }
            )
            for seed_index in range(1, 31):
                seeds.append(
                    {
                        "task": task,
                        "seed": f"{task}-seed-{seed_index}",
                        "seed_index": str(seed_index),
                    }
                )
    manifest = build_final_exclusion(
        tasks,
        seeds,
        manifest_name="paper",
        source_commit="commit",
    )
    assert len(manifest.tasks) == 50
    assert all(len(item.test_seeds) == 30 for item in manifest.tasks)


def test_compiler_does_not_auto_generate_missing_final_seed():
    tasks = [
        {
            "task": "basic-task-0",
            "difficulty": "basic",
            "goal_status": "experience_covered",
        }
    ]
    seeds = [
        {
            "task": "basic-task-0",
            "seed": f"seed-{seed_index}",
            "seed_index": str(seed_index),
        }
        for seed_index in range(1, 30)
    ]
    with pytest.raises(ValueError, match="exactly 30 seeds"):
        build_final_exclusion(
            tasks,
            seeds,
            manifest_name="paper",
            source_commit="commit",
        )
