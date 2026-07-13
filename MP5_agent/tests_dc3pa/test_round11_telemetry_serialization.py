import numpy as np

from dc3pa.integration.execution_observer import make_execution_event
from dc3pa.integration.telemetry_serialization import serialize_execution_event


def test_serialization_keeps_semantic_payload_and_removes_rgb():
    event = make_execution_event(
        "action_finished",
        plan_id="p",
        step_id="s",
        step_index=0,
        action_index=1,
        status="failure",
        action={"name": "mine", "args": {"obj": "stone"}},
        result={"reason": "wrong tool"},
        inventory={"wooden pickaxe": 1},
        rgb=np.zeros((4, 4, 3), dtype=np.uint8),
    )
    payload = serialize_execution_event(event, image_path="images/s.npy")
    assert payload["status"] == "failure"
    assert payload["payload"]["action"]["name"] == "mine"
    assert payload["payload"]["result"]["reason"] == "wrong tool"
    assert "rgb" not in payload["payload"]
    assert payload["payload"]["image_path"] == "images/s.npy"
