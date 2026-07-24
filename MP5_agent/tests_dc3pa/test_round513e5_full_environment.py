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
from dc3pa.experiments.round513e6d2 import (
    ActionObjectSignatureRegistryV2,
    find_evidence_from_telemetry_v2,
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


@pytest.mark.minedojo
def test_round513e6_find_v2_telemetry_records_raw_step_evidence_without_extra_env_step():
    agent_dir = Path(__file__).resolve().parents[1] / "agent"
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))
    import structured_actions

    class CountingEnv:
        def __init__(self):
            self.step_count = 0
            blocks = np.full((11, 11, 11), "air", dtype=object)
            blocks[6, 4, 5] = "stone"
            self.events = {
                "voxels": {"block_name": blocks},
                "location_stats": {
                    "pos": np.asarray([0.0, 64.0, 0.0]),
                    "yaw": np.asarray([0.0]),
                    "pitch": np.asarray([0.0]),
                },
                "rgb": np.zeros((3, 8, 8), dtype=np.uint8),
            }

        def step(self, action):
            del action
            self.step_count += 1
            return self.events, 0.0, False, {}

    env = CountingEnv()
    memory = SimpleNamespace()
    structured_actions.begin_find_observation_trace(memory, "iron_ore", "iron ore", 120)
    assert not structured_actions._fresh_aboveground_clearance_is_safe(
        env, memory, "iron ore"
    )
    # sleep() has always used exactly five no-op env.step calls. Telemetry adds none.
    assert env.step_count == 5
    structured_actions.finish_find_observation_trace(
        memory, "safety_clearance_stop", budget_exhausted=False, complete=True
    )
    raw = structured_actions.consume_find_observation_trace(memory)
    assert len(raw["observation_steps_v2"]) == 1
    step = raw["observation_steps_v2"][0]
    assert step["detector_sensor_status"] == "ok"
    assert step["observation_sha256"]
    assert step["image_sha256"]
    assert step["controller_step_result"] == "safety_clearance_stop"

    telemetry = [{
        "event_type": "action_finished",
        "payload": {"result": {"post_state_evidence": {"find_observation": raw}}},
    }]
    evidence = find_evidence_from_telemetry_v2(
        Action("find", {"obj": "iron_ore"}),
        telemetry,
        ActionObjectSignatureRegistryV2().with_id(),
    )
    assert evidence is not None
    assert evidence.steps[0].required_sensor_complete
