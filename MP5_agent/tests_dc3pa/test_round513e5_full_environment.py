import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from dc3pa.contracts import Action
from dc3pa.experiments.round513e5 import (
    action_outcome_v4_1_3,
    find_evidence_from_telemetry_v4_1_3,
)
from dc3pa.experiments.round513_instrumentation import (
    ControllerReceiptV4_1,
    StateEvidenceV4_1,
)


@pytest.mark.minedojo
def test_round513e5_real_controller_find_telemetry_is_labelable_without_env_step():
    agent_dir = Path(__file__).resolve().parents[1] / "agent"
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))
    import structured_actions
    from controller import Controller

    assert callable(getattr(Controller, "check_and_execute_workflow", None))
    memory = SimpleNamespace()
    structured_actions.begin_find_observation_trace(memory, "log", "wood", 120)
    blocks = np.full((11, 11, 11), "air", dtype=object)
    blocks[6, 5, 5] = "wood"
    events = {
        "voxels": {"block_name": blocks},
        "location_stats": {"pos": np.asarray([0.0, 64.0, 0.0])},
    }
    target = structured_actions.select_target_block(events, "wood")
    structured_actions._record_find_observation(
        memory,
        events,
        "wood",
        target,
        "within_frozen_voxel_observation_volume",
    )
    structured_actions.finish_find_observation_trace(
        memory,
        "target_visible_in_voxel_volume",
        budget_exhausted=False,
    )
    telemetry = [
        {
            "event_type": "action_finished",
            "payload": {
                "result": {
                    "post_state_evidence": {
                        "find_observation": structured_actions.consume_find_observation_trace(memory)
                    }
                }
            },
        }
    ]
    action = Action("find", {"obj": "log"})
    evidence = find_evidence_from_telemetry_v4_1_3(action, telemetry)
    assert evidence is not None
    outcome = action_outcome_v4_1_3(
        action=action,
        pre=StateEvidenceV4_1(inventory={}),
        post=StateEvidenceV4_1(inventory={}),
        controller=ControllerReceiptV4_1(True, True, {}, 0, 0.0),
        find_evidence=evidence,
    )
    assert outcome.action_outcome_status == "success"
