import pytest

from dc3pa.contracts import AgentState, Plan
from dc3pa.errors import ContractValidationError


def sample_workflow():
    return {
        "workflow": [
            {
                "times": "1",
                "actions": [
                    {"name": "find", "args": {"obj": "log"}},
                    {"name": "move_to", "args": {"obj": "log"}},
                    {"name": "mine", "args": {"obj": "log", "tool": None}},
                ],
            }
        ]
    }


def test_legacy_roundtrip_preserves_controller_shape():
    plan = Plan.from_dict(sample_workflow(), task="log")
    legacy = plan.to_legacy_workflow()
    assert legacy["workflow"][0]["times"] == "1"
    assert legacy["workflow"][0]["actions"][2]["args"]["tool"] is None


def test_invalid_action_is_rejected():
    payload = sample_workflow()
    payload["workflow"][0]["actions"][0]["name"] = "teleport"
    with pytest.raises(ContractValidationError):
        Plan.from_dict(payload, task="log")


def test_state_inventory_normalization():
    state = AgentState(task="x", inventory={"Wooden_Pickaxe": 1, "wooden pickaxe": 2})
    assert state.normalized_inventory() == {"wooden pickaxe": 3.0}
