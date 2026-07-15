from dc3pa.experiments.final_taskset_release import (
    REQUIRED_CRITICAL_TASKS,
    TaskSemanticReceipt,
    audit_task_semantics,
)


DIFFICULTY = {
    "craft fence": "easy",
    "craft wooden door": "easy",
    "craft shears": "hard",
    "craft diamond axe": "complex",
    "mine coal ore": "medium",
    "mine iron ore": "medium",
}


def receipt(task):
    return TaskSemanticReceipt(
        receipt_id=f"receipt:{task}",
        task_name=task,
        difficulty=DIFFICULTY[task],
        source_commit="commit",
        task_asset_validation_report_id="task-report",
        semantic_validation_mode="controlled_success_fixture",
        requested_seed=f"seed:{task}",
        effective_seed=f"seed:{task}",
        process_exit_code=0,
        environment_started=True,
        controller_started=True,
        actual_runtime_task_loaded=True,
        agent_target_name=task,
        environment_target_name=task,
        spawned_block_name=task,
        controller_success_target_name=task,
        evaluator_success_target_name=task,
        inventory_name_field="inventory.name",
        inventory_quantity_field="inventory.quantity",
        evaluator_delegates_to_controller=True,
        success_condition_observed=True,
        controller_success_observed=True,
        evaluator_success_observed=True,
        controller_evaluator_agree=True,
        task_completed=True,
        provider_call_count=0,
        formal_memory_used=False,
        excluded_from_formal_fitting=True,
        technical_failure_count=0,
        trace_sha256="trace",
        observation_sha256="observation",
    )


def test_all_six_critical_task_semantics_are_required():
    report = audit_task_semantics(
        [receipt(task) for task in sorted(REQUIRED_CRITICAL_TASKS)],
        source_commit="commit",
        task_asset_validation_report_id="task-report",
    )
    assert report.eligible
    assert report.receipt_count == 6


def test_missing_critical_task_fails():
    tasks = sorted(REQUIRED_CRITICAL_TASKS)[:-1]
    report = audit_task_semantics(
        [receipt(task) for task in tasks],
        source_commit="commit",
        task_asset_validation_report_id="task-report",
    )
    assert not report.eligible
