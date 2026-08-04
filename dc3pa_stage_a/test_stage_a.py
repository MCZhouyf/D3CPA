"""Tests for the Stage A tooling. No MineDojo, no LLM, no GPU required."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dc3pa_stage_a.analyze_stage_a import (
    build_report,
    dual_population_success,
    mode_symmetry,
    order_invariance,
    read_jsonl,
    render_markdown,
    substitute_scope,
)
from dc3pa_stage_a.inventory_write_logger import InventoryWriteLogger
from dc3pa_stage_a.paper_config import OPTION_B_ENV, PaperRunConfig, load

FIXTURES = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------------ logger


class _FakeItem:
    def __init__(self, slot, name, quantity):
        self.slot = slot
        self.name = name
        self.variant = None
        self.quantity = quantity


class _FakeEnv:
    def __init__(self):
        self.calls = []

    def set_inventory(self, items):
        self.calls.append(list(items))
        return "ok"


def test_logger_passes_through_and_records(tmp_path):
    env = _FakeEnv()
    path = tmp_path / "writes.jsonl"
    logger = InventoryWriteLogger(path, context={"task": "diamond", "seed": 11})
    logger.install(env)

    assert env.set_inventory([_FakeItem(0, "iron_ore", 3)]) == "ok"
    assert env.set_inventory([_FakeItem(0, "iron_ore", 3), _FakeItem(1, "coal", 3)]) == "ok"
    logger.uninstall()

    # behaviour unchanged: the underlying method saw both calls verbatim
    assert len(env.calls) == 2
    # and the original bound method is restored
    assert not hasattr(env.set_inventory, "__wrapped__")

    records = read_jsonl(path)
    assert len(records) == 2
    assert records[0]["granted"] == {"iron_ore": 3}
    # second call grants only the increment, not the whole inventory
    assert records[1]["granted"] == {"coal": 3}
    assert records[1]["resulting_inventory"] == {"iron_ore": 3, "coal": 3}
    assert records[0]["task"] == "diamond"
    assert records[0]["caller_chain"][0]["function"] == "test_logger_passes_through_and_records"


def test_logger_context_manager_restores_on_error(tmp_path):
    env = _FakeEnv()
    original = env.set_inventory
    with InventoryWriteLogger(tmp_path / "w.jsonl") as logger:
        logger.install(env)
        assert env.set_inventory is not original
    assert env.set_inventory == original


# ------------------------------------------------------------ paper config


def _valid_config(**overrides) -> PaperRunConfig:
    payload = dict(
        runtime_mode="dc3pa",
        memory_mode="evaluate_readonly",
        record_legacy_workflow_memory=False,
        record_multimodal_memory=False,
        max_execution_attempts=30,
        env_flags=dict(OPTION_B_ENV),
        acquire_seeds=[1, 2, 3],
        evaluate_seeds=[10, 11],
    )
    payload.update(overrides)
    return PaperRunConfig(**payload)


def test_option_b_config_is_valid_and_hashes_stably(tmp_path):
    config = _valid_config()
    config.validate()
    first = config.config_hash()
    assert first == _valid_config().config_hash()
    written = config.write(tmp_path / "cfg.json")
    assert written == first
    assert load(tmp_path / "cfg.json").config_hash() == first


def test_option_b_rejects_planner_hacks_left_on():
    bad = _valid_config(
        env_flags={
            "DC3PA_LEGACY_TASK_HACKS": "1",
            "DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK": "1",
        }
    )
    with pytest.raises(ValueError, match="DC3PA_LEGACY_TASK_HACKS=0"):
        bad.validate()


def test_option_b_rejects_disabled_controller_substitute():
    bad = _valid_config(
        env_flags={
            "DC3PA_LEGACY_TASK_HACKS": "0",
            "DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK": "0",
        }
    )
    with pytest.raises(ValueError, match="BOUNDED_RESOURCE_FALLBACK=1"):
        bad.validate()


def test_evaluate_readonly_forbids_long_term_writes():
    with pytest.raises(ValueError, match="evaluate_readonly forbids"):
        _valid_config(record_legacy_workflow_memory=True).validate()


def test_seed_overlap_is_rejected():
    with pytest.raises(ValueError, match="overlap"):
        _valid_config(acquire_seeds=[1, 2], evaluate_seeds=[2, 3]).validate()


def test_assert_process_matches_detects_drift():
    config = _valid_config()
    config.assert_process_matches(dict(OPTION_B_ENV))
    with pytest.raises(RuntimeError, match="does not match"):
        config.assert_process_matches(
            {
                "DC3PA_LEGACY_TASK_HACKS": "1",
                "DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK": "1",
            }
        )


# ---------------------------------------------------------------- analysis


@pytest.fixture(scope="module")
def loaded():
    return (
        read_jsonl(FIXTURES / "inventory_writes.jsonl"),
        read_jsonl(FIXTURES / "episodes.jsonl"),
    )


def test_scope_identifies_only_substitute_tasks(loaded):
    writes, episodes = loaded
    scope = substitute_scope(writes, episodes)
    assert set(scope["affected_tasks"]) == {"diamond", "redstone"}
    assert "log" in scope["unaffected_tasks"]
    assert scope["per_tier"]["complex"]["affected_tasks"] == 2
    assert scope["per_tier"]["basic"]["affected_tasks"] == 0
    assert scope["granted_by_task"]["diamond"]["iron ore"] > 0


def test_symmetry_flags_balanced_usage(loaded):
    writes, episodes = loaded
    symmetry = mode_symmetry(writes, episodes)
    assert set(symmetry["per_mode"]) == {"dc3pa", "reasoning_only", "mp5_legacy"}
    assert symmetry["symmetric_within_10pct"] is True


def test_symmetry_detects_asymmetric_usage(loaded):
    """If one mode invokes the substitute more, the comparison is confounded."""
    writes, episodes = loaded
    skewed = list(writes) + [
        {
            "task": "diamond",
            "seed": 99,
            "runtime_mode": "dc3pa",
            "granted": {"iron ore": 3},
        }
        for _ in range(40)
    ]
    symmetry = mode_symmetry(skewed, episodes)
    assert symmetry["symmetric_within_10pct"] is False


def test_order_invariance_separates_memory_modes(loaded):
    _, episodes = loaded
    order = order_invariance(episodes)
    assert order["evaluate_readonly"]["agreement_rate"] == 1.0
    # acquire lets traversal order change what each seed can read
    assert order["acquire"]["agreement_rate"] < 1.0
    assert order["acquire"]["mismatches"]


def test_dual_population_reports_both_denominators(loaded):
    writes, episodes = loaded
    scope = substitute_scope(writes, episodes)
    dual = dual_population_success(episodes, scope["affected_tasks"])
    assert set(dual["all_tasks"]) == {"dc3pa", "reasoning_only", "mp5_legacy"}
    assert dual["substitute_free_task_count"] == 5
    for mode in dual["all_tasks"]:
        assert dual["all_tasks"][mode]["episodes"] > dual["substitute_free_tasks"][mode]["episodes"]


def test_report_and_markdown_render(loaded, tmp_path):
    writes, episodes = loaded
    report = build_report(writes, episodes)
    assert report["counts"]["episodes"] == len(episodes)
    markdown = render_markdown(report)
    for heading in ("Low-level substitute scope", "Per-mode symmetry",
                    "Order invariance", "Dual population"):
        assert heading in markdown
    (tmp_path / "out.md").write_text(markdown, encoding="utf-8")
    assert (tmp_path / "out.md").read_text(encoding="utf-8").startswith("# Stage A analysis")


# ------------------------------------------- write classification (corrected)


def test_empty_grant_is_not_a_substitute_write():
    """Episode setup calls set_inventory([]) and must never be counted."""
    from dc3pa_stage_a.analyze_stage_a import is_substitute_write

    assert is_substitute_write({"granted": {}}) is False
    assert is_substitute_write({"granted": {"iron ore": 0}}) is False
    assert is_substitute_write({"granted": {"iron ore": 3}}) is True


def test_bootstrap_writes_are_counted_regardless_of_function_name():
    """Inclusion must not depend on a function-name allowlist.

    ``ensure_wooden_bootstrap`` / ``_fallback_craft_bootstrap_item`` also write
    inventory, and their gating cannot be settled statically. An allowlist keyed
    on the deep-mining fallbacks would silently under-count them.
    """
    from dc3pa_stage_a.analyze_stage_a import attribute_write, mode_symmetry, substitute_scope

    episodes = [
        {"task": "craft boat", "tier": "easy", "seed": 1, "runtime_mode": "dc3pa"},
        {"task": "obtain diamond", "tier": "complex", "seed": 1, "runtime_mode": "dc3pa"},
    ]
    writes = [
        {  # episode-start reset: excluded
            "task": "craft boat", "seed": 1, "runtime_mode": "dc3pa",
            "granted": {},
            "caller_chain": [{"file": "run_agent.py", "function": "single_task_evaluate"}],
        },
        {  # bootstrap write on a task the static gate would call unaffected
            "task": "craft boat", "seed": 1, "runtime_mode": "dc3pa",
            "granted": {"wooden pickaxe": 1},
            "caller_chain": [{"file": "controller.py", "function": "_fallback_craft_wooden_pickaxe"}],
        },
        {
            "task": "obtain diamond", "seed": 1, "runtime_mode": "dc3pa",
            "granted": {"iron ore": 3},
            "caller_chain": [{"file": "controller.py", "function": "_fallback_mine_diamond_resource"}],
        },
    ]

    scope = substitute_scope(writes, episodes)
    assert scope["raw_write_records"] == 3
    assert scope["substitute_write_records"] == 2
    # the boat task IS affected, even though task-name gating would not predict it
    assert set(scope["affected_tasks"]) == {"craft boat", "obtain diamond"}
    assert scope["calls_by_function"] == {
        "_fallback_craft_wooden_pickaxe": 1,
        "_fallback_mine_diamond_resource": 1,
    }

    symmetry = mode_symmetry(writes, episodes)
    assert symmetry["per_mode"]["dc3pa"]["substitute_calls"] == 2

    assert attribute_write({"caller_chain": []}) == "unattributed"
