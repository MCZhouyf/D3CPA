from __future__ import annotations

import pytest

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.evaluation import EvaluationReport
from dc3pa.planner import HighFrequencyDualChainPlanner
from dc3pa.planner.constraint_repair_policy import (
    BLOCK_ON_UNRESOLVED,
    EVALUATION_ONLY,
    EVALUATION_THEN_DETERMINISTIC_FALLBACK,
    LEGACY,
    should_attempt_deterministic_repair,
    should_block_unresolved_hard_conflict,
    validate_constraint_repair_policy,
)
from dc3pa.reliability import DualChainConfig
from tests_dc3pa.helpers_stage3_5 import (
    FunctionEvaluationChain,
    FunctionReliabilityModel,
    StaticReasoningChain,
)


def test_invalid_policy_is_rejected():
    with pytest.raises(ValueError):
        validate_constraint_repair_policy("invented")


def test_legacy_policy_exactly_matches_pre_round2_behavior():
    assert should_attempt_deterministic_repair(
        LEGACY, phase="request_replan", hard_conflict=True
    )
    assert not should_attempt_deterministic_repair(
        LEGACY, phase="request_replan", hard_conflict=False
    )
    assert should_attempt_deterministic_repair(
        LEGACY, phase="post_patch", hard_conflict=True
    )
    assert should_attempt_deterministic_repair(
        LEGACY, phase="post_patch", hard_conflict=False
    )


def test_recommended_policy_only_repairs_known_hard_conflicts():
    for phase in ("request_replan", "post_patch"):
        assert should_attempt_deterministic_repair(
            EVALUATION_THEN_DETERMINISTIC_FALLBACK,
            phase=phase,
            hard_conflict=True,
        )
        assert not should_attempt_deterministic_repair(
            EVALUATION_THEN_DETERMINISTIC_FALLBACK,
            phase=phase,
            hard_conflict=False,
        )


def test_evaluation_only_and_block_policy_never_use_deterministic_repair():
    for policy in (EVALUATION_ONLY, BLOCK_ON_UNRESOLVED):
        for phase in ("request_replan", "post_patch"):
            assert not should_attempt_deterministic_repair(
                policy, phase=phase, hard_conflict=True
            )
    assert should_block_unresolved_hard_conflict(BLOCK_ON_UNRESOLVED)
    assert not should_block_unresolved_hard_conflict(EVALUATION_ONLY)


def test_block_policy_leaves_hard_conflict_unresolved_without_local_repair():
    craft_pickaxe = PlanStep(
        step_id="pickaxe",
        actions=[
            Action(
                "craft",
                {
                    "obj": {"wooden pickaxe": 1},
                    "materials": {"planks": 3, "stick": 2},
                    "platform": "crafting table",
                },
            )
        ],
    )
    plan = Plan(task="cobblestone", plan_id="needs-materials", steps=[craft_pickaxe])
    planner = HighFrequencyDualChainPlanner(
        StaticReasoningChain(plan),
        FunctionReliabilityModel(lambda plan, index: (0.95, True)),
        FunctionEvaluationChain(
            lambda request: EvaluationReport.unresolved(
                request.plan,
                "hard conflict remains",
            )
        ),
        config=DualChainConfig(
            max_revision_rounds=1,
            constraint_repair_policy=BLOCK_ON_UNRESOLVED,
        ),
    )

    outcome = planner.plan_with_outcome(
        "cobblestone",
        AgentState(task="cobblestone", inventory={}),
    )

    assert outcome.final_plan is plan
    assert outcome.revision_count == 0
    assert outcome.unresolved
    assert outcome.unresolved[0]["hard_conflict"] is True
