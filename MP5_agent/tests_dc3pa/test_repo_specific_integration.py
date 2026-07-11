import os
import subprocess
import sys
from pathlib import Path

from dc3pa.baseline.patcher import apply_guarded_legacy_patches


def _write_repo_fixture(root: Path) -> None:
    agent = root / "MP5_agent" / "agent"
    agent.mkdir(parents=True)
    (agent / "dc3pa_feature_flags.py").write_text(
        "import os\n"
        "def legacy_task_hacks_enabled():\n"
        "    return os.environ.get('DC3PA_LEGACY_TASK_HACKS', '1') == '1'\n",
        encoding="utf-8",
    )
    (agent / "planner.py").write_text(
        "from utils import *\n"
        "class Planner:\n"
        "    def _inject_prerequisite_steps(self, workflow_dict):\n"
        "        workflow = workflow_dict.get(\"workflow\", [])\n",
        encoding="utf-8",
    )
    (agent / "run_agent.py").write_text(
        "from utils import *\n"
        "class Evaluator:\n"
        "    def x(self):\n"
        "        seed = random.randint(1,1000000000000)\n"
        "        env = make(\n"
        "            target_quantities=100, seed=3, \n"
        "        )\n"
        "    def _fixed_workflow_for_task(self, task_information):\n"
        "        if task_information.get(\"task\") != \"redstone\":\n"
        "            return None\n",
        encoding="utf-8",
    )
    (agent / "controller.py").write_text(
        "from utils import *\n"
        "class Controller:\n"
        "    def _is_deep_mining_task(self, task_information):\n"
        "        return task_information.get(\"task\") in {\"diamond\", \"redstone\"}\n",
        encoding="utf-8",
    )


def test_patcher_handles_current_repo_inline_minedojo_seed_anchor(tmp_path):
    _write_repo_fixture(tmp_path)
    first = apply_guarded_legacy_patches(tmp_path)
    second = apply_guarded_legacy_patches(tmp_path)
    run_agent = (tmp_path / "MP5_agent" / "agent" / "run_agent.py").read_text(
        encoding="utf-8"
    )
    assert "run_agent: make MineDojo simulator seed externally controllable" in first
    assert second == []
    assert 'seed=int(os.environ.get("DC3PA_SIM_SEED", 3))' in run_agent


def test_feature_flags_import_from_legacy_agent_cwd():
    agent_dir = Path(__file__).resolve().parents[1] / "agent"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import dc3pa_feature_flags; "
                "print(dc3pa_feature_flags.legacy_task_hacks_enabled())"
            ),
        ],
        cwd=str(agent_dir),
        env={**os.environ, "DC3PA_LEGACY_TASK_HACKS": "0"},
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert completed.stdout.strip() == "False"
