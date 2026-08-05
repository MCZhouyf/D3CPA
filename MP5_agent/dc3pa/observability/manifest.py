from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from ..config import DC3PAConfig
from ..contracts import utc_now_iso


def _git_value(repo_root: Path, args: list[str]) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return completed.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _package_versions(names: Iterable[str]) -> Dict[str, Optional[str]]:
    versions: Dict[str, Optional[str]] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


@dataclass(frozen=True)
class RunManifest:
    created_at: str
    config: Dict[str, Any]
    config_sha256: str
    repo_root: str
    git_commit: Optional[str]
    git_dirty: Optional[bool]
    python_version: str
    platform: str
    packages: Dict[str, Optional[str]]
    selected_environment: Dict[str, str]

    def write(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(asdict(self), handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")


def create_run_manifest(
    config: DC3PAConfig,
    repo_root: str | Path,
    package_names: Iterable[str] = (
        "minedojo",
        "langchain",
        "openai",
        "numpy",
        "Pillow",
        "chromadb",
    ),
    environment: Optional[Mapping[str, str]] = None,
) -> RunManifest:
    root = Path(repo_root).resolve()
    status = _git_value(root, ["status", "--porcelain"])
    selected_keys = {
        "GPT_MODEL_NAME",
        "TASK_FILE",
        "EPISODE_SEED",
        "DC3PA_WORLD_SEED",
        "DC3PA_SIM_SEED",
        "PYTHONHASHSEED",
        "DC3PA_LEGACY_TASK_HACKS",
        "DC3PA_CONTROLLER_LOW_LEVEL_RECOVERY",
        "MP5_DISABLE_MEMORY",
        "DC3PA_MEMORY_ENABLED",
    }
    source_environment = environment if environment is not None else os.environ
    selected_environment = {
        key: value
        for key, value in source_environment.items()
        if key in selected_keys and key != "OPENAI_API_KEY"
    }
    return RunManifest(
        created_at=utc_now_iso(),
        config=config.to_dict(),
        config_sha256=config.stable_hash(),
        repo_root=str(root),
        git_commit=_git_value(root, ["rev-parse", "HEAD"]),
        git_dirty=(bool(status) if status is not None else None),
        python_version=sys.version,
        platform=platform.platform(),
        packages=_package_versions(package_names),
        selected_environment=selected_environment,
    )
