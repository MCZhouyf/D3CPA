from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.evaluation.material_repair import repair_material_deficits
from dc3pa.reliability import KnowledgeReliabilityStrategy, project_inventory


def _craft_pickaxe_step() -> PlanStep:
    return PlanStep(
        actions=[
            Action(
                "craft",
                {
                    "obj": {"wooden pickaxe": 1},
                    "materials": {"planks": 3, "stick": 2},
                    "platform": "crafting table",
                },
            )
        ]
    )


def test_material_repair_closes_wooden_pickaxe_dependencies_from_empty_inventory():
    plan = Plan(task="cobblestone", steps=[_craft_pickaxe_step()])
    state = AgentState(task=plan.task, inventory={})

    result = repair_material_deficits(plan, state)

    assert result.inserted_step_count > 0
    assert result.inserted_targets.count("log") >= 3
    assert "crafting table" in result.inserted_targets
    assert "stick" in result.inserted_targets
    projection = project_inventory(result.plan, state)
    before_pickaxe = projection.before(len(result.plan.steps) - 1)
    assert before_pickaxe["planks"] >= 3.0
    assert before_pickaxe["stick"] >= 2.0
    assert before_pickaxe["crafting table"] >= 1.0
    score = KnowledgeReliabilityStrategy().score(
        result.plan,
        len(result.plan.steps) - 1,
        state,
    )
    assert score.probability == 1.0
    assert not score.hard_conflict


def test_material_repair_batches_future_plank_demand_before_crafting_table_use():
    plan = Plan(
        task="cobblestone",
        steps=[
            PlanStep(
                actions=[
                    Action(
                        "craft",
                        {
                            "obj": {"crafting table": 1},
                            "materials": {"planks": 4},
                            "platform": None,
                        },
                    )
                ]
            ),
            PlanStep(
                actions=[
                    Action(
                        "craft",
                        {
                            "obj": {"stick": 4},
                            "materials": {"planks": 2},
                            "platform": "crafting table",
                        },
                    )
                ]
            ),
            _craft_pickaxe_step(),
        ],
    )

    result = repair_material_deficits(plan, AgentState(task=plan.task, inventory={}))

    stick_index = next(
        index
        for index, step in enumerate(result.plan.steps)
        if step.actions[0].name == "craft"
        and "stick" in step.actions[0].args["obj"]
        and not step.metadata.get("dc3pa_auto_material_repair")
    )
    log_repairs_after_stick = [
        step
        for step in result.plan.steps[stick_index + 1 :]
        if step.metadata.get("target") == "log"
    ]
    assert not log_repairs_after_stick
    before_stick = project_inventory(result.plan, AgentState(task=plan.task)).before(
        stick_index
    )
    assert before_stick["planks"] >= 5.0
    before_pickaxe = project_inventory(result.plan, AgentState(task=plan.task)).before(
        len(result.plan.steps) - 1
    )
    assert before_pickaxe["planks"] >= 3.0


def test_material_repair_removes_invalid_direct_gather_for_craftable_items():
    invalid_planks = PlanStep(
        actions=[
            Action("find", {"obj": "planks"}),
            Action("move_to", {"obj": "planks"}),
            Action("mine", {"obj": "planks", "tool": None}),
        ],
        times=4,
    )
    craft_table = PlanStep(
        actions=[
            Action(
                "craft",
                {
                    "obj": {"crafting table": 1},
                    "materials": {"planks": 4},
                    "platform": None,
                },
            )
        ]
    )
    plan = Plan(task="cobblestone", steps=[invalid_planks, craft_table])

    result = repair_material_deficits(plan, AgentState(task=plan.task, inventory={}))

    assert all(
        not (
            step.actions[0].name == "find"
            and step.actions[0].args.get("obj") == "planks"
        )
        for step in result.plan.steps
    )
    assert "removed invalid direct gather:planks" in result.inserted_targets
    before_table = project_inventory(result.plan, AgentState(task=plan.task)).before(
        len(result.plan.steps) - 1
    )
    assert before_table["planks"] >= 4.0


def test_material_repair_is_idempotent_once_known_deficits_are_closed():
    state = AgentState(task="cobblestone", inventory={})
    first = repair_material_deficits(
        Plan(task="cobblestone", steps=[_craft_pickaxe_step()]),
        state,
    )
    second = repair_material_deficits(first.plan, state)

    assert second.plan is first.plan
    assert second.inserted_step_count == 0
