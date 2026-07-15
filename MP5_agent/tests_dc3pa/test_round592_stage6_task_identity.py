from scripts_dc3pa.stage6_run_minecraft import (
    _expected_reasoning_only_provider_calls,
    _runtime_target_matches_catalog_task,
    build_parser,
)


def test_action_prefixed_catalog_task_matches_runtime_target():
    assert _runtime_target_matches_catalog_task(
        runtime_target="crafting table",
        catalog_task="craft crafting table",
    )
    assert _runtime_target_matches_catalog_task(
        runtime_target="coal ore",
        catalog_task="mine coal ore",
    )


def test_different_runtime_target_is_rejected():
    assert not _runtime_target_matches_catalog_task(
        runtime_target="stone pickaxe",
        catalog_task="craft stone shovel",
    )


def test_single_attempt_provider_calls_include_final_failure_reflection():
    success = type("Result", (), {"success": True})()
    failure = type("Result", (), {"success": False})()
    assert _expected_reasoning_only_provider_calls(
        task_count=1, result=success
    ) == 1
    assert _expected_reasoning_only_provider_calls(
        task_count=1, result=failure
    ) == 2


def test_formal_dry_run_has_bounded_exploration_default():
    assert build_parser().parse_args([]).dry_run_max_explore_steps == 16
