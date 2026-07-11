from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from ..config import DC3PAConfig


@dataclass(frozen=True)
class LegacyLaunchSpec:
    command: List[str]
    cwd: str
    environment: Dict[str, str]

    def redacted(self) -> "LegacyLaunchSpec":
        env = dict(self.environment)
        secret_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
        for name in list(env):
            if any(marker in name.upper() for marker in secret_markers):
                env[name] = "<redacted>"
        return LegacyLaunchSpec(command=list(self.command), cwd=self.cwd, environment=env)


def build_legacy_launch_spec(
    repo_root: str | Path,
    config: DC3PAConfig,
    seed: int,
    task_file: Optional[str] = None,
    model_name: Optional[str] = None,
    base_environment: Optional[Mapping[str, str]] = None,
) -> LegacyLaunchSpec:
    config.validate()
    root = Path(repo_root).resolve()
    agent_dir = root / "MP5_agent" / "agent"
    entrypoint = agent_dir / "run_agent.py"
    if not entrypoint.exists():
        raise FileNotFoundError(f"Legacy entrypoint not found: {entrypoint}")
    resolved_task = task_file or config.task_file
    resolved_model = model_name or config.model_name
    if not resolved_task:
        raise ValueError("A task file is required")
    if not resolved_model:
        raise ValueError("A model name is required")
    task_path = Path(resolved_task)
    if not task_path.is_absolute():
        candidate = root / resolved_task
        task_path = candidate if candidate.exists() else agent_dir / resolved_task
    task_path = task_path.resolve()
    if not task_path.is_file():
        raise FileNotFoundError(f"Task file not found: {task_path}")
    environment = dict(base_environment or os.environ)
    environment.update(config.feature_flags.to_environment())
    environment.update(
        {
            "DC3PA_WORLD_SEED": str(seed),
            "DC3PA_SIM_SEED": str(seed),
            "PYTHONHASHSEED": str(seed),
            "GPT_MODEL_NAME": resolved_model,
            "TASK_FILE": str(task_path),
            "PYTHONPATH": os.pathsep.join(
                filter(
                    None,
                    [
                        str((root / "MP5_agent").resolve()),
                        environment.get("PYTHONPATH", ""),
                    ],
                )
            ),
        }
    )
    command = [sys.executable, str(entrypoint)]
    return LegacyLaunchSpec(command=command, cwd=str(agent_dir), environment=environment)


def run_legacy(
    spec: LegacyLaunchSpec,
    check: bool = False,
    tee_path: str | Path | None = None,
) -> subprocess.CompletedProcess:
    if tee_path is None:
        return subprocess.run(
            spec.command,
            cwd=spec.cwd,
            env=spec.environment,
            check=check,
        )
    output_path = Path(tee_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    captured = []
    with output_path.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            spec.command,
            cwd=spec.cwd,
            env=spec.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log_handle.write(line)
            log_handle.flush()
            captured.append(line)
        return_code = process.wait()
    completed = subprocess.CompletedProcess(
        spec.command, return_code, stdout="".join(captured), stderr=None
    )
    if check and return_code != 0:
        raise subprocess.CalledProcessError(
            return_code, spec.command, output=completed.stdout
        )
    return completed
