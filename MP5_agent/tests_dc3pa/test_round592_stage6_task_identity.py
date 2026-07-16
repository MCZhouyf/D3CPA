from scripts_dc3pa.stage6_run_minecraft import (
    _apply_formal_acquisition_execution_budget,
    _expected_reasoning_only_provider_calls,
    _runtime_target_matches_catalog_task,
    _validate_formal_task_spec,
    build_parser,
)
import json

import pytest


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


def test_formal_task_spec_approves_explicit_runtime_name(tmp_path):
    specs = tmp_path / "formal_task_specs"
    tasks = tmp_path / "creative_task_jsons"
    specs.mkdir()
    tasks.mkdir()
    task_path = tasks / "craft_button.json"
    task = {"task": "wooden button", "quantity": 1}
    task_path.write_text(json.dumps([task]), encoding="utf-8")
    spec_path = specs / "craft_button.json"
    spec_path.write_text(
        json.dumps(
            {
                "task_name": "craft button",
                "target": {"candidate_item_name": "wooden button", "quantity": 1},
                "creative_task_file": "creative_task_jsons/craft_button.json",
            }
        ),
        encoding="utf-8",
    )

    _validate_formal_task_spec(
        spec_path=spec_path,
        catalog_task="craft button",
        runtime_task_path=task_path,
        runtime_task=task,
    )


def test_formal_task_spec_rejects_unapproved_runtime_name(tmp_path):
    specs = tmp_path / "formal_task_specs"
    tasks = tmp_path / "creative_task_jsons"
    specs.mkdir()
    tasks.mkdir()
    task_path = tasks / "craft_button.json"
    task_path.write_text("[]", encoding="utf-8")
    spec_path = specs / "craft_button.json"
    spec_path.write_text(
        json.dumps(
            {
                "task_name": "craft button",
                "target": {"candidate_item_name": "stone button", "quantity": 1},
                "creative_task_file": "creative_task_jsons/craft_button.json",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="target differs"):
        _validate_formal_task_spec(
            spec_path=spec_path,
            catalog_task="craft button",
            runtime_task_path=task_path,
            runtime_task={"task": "wooden button", "quantity": 1},
        )


def test_formal_acquisition_budget_caps_legacy_exploration(monkeypatch):
    budget = type(
        "Budget",
        (),
        {
            "phase": "experience_acquisition",
            "maximum_high_level_steps_per_episode": 60,
        },
    )()
    blueprint = type("Blueprint", (), {"phase_budgets": (budget,)})()
    monkeypatch.setenv("DC3PA_MAX_EXPLORE_STEPS", "10000")

    assert _apply_formal_acquisition_execution_budget(blueprint) is budget
    assert __import__("os").environ["DC3PA_MAX_EXPLORE_STEPS"] == "60"


def test_formal_acquisition_budget_requires_one_frozen_phase():
    blueprint = type("Blueprint", (), {"phase_budgets": ()})()
    with pytest.raises(ValueError, match="exactly one"):
        _apply_formal_acquisition_execution_budget(blueprint)


def test_single_attempt_provider_calls_include_final_failure_reflection():
    success = type("Result", (), {"success": True})()
    failure = type("Result", (), {"success": False})()
    assert _expected_reasoning_only_provider_calls(
        task_count=1, result=success
    ) == 1
    assert _expected_reasoning_only_provider_calls(
        task_count=1, result=failure
    ) == 2


def test_reactive_success_provider_calls_include_planning_and_reflection_events():
    event = lambda name: type("Event", (), {"event_type": name})()
    result = type(
        "Result",
        (),
        {
            "success": True,
            "events": (
                event("planning_started"),
                event("reflection_created"),
                event("planning_started"),
                event("controller_completed"),
            ),
        },
    )()

    assert _expected_reasoning_only_provider_calls(
        task_count=1, result=result
    ) == 3


def test_formal_dry_run_has_bounded_exploration_default():
    assert build_parser().parse_args([]).dry_run_max_explore_steps == 16
