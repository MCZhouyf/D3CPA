from pathlib import Path

import pytest

from dc3pa.baseline.audit import audit_paths
from dc3pa.baseline.patcher import apply_guarded_legacy_patches
from dc3pa.errors import PatchApplicationError


def test_audit_finds_inventory_mutation_and_task_branch(tmp_path):
    source = tmp_path / "controller.py"
    source.write_text(
        'if task == "diamond":\n    env.set_inventory([])\n', encoding="utf-8"
    )
    findings = audit_paths([source])
    categories = {finding.category for finding in findings}
    assert "task_specific_branch" in categories
    assert "environment_state_mutation" in categories


def _make_legacy_fixture(root: Path):
    agent = root / "MP5_agent" / "agent"
    agent.mkdir(parents=True)
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
        "            seed=3,\n"
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


def test_guarded_patcher_is_idempotent(tmp_path):
    _make_legacy_fixture(tmp_path)
    first = apply_guarded_legacy_patches(tmp_path)
    second = apply_guarded_legacy_patches(tmp_path)
    assert first
    assert second == []
    planner = (tmp_path / "MP5_agent" / "agent" / "planner.py").read_text()
    assert "if not legacy_task_hacks_enabled()" in planner
    run_agent = (tmp_path / "MP5_agent" / "agent" / "run_agent.py").read_text()
    assert 'seed_override = os.environ.get("DC3PA_WORLD_SEED")' in run_agent
    assert 'seed=int(os.environ.get("DC3PA_SIM_SEED", 3))' in run_agent


def test_guarded_patcher_refuses_anchor_drift(tmp_path):
    _make_legacy_fixture(tmp_path)
    planner = tmp_path / "MP5_agent" / "agent" / "planner.py"
    planner.write_text("# rewritten upstream\n", encoding="utf-8")
    with pytest.raises(PatchApplicationError):
        apply_guarded_legacy_patches(tmp_path)


def test_audit_does_not_misclassify_rng_seeding(tmp_path):
    source = tmp_path / "run_agent.py"
    source.write_text(
        "np.random.seed(3)\nrandom.seed(3)\nvalue = random.randint(1, 9)\n",
        encoding="utf-8",
    )
    findings = audit_paths([source])
    randomness_lines = {
        finding.line
        for finding in findings
        if finding.category == "uncontrolled_randomness"
    }
    assert randomness_lines == {3}


def test_audit_legacy_sources_uses_repo_relative_paths(tmp_path):
    agent = tmp_path / "MP5_agent" / "agent"
    agent.mkdir(parents=True)
    for name in ("planner.py", "run_agent.py", "controller.py", "work_memory.py"):
        (agent / name).write_text("seed=3\n", encoding="utf-8")
    from dc3pa.baseline.audit import audit_legacy_sources

    findings = audit_legacy_sources(tmp_path)
    assert findings
    assert all(not Path(finding.path).is_absolute() for finding in findings)
