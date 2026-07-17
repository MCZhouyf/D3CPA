from scripts_dc3pa.audit_paper_memory_v5_coverage import (
    covered_tasks,
    task_entries,
)

from dc3pa.experiments.memory_coverage_audit import build_coverage_audit


def _tasks():
    return [
        {
            "task": f"covered-{index}",
            "difficulty": "easy",
            "goal_status": "experience_covered",
        }
        for index in range(25)
    ]


def test_final_exclusion_input_keeps_only_experience_covered_tasks():
    payload = {
        "tasks": _tasks()
        + [
            {
                "task": "held-out",
                "difficulty": "hard",
                "goal_status": "final_heldout_terminal_goal",
            }
        ]
    }

    assert len(covered_tasks(payload)) == 25
    assert all(
        item["goal_status"] == "experience_covered"
        for item in covered_tasks(payload)
    )


def test_executed_blueprint_supplies_the_frozen_exclusion_split():
    tasks = _tasks()
    blueprint = {"final_test_exclusion": {"tasks": tasks}}

    assert task_entries(blueprint) == tasks
    assert covered_tasks(blueprint) == tasks


def test_coverage_audit_reads_dependency_success_count():
    tasks = _tasks()
    report = build_coverage_audit(
        paper_memory_release={
            "eligible": True,
            "release_id": "paper",
            "scene_exemplar_count": 1,
            "dependency_edge_count": 1,
            "structured_action_key_coverage": 1.0,
        },
        active_taskset_release={"eligible": True, "release_id": "taskset"},
        acquisition_audit={
            "successful_episode_count": 40,
            "success_by_task": {item["task"]: 1 for item in tasks},
        },
        acquisition_records=(),
        snapshot_rows={
            "scene_exemplars": ({"task_name": tasks[0]["task"]},),
            "dependency_edges": ({"success_count": 3},),
        },
        covered_tasks=tasks,
        final_heldout_tasks=(),
        final_task_seed_pairs=(),
    )

    assert report.dependency_support_histogram == {"3": 1}
