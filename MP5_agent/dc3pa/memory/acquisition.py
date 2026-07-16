"""Append-only acquisition records for successful trajectories.

Records are stored one file per successful episode. This avoids partially written
JSONL transactions and makes the offline snapshot builder deterministic.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_id(value: str) -> str:
    cleaned = _SAFE_ID_RE.sub("_", str(value)).strip("._")
    if not cleaned:
        raise ValueError("episode_id must contain at least one safe character")
    return cleaned


def _json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return repr(value)


@dataclass(frozen=True)
class LocalSceneCandidate:
    episode_id: str
    task_name: str
    plan_id: str
    plan_version: int
    step_id: str
    step_index: int
    action_index: int
    local_subgoal: str
    action: Dict[str, Any]
    image_path: str
    pre_inventory: Dict[str, Any] = field(default_factory=dict)
    status: str = "success"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SuccessfulTrajectoryRecord:
    episode_id: str
    task_name: str
    seed: str
    plan: Dict[str, Any]
    telemetry: Tuple[Dict[str, Any], ...]
    scene_candidates: Tuple[LocalSceneCandidate, ...]
    metadata: Dict[str, Any] = field(default_factory=dict)


class AcquisitionStore:
    """Deterministic per-episode store. Failed episodes are never committed."""

    SCHEMA_VERSION = 1

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.episodes_dir = self.root / "episodes"
        self.images_dir = self.root / "images"
        self.episodes_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def episode_path(self, episode_id: str) -> Path:
        return self.episodes_dir / f"{_safe_id(episode_id)}.json"

    def commit_success(self, record: SuccessfulTrajectoryRecord) -> Path:
        if not record.episode_id:
            raise ValueError("record.episode_id must not be empty")
        if any(candidate.status != "success" for candidate in record.scene_candidates):
            raise ValueError("only successful local actions may be committed")

        target = self.episode_path(record.episode_id)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "record": asdict(record),
        }
        data = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            default=_json_default,
        )

        # Resume is idempotent, but an existing deterministic episode may never
        # be replaced with different scientific data.
        if target.exists():
            if target.read_text(encoding="utf-8") != data:
                raise FileExistsError(
                    f"acquisition episode already exists with different content: {target}"
                )
            return target

        fd, temp_name = tempfile.mkstemp(
            dir=str(self.episodes_dir),
            prefix=f".{target.stem}.",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
        return target

    def iter_payloads(self) -> Iterable[Dict[str, Any]]:
        for path in sorted(self.episodes_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != self.SCHEMA_VERSION:
                raise ValueError(f"unsupported acquisition schema: {path}")
            yield payload

    def count(self) -> int:
        return sum(1 for _ in self.episodes_dir.glob("*.json"))

    def write_rgb_array(
        self,
        *,
        episode_id: str,
        step_id: str,
        action_index: int,
        rgb: Any,
    ) -> str:
        """Persist a captured existing frame without taking another env step.

        NumPy is imported lazily because this helper is only used in acquisition.
        """
        import numpy as np

        episode_dir = self.images_dir / _safe_id(episode_id)
        episode_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{_safe_id(step_id)}_a{int(action_index):03d}.npy"
        path = episode_dir / filename
        array = np.asarray(rgb)
        if path.exists():
            existing = np.load(path, allow_pickle=False)
            if existing.dtype != array.dtype or existing.shape != array.shape or not np.array_equal(existing, array):
                raise FileExistsError(
                    f"acquisition image already exists with different content: {path}"
                )
            return str(path.relative_to(self.root))
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp.open("wb") as handle:
                np.save(handle, array, allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        return str(path.relative_to(self.root))
