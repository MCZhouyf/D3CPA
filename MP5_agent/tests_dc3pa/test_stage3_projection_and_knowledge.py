from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.memory import DependencyEdge
from dc3pa.reliability import KnowledgeReliabilityStrategy, project_inventory


class StubDependencies:
    def __init__(self, edges):
        self.edges = edges

    def prerequisites_for(self, target):
        return [edge for edge in self.edges if edge.target == target]


def craft_pickaxe_step():
    return PlanStep(
        actions=[
            Action(
                "craft",
                {
                    "obj": {"wooden_pickaxe": 1},
                    "materials": {"planks": 3, "stick": 2},
                    "platform": "crafting_table",
                },
            )
        ]
    )


def mine_cobble_step():
    return PlanStep(
        actions=[Action("mine", {"obj": "cobblestone", "tool": "wooden_pickaxe"})]
    )


def test_inventory_projection_allows_prerequisite_produced_by_plan_prefix():
    plan = Plan(task="cobblestone", steps=[craft_pickaxe_step(), mine_cobble_step()])
    state = AgentState(
        task=plan.task,
        inventory={"planks": 3, "stick": 2, "crafting_table": 1},
    )
    projection = project_inventory(plan, state)
    assert projection.before(1)["wooden pickaxe"] == 1.0
    strategy = KnowledgeReliabilityStrategy(
        StubDependencies(
            [DependencyEdge("wooden pickaxe", "cobblestone", "tool")]
        )
    )
    score = strategy.score(plan, 1, state)
    assert score.probability == 1.0
    assert not score.hard_conflict


def test_missing_tool_is_binary_hard_conflict_with_evidence():
    plan = Plan(task="cobblestone", steps=[mine_cobble_step()])
    strategy = KnowledgeReliabilityStrategy(
        StubDependencies(
            [DependencyEdge("wooden pickaxe", "cobblestone", "tool")]
        )
    )
    score = strategy.score(plan, 0, AgentState(task=plan.task))
    assert score.probability == 0.0
    assert score.hard_conflict
    assert score.evidence["missing"][0]["item"] == "wooden pickaxe"


def test_explicit_crafting_materials_are_checked_even_without_memory():
    plan = Plan(task="pickaxe", steps=[craft_pickaxe_step()])
    score = KnowledgeReliabilityStrategy().score(
        plan,
        0,
        AgentState(task=plan.task, inventory={"planks": 3, "stick": 1}),
    )
    assert score.probability == 0.0
    missing_names = {item["item"] for item in score.evidence["missing"]}
    assert missing_names == {"stick", "crafting table"}


def test_no_known_prerequisite_returns_unavailable_not_false_confidence():
    plan = Plan(
        task="look",
        steps=[PlanStep(actions=[Action("find", {"obj": "tree"})])],
    )
    score = KnowledgeReliabilityStrategy().score(
        plan, 0, AgentState(task=plan.task)
    )
    assert score.probability is None
    assert not score.available


def test_inventory_projection_rejects_nonfinite_quantities():
    plan = Plan(task="look", steps=[PlanStep(actions=[Action("find", {"obj": "tree"})])])
    try:
        project_inventory(plan, AgentState(task=plan.task, inventory={"log": float("nan")}))
    except ValueError as exc:
        assert "finite" in str(exc)
    else:
        raise AssertionError("non-finite inventory was silently accepted")
