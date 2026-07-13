from dataclasses import dataclass, field

from dc3pa.contracts import Action
from dc3pa.integration.local_subgoal import resolve_local_subgoal


@dataclass
class _Step:
    actions: list
    step_id: str = "s1"
    expected_outputs: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


def test_explicit_metadata_has_priority():
    step = _Step(
        actions=[Action("mine", {"obj": "cobblestone", "tool": "wooden_pickaxe"})],
        metadata={"local_subgoal": "obtain stone safely"},
    )
    assert resolve_local_subgoal(step) == "obtain stone safely"


def test_expected_output_precedes_action_fallback():
    step = _Step(
        actions=[Action("find", {"obj": "tree"})],
        expected_outputs={"log": 1},
    )
    assert resolve_local_subgoal(step) == "obtain log"


def test_action_fallback_is_semantic_not_positional():
    step = _Step(
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
    assert resolve_local_subgoal(step) == "craft wooden pickaxe"
