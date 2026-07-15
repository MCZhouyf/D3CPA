#!/usr/bin/env python3
"""Build and freeze an author-approved DC3PA real-experiment blueprint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.blueprint import (
    AcquisitionAssignment,
    AuthorApproval,
    EnvironmentSearchSpace,
    PhaseBudget,
    RealExperimentBlueprint,
    save_blueprint,
    sha256_file,
)
from dc3pa.reliability.activation_policy import load_activation_policy
from dc3pa.reliability.development_protocol import GroupAssignment
from dc3pa.reliability.final_test_exclusion import load_final_test_exclusion


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--author-spec", required=True)
    parser.add_argument("--final-test-exclusion", required=True)
    parser.add_argument("--activation-policy", required=True)
    parser.add_argument("--data-sufficiency-policy", required=True)
    parser.add_argument("--output-blueprint", required=True)
    parser.add_argument(
        "--print-content-sha-for-approval",
        action="store_true",
        help=(
            "Print the content SHA before approval. The author then inserts it "
            "into author_approval and reruns without this flag."
        ),
    )
    args = parser.parse_args()

    spec = json.loads(Path(args.author_spec).read_text(encoding="utf-8"))
    if spec.get("draft_only") is True:
        raise SystemExit(
            "Refusing to build from a draft_only author spec. Copy it outside "
            "Git, fill every author decision, remove draft_only or set it to "
            "false, then rerun."
        )
    exclusion = load_final_test_exclusion(args.final_test_exclusion)
    policy = load_activation_policy(args.activation_policy)

    acquisition = tuple(
        AcquisitionAssignment(**item)
        for item in spec["acquisition_assignments"]
    )
    development = tuple(
        GroupAssignment(**item)
        for item in spec["development_assignments"]
    )
    budgets = tuple(PhaseBudget(**item) for item in spec["phase_budgets"])
    search = EnvironmentSearchSpace(
        top_k_values=tuple(spec["environment_search_space"]["top_k_values"]),
        text_threshold_values=tuple(
            spec["environment_search_space"]["text_threshold_values"]
        ),
        match_threshold_values=tuple(
            spec["environment_search_space"]["match_threshold_values"]
        ),
        environment_scope=spec["environment_search_space"][
            "environment_scope"
        ],
    )
    approval = AuthorApproval(**spec["author_approval"])

    blueprint = RealExperimentBlueprint(
        blueprint_name=spec["blueprint_name"],
        profile=spec["profile"],
        final_test_exclusion=exclusion,
        acquisition_assignments=acquisition,
        development_assignments=development,
        phase_budgets=budgets,
        environment_search_space=search,
        activation_policy_id=policy.policy_id,
        activation_policy_file_sha256=sha256_file(args.activation_policy),
        data_sufficiency_policy_file_sha256=sha256_file(
            args.data_sufficiency_policy
        ),
        collector_mode=spec["collector_mode"],
        collector_reads_growing_scene_memory=bool(
            spec["collector_reads_growing_scene_memory"]
        ),
        controller_profile=spec["controller_profile"],
        planner_model_id=spec["planner_model_id"],
        confidence_model_id=spec["confidence_model_id"],
        prompt_hashes=spec["prompt_hashes"],
        source_commit=spec["source_commit"],
        author_approval=approval,
        notes=spec.get("notes", ""),
    )

    if args.print_content_sha_for_approval:
        print(
            json.dumps(
                {
                    "content_sha256_before_approval": (
                        blueprint.content_sha256_before_approval()
                    ),
                    "instruction": (
                        "Insert this SHA into "
                        "author_approval.approved_blueprint_content_sha256, "
                        "record author approval, and rerun without the flag."
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    blueprint_id = save_blueprint(args.output_blueprint, blueprint)
    print(
        json.dumps(
            {
                "blueprint_id": blueprint_id,
                "output": str(Path(args.output_blueprint)),
                "profile": blueprint.profile,
                "final_task_count": len(exclusion.tasks),
                "acquisition_group_count": len(acquisition),
                "development_group_count": len(development),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
