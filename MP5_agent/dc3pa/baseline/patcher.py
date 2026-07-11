from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from ..errors import PatchApplicationError


@dataclass(frozen=True)
class Replacement:
    old: str
    new: str
    description: str
    alternatives: Sequence[tuple[str, str]] = ()


def _apply_replacements(
    path: Path, replacements: Sequence[Replacement], dry_run: bool
) -> List[str]:
    if not path.exists():
        raise PatchApplicationError(f"Cannot patch missing file: {path}")
    text = path.read_text(encoding="utf-8")
    changed: List[str] = []
    for replacement in replacements:
        candidates = [(replacement.old, replacement.new), *replacement.alternatives]
        if any(new in text for _, new in candidates):
            continue
        matches = [
            (old, new, text.count(old))
            for old, new in candidates
            if text.count(old) > 0
        ]
        occurrences = sum(count for _, _, count in matches)
        if occurrences != 1:
            raise PatchApplicationError(
                f"Guarded patch '{replacement.description}' expected one anchor in {path}, "
                f"found {occurrences}. Refusing to guess."
            )
        old, new, _ = matches[0]
        text = text.replace(old, new, 1)
        changed.append(replacement.description)
    if changed and not dry_run:
        backup = path.with_suffix(path.suffix + ".dc3pa-stage0.bak")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(text, encoding="utf-8")
    return changed


def apply_guarded_legacy_patches(repo_root: str | Path, dry_run: bool = False) -> List[str]:
    """Apply narrow, idempotent patches; abort whenever an expected anchor drifted.

    This intentionally does not rewrite the controller. It only gates the existing
    deep-mining task hacks through ``_is_deep_mining_task`` and gates the fixed
    workflow / planner prerequisite injection. General low-level retries remain intact.
    """

    root = Path(repo_root)
    agent = root / "MP5_agent" / "agent"
    changes: List[str] = []

    planner_replacements = (
        Replacement(
            "from utils import *\n",
            "from utils import *\nfrom dc3pa_feature_flags import legacy_task_hacks_enabled\n",
            "planner: import feature flag",
        ),
        Replacement(
            "    def _inject_prerequisite_steps(self, workflow_dict):\n        workflow = workflow_dict.get(\"workflow\", [])",
            "    def _inject_prerequisite_steps(self, workflow_dict):\n        if not legacy_task_hacks_enabled():\n            return workflow_dict\n        workflow = workflow_dict.get(\"workflow\", [])",
            "planner: gate prerequisite injection",
        ),
    )
    changes.extend(_apply_replacements(agent / "planner.py", planner_replacements, dry_run))

    run_agent_replacements = (
        Replacement(
            "from utils import *\n",
            "from utils import *\nfrom dc3pa_feature_flags import legacy_task_hacks_enabled\n",
            "run_agent: import feature flag",
        ),
        Replacement(
            "        seed = random.randint(1,1000000000000)",
            "        seed_override = os.environ.get(\"DC3PA_WORLD_SEED\")\n        seed = int(seed_override) if seed_override is not None else random.randint(1,1000000000000)\n        random.seed(seed)\n        np.random.seed(seed % (2 ** 32))",
            "run_agent: make world and process RNG seeds externally controllable",
        ),
        Replacement(
            "            seed=3,",
            "            seed=int(os.environ.get(\"DC3PA_SIM_SEED\", 3)),",
            "run_agent: make MineDojo simulator seed externally controllable",
            alternatives=(
                (
                    "            target_quantities=100, seed=3, ",
                    "            target_quantities=100, seed=int(os.environ.get(\"DC3PA_SIM_SEED\", 3)), ",
                ),
            ),
        ),
        Replacement(
            "    def _fixed_workflow_for_task(self, task_information):\n        if task_information.get(\"task\") != \"redstone\":",
            "    def _fixed_workflow_for_task(self, task_information):\n        if not legacy_task_hacks_enabled():\n            return None\n        if task_information.get(\"task\") != \"redstone\":",
            "run_agent: gate fixed redstone workflow",
        ),
    )
    changes.extend(
        _apply_replacements(agent / "run_agent.py", run_agent_replacements, dry_run)
    )

    controller_replacements = (
        Replacement(
            "from utils import *\n",
            "from utils import *\nfrom dc3pa_feature_flags import legacy_task_hacks_enabled\n",
            "controller: import feature flag",
        ),
        Replacement(
            "    def _is_deep_mining_task(self, task_information):\n        return task_information.get(\"task\") in {\"diamond\", \"redstone\"}",
            "    def _is_deep_mining_task(self, task_information):\n        return legacy_task_hacks_enabled() and task_information.get(\"task\") in {\"diamond\", \"redstone\"}",
            "controller: gate deep-mining task hacks",
        ),
    )
    changes.extend(
        _apply_replacements(agent / "controller.py", controller_replacements, dry_run)
    )
    return changes
