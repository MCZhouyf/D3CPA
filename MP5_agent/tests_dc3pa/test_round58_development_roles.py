from __future__ import annotations

from collections import Counter, defaultdict

from tests_dc3pa.round58_helpers import design


def test_development_is_task_level_three_one_one_per_difficulty():
    item = design()
    task_roles = {}
    difficulty_tasks = defaultdict(lambda: defaultdict(set))
    for row in item.development_assignments:
        previous = task_roles.setdefault(row.task, row.role)
        assert previous == row.role
        difficulty_tasks[row.difficulty][row.role].add(row.task)

    for difficulty, roles in difficulty_tasks.items():
        assert len(roles["dev_train"]) == 3
        assert len(roles["dev_tune"]) == 1
        assert len(roles["dev_holdout"]) == 1

    counts = Counter(row.role for row in item.development_assignments)
    assert counts == {"dev_train": 45, "dev_tune": 15, "dev_holdout": 15}
    assert len(item.acquisition_assignments) == 100
    assert len(item.dry_run_group_ids) == 6

    assignments = {
        row.group_id: row for row in item.development_assignments
    }
    dry_run = [assignments[group_id] for group_id in item.dry_run_group_ids]
    assert {row.role for row in dry_run} == {"dev_train"}
    assert Counter(row.difficulty for row in dry_run) == {
        "basic": 2,
        "medium": 2,
        "complex": 2,
    }
