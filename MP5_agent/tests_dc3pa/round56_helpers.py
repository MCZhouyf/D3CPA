from __future__ import annotations

import hashlib
from dataclasses import replace

from dc3pa.experiments.blueprint import (
    AcquisitionAssignment,
    AuthorApproval,
    EnvironmentSearchSpace,
    PhaseBudget,
    RealExperimentBlueprint,
)
from dc3pa.reliability.development_protocol import GroupAssignment
from dc3pa.reliability.final_test_exclusion import (
    FinalEvaluationTask,
    FinalTestExclusionManifest,
)


def final_manifest(task_count_per_difficulty=2, seed_count=2):
    tasks = []
    for difficulty in ("basic", "easy", "medium", "hard", "complex"):
        for index in range(task_count_per_difficulty):
            tasks.append(
                FinalEvaluationTask(
                    task=f"{difficulty}-task-{index}",
                    difficulty=difficulty,
                    goal_status=(
                        "experience_covered"
                        if index < task_count_per_difficulty // 2
                        else "final_heldout_terminal_goal"
                    ),
                    test_seeds=tuple(
                        f"test-{seed}" for seed in range(seed_count)
                    ),
                )
            )
    return FinalTestExclusionManifest(
        manifest_name="synthetic-final",
        tasks=tuple(tasks),
        created_from_commit="commit",
    ).with_id()


def make_blueprint(
    *,
    profile="synthetic_test",
    manifest=None,
    acquisition=None,
    development=None,
    environment_search=None,
):
    manifest = manifest or final_manifest()
    acquisition = acquisition or (
        AcquisitionAssignment(
            group_id="acq-1",
            task="basic-task-0",
            seed="acq-seed",
            task_kind="experience_covered_final_goal",
            sequence_index=0,
        ),
        AcquisitionAssignment(
            group_id="acq-2",
            task="auxiliary-craft-stick",
            seed="acq-seed-2",
            task_kind="auxiliary_technology_tree",
            sequence_index=1,
        ),
    )
    development = development or (
        GroupAssignment(
            group_id="train",
            task="basic-task-0",
            seed="dev-train",
            role="dev_train",
            difficulty="basic",
            goal_status="experience_covered",
        ),
        GroupAssignment(
            group_id="tune",
            task="dev-novel-a",
            seed="dev-tune",
            role="dev_tune",
            difficulty="medium",
            goal_status="development_novel_goal",
        ),
        GroupAssignment(
            group_id="holdout",
            task="dev-novel-b",
            seed="dev-holdout",
            role="dev_holdout",
            difficulty="hard",
            goal_status="development_novel_goal",
        ),
    )
    budgets = (
        PhaseBudget("dry_run", 6, 40, 20, 3, 600, 0.0),
        PhaseBudget("experience_acquisition", 10, 40, 20, 3, 600, 0.0),
        PhaseBudget("confidence_collection", 10, 40, 20, 3, 600, 0.0),
        PhaseBudget("development_holdout", 10, 40, 20, 3, 600, 0.0),
        PhaseBudget("final_evaluation", 10, 40, 20, 3, 600, 0.0),
    )
    search = environment_search or EnvironmentSearchSpace(
        top_k_values=(1, 3),
        text_threshold_values=(0.3, 0.5),
        match_threshold_values=(0.4, 0.6),
    )
    placeholder_approval = AuthorApproval(
        approval_record_id="approval",
        approved_at="2026-07-15T00:00:00+00:00",
        approved_blueprint_content_sha256="placeholder",
    )
    draft = RealExperimentBlueprint(
        blueprint_name="synthetic-blueprint",
        profile=profile,
        final_test_exclusion=manifest,
        acquisition_assignments=tuple(acquisition),
        development_assignments=tuple(development),
        phase_budgets=budgets,
        environment_search_space=search,
        activation_policy_id="policy",
        activation_policy_file_sha256="policy-file",
        data_sufficiency_policy_file_sha256="sufficiency-file",
        collector_mode="single_chain_reactive",
        collector_reads_growing_scene_memory=True,
        controller_profile="paper-matched",
        planner_model_id="planner",
        confidence_model_id="confidence",
        prompt_hashes={"planner": "planner-prompt", "confidence": "confidence-prompt"},
        source_commit="commit",
        author_approval=placeholder_approval,
    )
    content_sha = draft.content_sha256_before_approval()
    return replace(
        draft,
        author_approval=replace(
            placeholder_approval,
            approved_blueprint_content_sha256=content_sha,
        ),
    ).with_id()
