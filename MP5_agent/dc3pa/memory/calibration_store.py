"""Append-only calibration episode store.

Unlike :mod:`dc3pa.memory.acquisition`, calibration records include both
successful and failed executions.  They are never imported into long-term
memory; they exist only to construct step-level labels and calibration metrics.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple


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
class CalibrationEpisodeRecord:
    episode_id: str
    task_name: str
    seed: str
    success: bool
    plan: Dict[str, Any]
    telemetry: Tuple[Dict[str, Any], ...]
    confidence_observations: Tuple[Dict[str, Any], ...] = ()
    failure_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class CalibrationEpisodeStore:
    """Atomic one-file-per-episode calibration log."""

    SCHEMA_VERSION = 2

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.episodes_dir = self.root / "episodes"
        self.episodes_dir.mkdir(parents=True, exist_ok=True)

    def episode_path(self, episode_id: str) -> Path:
        return self.episodes_dir / f"{_safe_id(episode_id)}.json"

    def commit(self, record: CalibrationEpisodeRecord) -> Path:
        if not record.episode_id:
            raise ValueError("record.episode_id must not be empty")
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
            schema_version = payload.get("schema_version")
            if schema_version == 1:
                record = payload.get("record", {})
                if isinstance(record, dict):
                    record.setdefault("confidence_observations", ())
                yield payload
                continue
            if schema_version != self.SCHEMA_VERSION:
                raise ValueError(f"unsupported calibration schema: {path}")
            yield payload

    def count(self) -> int:
        return sum(1 for _ in self.episodes_dir.glob("*.json"))
