import sys
from pathlib import Path

import pytest


@pytest.mark.minedojo
def test_round513d_real_legacy_controller_and_launcher_import():
    agent_dir = Path(__file__).resolve().parents[1] / "agent"
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))
    from controller import Controller
    from scripts_dc3pa.stage6_run_minecraft import build_parser

    assert callable(getattr(Controller, "check_and_execute_workflow", None))
    mode_action = next(
        action for action in build_parser()._actions if action.dest == "mode"
    )
    assert "chrmlite_estimation_collection_v41" in mode_action.choices
