#!/usr/bin/env python3
"""Generate the deterministic DC3PA GPT-5.1 reference design pack."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.reference_design import (
    ReferenceDesignConfig,
    build_reference_design,
    load_task_catalog,
)


def _write_csv(path: Path, headers, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-catalog", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise SystemExit("Output directory must be empty")

    design = build_reference_design(
        load_task_catalog(args.task_catalog),
        config=ReferenceDesignConfig(source_commit=args.source_commit),
    )
    payload = design.to_dict()
    (output / "reference_design.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output / "final_test_exclusion.json").write_text(
        json.dumps(
            design.final_test_exclusion.to_dict(),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "activation_policy.json").write_text(
        json.dumps(
            design.activation_policy.to_dict(), indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "data_sufficiency_policy.json").write_text(
        json.dumps(
            design.data_sufficiency_policy, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "model_profile.json").write_text(
        json.dumps(design.model_profile, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "dry_run_selection.json").write_text(
        json.dumps(
            {"group_ids": list(design.dry_run_group_ids)},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    _write_csv(
        output / "final_tasks.csv",
        ("task", "difficulty", "goal_status"),
        [
            {
                "task": item.task,
                "difficulty": item.difficulty,
                "goal_status": item.goal_status,
            }
            for item in design.final_test_exclusion.tasks
        ],
    )
    _write_csv(
        output / "final_seeds.csv",
        ("task", "seed", "seed_index"),
        [
            {"task": item.task, "seed": seed, "seed_index": index}
            for item in design.final_test_exclusion.tasks
            for index, seed in enumerate(item.test_seeds, start=1)
        ],
    )
    _write_csv(
        output / "acquisition.csv",
        (
            "group_id", "task", "seed", "task_kind", "difficulty",
            "sequence_index",
        ),
        [
            {
                "group_id": item.group_id,
                "task": item.task,
                "seed": item.seed,
                "task_kind": item.task_kind,
                "difficulty": item.difficulty,
                "sequence_index": item.sequence_index,
            }
            for item in design.acquisition_assignments
        ],
    )
    _write_csv(
        output / "development.csv",
        ("group_id", "task", "seed", "role", "difficulty", "goal_status"),
        [
            {
                "group_id": item.group_id,
                "task": item.task,
                "seed": item.seed,
                "role": item.role,
                "difficulty": item.difficulty,
                "goal_status": item.goal_status,
            }
            for item in design.development_assignments
        ],
    )
    _write_csv(
        output / "phase_budgets.csv",
        (
            "phase", "maximum_episodes",
            "maximum_high_level_steps_per_episode",
            "maximum_llm_calls_per_episode",
            "maximum_replans_per_episode",
            "timeout_seconds_per_episode", "temperature", "top_p", "notes",
        ),
        [item.to_dict() for item in design.phase_budgets],
    )

    report = [
        "# DC3PA GPT-5.1 Reference Design",
        "",
        f"- Design ID: `{design.design_id}`",
        f"- Source commit: `{args.source_commit}`",
        f"- Model snapshot: `{design.config.model_snapshot}`",
        f"- Split salt: `{design.config.split_salt}`",
        f"- Final-seed salt: `{design.config.final_seed_salt}`",
        f"- Acquisition-seed salt: `{design.config.acquisition_seed_salt}`",
        f"- Development-seed salt: `{design.config.development_seed_salt}`",
        f"- Development-role salt: `{design.config.role_salt}`",
        "- Split: horizon-adjacent deterministic pairs; one covered and one held-out per pair.",
        "- Final seeds: deterministic positive 31-bit seeds, 30 per task.",
        f"- Acquisition episodes: {len(design.acquisition_assignments)}",
        f"- Development episodes: {len(design.development_assignments)}",
        "- Development task split per difficulty: 3 train / 1 tune / 1 holdout covered tasks.",
        "- Final held-out tasks never enter acquisition or development.",
        "",
        "## Important",
        "",
        "This pack is a recommended, deterministic reference design. Review the "
        "generated task split once, then freeze it before real acquisition. "
        "Later adjustments may use train/tune data only and require a new "
        "Blueprint approval; final status/seeds and locked holdout outcomes "
        "must not be changed after observation.",
        "",
    ]
    (output / "reference_design_report.md").write_text(
        "\n".join(report), encoding="utf-8"
    )
    print(json.dumps({"design_id": design.design_id, "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
