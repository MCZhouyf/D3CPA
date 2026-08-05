"""Append-only G1 event storage and deterministic Parquet reconstruction."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping

import pyarrow as pa
import pyarrow.parquet as pq

from .trace import JsonlTraceWriter


SCHEMA_VERSION = "g1.v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class G1EpisodeWriter:
    """One append-only raw event file per episode; no shared Parquet append."""

    def __init__(self, root: str | Path, episode_id: str) -> None:
        self.root = Path(root)
        self.episode_id = str(episode_id)
        self.raw_dir = self.root / "raw_events"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.partial_path = self.raw_dir / f"{self.episode_id}.{uuid.uuid4().hex}.partial.jsonl"
        self.writer = JsonlTraceWriter(self.partial_path)

    def write(self, event_type: str, payload: Mapping[str, Any]) -> None:
        self.writer.write(event_type, payload)

    def finalize(self) -> Path:
        completed = self.partial_path.with_suffix(".jsonl")
        os.replace(self.partial_path, completed)
        return completed


def write_parquet_atomically(rows: Iterable[Mapping[str, Any]], destination: str | Path) -> Path:
    """Atomically materialise completed rows; partial raw events remain excluded."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized = [dict(row) for row in rows]
    table = pa.Table.from_pylist(materialized)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.partial")
    pq.write_table(table, temporary)
    os.replace(temporary, path)
    return path
