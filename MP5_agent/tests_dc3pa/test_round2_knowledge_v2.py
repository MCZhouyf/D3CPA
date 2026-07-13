from __future__ import annotations

import pytest

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.memory.dependency_store import DependencyEdge
from dc3pa.reliability.knowledge import KnowledgeReliabilityStrategy
from dc3pa.reliability.knowledge_v2 import (
    KnowledgeReliabilityStrategyV2,
    KnowledgeShadowStrategy,
)


class Dependencies:
    def __init__(self, edges=()):
        self.edges = list(edges)

    def prerequisites_for(self, target: str):
        return [edge for edge in self.edges if edge.target == target]


def state(inventory=None):
    return AgentState(task="test", inventory=dict(inventory or {}))


def plan_for(action: Action, *, times: int = 1):
    return Plan(
        task="test",
        steps=[PlanStep(step_id="s0", actions=[action], times=times)],
        plan_id="p0",
    )


def craft_pickaxe():
    return Action(
        "craft",
        {
            "obj": {"wooden pickaxe": 1},
            "materials": {"planks": 3, "stick": 2},
            "platform": "crafting table",
        },
    )


def test_unknown_is_unavailable_not_zero():
    strategy = KnowledgeReliabilityStrategyV2()
    result = strategy.score(
        plan_for(Action("find", {"obj": "tree"})),
        0,
        state(),
    )
    assert result.available is False
    assert result.probability is None
    assert result.hard_conflict is False
    assert result.evidence["knowledge_v2"]["hard_feasible"] is None


def test_all_explicit_prerequisites_satisfied():
    strategy = KnowledgeReliabilityStrategyV2()
    result = strategy.score(
        plan_for(craft_pickaxe()),
        0,
        state({"planks": 3, "stick": 2, "crafting table": 1}),
    )
    assert result.available is True
    assert result.probability == pytest.approx(1.0)
    assert result.hard_conflict is False
    assert result.evidence["knowledge_v2"]["hard_feasible"] is True


def test_equal_weight_coverage_can_be_four_fifths_with_soft_missing():
    deps = Dependencies(
        [
            DependencyEdge(
                prerequisite="torch",
                target="wooden pickaxe",
                relation_type="context",
                success_count=1,
            ),
            DependencyEdge(
                prerequisite="chest",
                target="wooden pickaxe",
                relation_type="context",
                success_count=1,
            ),
        ]
    )
    strategy = KnowledgeReliabilityStrategyV2(deps, graph_hard_min_support=2)
    result = strategy.score(
        plan_for(craft_pickaxe()),
        0,
        state(
            {
                "planks": 3,
                "stick": 2,
                "crafting table": 1,
                "torch": 1,
            }
        ),
    )
    assert result.probability == pytest.approx(0.8)
    assert result.hard_conflict is False
    evidence = result.evidence["knowledge_v2"]
    assert evidence["hard_feasible"] is True
    assert [item["item"] for item in evidence["missing_soft"]] == ["chest"]


def test_missing_action_schema_requirement_is_hard():
    strategy = KnowledgeReliabilityStrategyV2()
    result = strategy.score(
        plan_for(craft_pickaxe()),
        0,
        state({"planks": 2, "stick": 2, "crafting table": 1}),
    )
    assert result.hard_conflict is True
    assert result.evidence["knowledge_v2"]["hard_feasible"] is False
    assert result.evidence["knowledge_v2"]["missing_hard"][0]["item"] == "planks"


def test_graph_support_threshold_controls_hard_vs_soft():
    action = Action("mine", {"obj": "cobblestone", "tool": "wooden pickaxe"})
    base_inventory = {"wooden pickaxe": 1}

    low = KnowledgeReliabilityStrategyV2(
        Dependencies(
            [
                DependencyEdge(
                    prerequisite="torch",
                    target="cobblestone",
                    relation_type="context",
                    success_count=1,
                )
            ]
        ),
        graph_hard_min_support=2,
    ).score(plan_for(action), 0, state(base_inventory))
    assert low.hard_conflict is False
    assert low.evidence["knowledge_v2"]["missing_soft"]

    high = KnowledgeReliabilityStrategyV2(
        Dependencies(
            [
                DependencyEdge(
                    prerequisite="torch",
                    target="cobblestone",
                    relation_type="context",
                    success_count=2,
                )
            ]
        ),
        graph_hard_min_support=2,
    ).score(plan_for(action), 0, state(base_inventory))
    assert high.hard_conflict is True
    assert high.evidence["knowledge_v2"]["missing_hard"]


def test_same_schema_and_graph_requirement_is_not_double_counted():
    deps = Dependencies(
        [
            DependencyEdge(
                prerequisite="crafting table",
                target="wooden pickaxe",
                relation_type="platform",
                success_count=10,
            )
        ]
    )
    result = KnowledgeReliabilityStrategyV2(deps).score(
        plan_for(craft_pickaxe()),
        0,
        state({"planks": 3, "stick": 2, "crafting table": 1}),
    )
    evidence = result.evidence["knowledge_v2"]
    assert len(evidence["checks"]) == 3
    platform = [item for item in evidence["checks"] if item["item"] == "crafting table"]
    assert len(platform) == 1
    assert set(platform[0]["sources"]) == {"action_schema", "dependency_graph:10"}


def test_quantity_requirement_is_respected():
    result = KnowledgeReliabilityStrategyV2().score(
        plan_for(craft_pickaxe()),
        0,
        state({"planks": 2, "stick": 2, "crafting table": 1}),
    )
    planks = [
        item
        for item in result.evidence["knowledge_v2"]["checks"]
        if item["item"] == "planks"
    ][0]
    assert planks["required"] == 3
    assert planks["available"] == 2
    assert planks["satisfied"] is False


def test_plan_prefix_projection_satisfies_later_step():
    make_sticks = Action(
        "craft",
        {
            "obj": {"stick": 4},
            "materials": {"planks": 2},
            "platform": "crafting table",
        },
    )
    plan = Plan(
        task="test",
        plan_id="p-projected",
        steps=[
            PlanStep(step_id="sticks", actions=[make_sticks]),
            PlanStep(step_id="pickaxe", actions=[craft_pickaxe()]),
        ],
    )
    result = KnowledgeReliabilityStrategyV2().score(
        plan,
        1,
        state({"planks": 5, "crafting table": 1}),
    )
    assert result.probability == pytest.approx(1.0)
    assert result.hard_conflict is False
    projected = result.evidence["knowledge_v2"]["projected_inventory"]
    assert projected["stick"] == pytest.approx(4.0)
    assert projected["planks"] == pytest.approx(3.0)


def test_shadow_mode_preserves_legacy_decision_exactly():
    plan = plan_for(craft_pickaxe())
    agent_state = state({"planks": 3, "stick": 2, "crafting table": 1})
    legacy = KnowledgeReliabilityStrategy()
    expected = legacy.score(plan, 0, agent_state)
    shadow = KnowledgeShadowStrategy(
        legacy,
        KnowledgeReliabilityStrategyV2(),
    ).score(plan, 0, agent_state)
    assert shadow.probability == expected.probability
    assert shadow.available == expected.available
    assert shadow.hard_conflict == expected.hard_conflict
    assert shadow.reason == expected.reason
    assert "shadow_v2" in shadow.evidence
