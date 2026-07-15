"""Repository-specific adapters for the ZYF-approved task assets."""

from __future__ import annotations

import contextlib
import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from dc3pa.experiments.task_assets import (
    normalize_name,
    validate_creative_payload,
    validate_formal_payload,
)


ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = ROOT / "agent"


def export_runtime_item_registry() -> list[dict[str, str]]:
    """Export the exact item namespace used by the current MP5 runtime."""
    from minedojo.sim.mc_meta import mc as MC

    runtime_ids = {str(value) for value in MC.MC_ITEM_IDS}
    entries = []
    for runtime_name in sorted({str(value) for value in MC.ALL_ITEMS}):
        canonical_id = f"minecraft:{runtime_name}"
        entries.append(
            {
                "name": normalize_name(runtime_name),
                "id": canonical_id if canonical_id in runtime_ids else runtime_name,
                "runtime_name": runtime_name,
            }
        )
    return entries


def _formal_and_creative(path: Path) -> tuple[Mapping[str, Any], Path, list[Mapping[str, Any]]]:
    formal = json.loads(path.read_text(encoding="utf-8"))
    validate_formal_payload(formal, label=str(path))
    asset_root = path.parent.parent
    creative_path = asset_root / str(formal["creative_task_file"])
    creative = json.loads(creative_path.read_text(encoding="utf-8"))
    validate_creative_payload(creative, label=str(creative_path))
    candidate = normalize_name(formal["target"]["candidate_item_name"])
    success_target = normalize_name(
        formal["success_condition"]["candidate_item_name"]
    )
    runtime_target = normalize_name(creative[0]["task"])
    if len({candidate, success_target, runtime_target}) != 1:
        raise ValueError(
            "Formal target, success target, and creative runtime target differ: "
            f"{candidate!r}, {success_target!r}, {runtime_target!r}"
        )
    return formal, creative_path, creative


def load_formal_task_spec(path: Path) -> list[Mapping[str, Any]]:
    """Load one descriptor through the actual Stage6 task JSON loader."""
    formal_path = Path(path).resolve()
    _, creative_path, expected = _formal_and_creative(formal_path)
    from scripts_dc3pa.stage6_run_minecraft import _load_task_list

    loaded = _load_task_list(creative_path)
    if loaded != expected or len(loaded) != 1:
        raise ValueError("Stage6 task loader changed the approved creative payload")
    return loaded


@contextlib.contextmanager
def _agent_directory():
    previous = Path.cwd()
    os.chdir(AGENT_DIR)
    try:
        yield
    finally:
        os.chdir(previous)


def smoke_formal_task_environment(path: Path) -> Mapping[str, Any]:
    """Construct and close the unchanged Evaluator/MineDojo environment."""
    formal_path = Path(path).resolve()
    formal, creative_path, _ = _formal_and_creative(formal_path)
    if str(AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(AGENT_DIR))
    with _agent_directory():
        runner = importlib.import_module("run_agent")
        runner.args = SimpleNamespace(
            mllm_url="",
            openai_key="",
            gpt_model_name="gpt-5.1",
            task=str(creative_path),
            answer_method="active",
            answer_model="mllm",
        )
        evaluator = runner.Evaluator()
        try:
            if evaluator.env is None:
                raise RuntimeError("Evaluator did not construct a MineDojo environment")
            return {
                "task_name": str(formal["task_name"]),
                "runtime_target": str(evaluator.task_target_name),
                "effective_world_seed": str(evaluator.effective_world_seed),
                "effective_simulator_seed": str(evaluator.effective_simulator_seed),
            }
        finally:
            close = getattr(evaluator.env, "close", None)
            if callable(close):
                close()


__all__ = [
    "export_runtime_item_registry",
    "load_formal_task_spec",
    "smoke_formal_task_environment",
]
