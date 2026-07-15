from __future__ import annotations

import pytest

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


def test_paper_profile_requires_50_tasks_five_by_ten_and_30_seeds():
    tasks = []
    for difficulty in ("basic", "easy", "medium", "hard", "complex"):
        for index in range(10):
            tasks.append(
                FinalEvaluationTask(
                    task=f"{difficulty}-{index}",
                    difficulty=difficulty,
                    goal_status=(
                        "experience_covered"
                        if index < 5
                        else "final_heldout_terminal_goal"
                    ),
                    test_seeds=tuple(str(seed) for seed in range(30)),
                )
            )
    manifest = FinalTestExclusionManifest(
        manifest_name="paper",
        tasks=tuple(tasks),
        created_from_commit="commit",
    ).with_id()

    approval = AuthorApproval("approval", "now", "placeholder")
    draft = RealExperimentBlueprint(
        blueprint_name="paper",
        profile="paper_minecraft_50",
        final_test_exclusion=manifest,
        acquisition_assignments=(
            AcquisitionAssignment(
                "acq", "basic-0", "dev-acq",
                "experience_covered_final_goal", sequence_index=0
            ),
        ),
        development_assignments=(
            GroupAssignment("train", "basic-0", "dev-1", "dev_train",
                            "basic", "experience_covered"),
            GroupAssignment("tune", "aux-a", "dev-2", "dev_tune",
                            "medium", "development_novel_goal"),
            GroupAssignment("holdout", "aux-b", "dev-3", "dev_holdout",
                            "hard", "development_novel_goal"),
        ),
        phase_budgets=(
            PhaseBudget("dry_run", 1, 1, 1, 0, 10, 0),
            PhaseBudget("experience_acquisition", 1, 1, 1, 0, 10, 0),
            PhaseBudget("confidence_collection", 1, 1, 1, 0, 10, 0),
            PhaseBudget("development_holdout", 1, 1, 1, 0, 10, 0),
            PhaseBudget("final_evaluation", 1, 1, 1, 0, 10, 0),
        ),
        environment_search_space=EnvironmentSearchSpace(
            (1, 3), (0.3, 0.5), (0.4, 0.6)
        ),
        activation_policy_id="policy",
        activation_policy_file_sha256="p",
        data_sufficiency_policy_file_sha256="s",
        collector_mode="single_chain_reactive",
        collector_reads_growing_scene_memory=True,
        controller_profile="paper",
        planner_model_id="planner",
        confidence_model_id="confidence",
        prompt_hashes={"planner": "hash"},
        source_commit="commit",
        author_approval=approval,
    )
    content = draft.content_sha256_before_approval()
    object.__setattr__(
        draft.author_approval,
        "approved_blueprint_content_sha256",
        content,
    )
    assert draft.with_id().blueprint_id


def test_wrong_paper_task_count_is_rejected():
    from tests_dc3pa.round56_helpers import make_blueprint
    with pytest.raises(ValueError):
        make_blueprint(profile="paper_minecraft_50")


def test_final_task_seeds_must_be_unique():
    with pytest.raises(ValueError, match="Duplicate test seed"):
        FinalEvaluationTask(
            task="duplicated-seeds",
            difficulty="basic",
            goal_status="experience_covered",
            test_seeds=("same", "same"),
        )
