"""Immutable SQLite snapshot helpers for calibration and final evaluation."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from urllib.parse import quote


class ReadOnlyMemoryError(RuntimeError):
    pass


def sha256_file(path: str | Path) -> str:
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_sqlite_readonly(path: str | Path, *, immutable: bool = True) -> sqlite3.Connection:
    db_path = Path(path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    suffix = "&immutable=1" if immutable else ""
    uri = f"file:{quote(str(db_path))}?mode=ro{suffix}"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _table_counts(connection: sqlite3.Connection) -> Dict[str, int]:
    names = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        if not str(row[0]).startswith("sqlite_")
    ]
    counts: Dict[str, int] = {}
    for name in names:
        escaped = name.replace('"', '""')
        counts[name] = int(
            connection.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0]
        )
    return counts


@dataclass(frozen=True)
class MemorySnapshotManifest:
    schema_version: int
    created_at_utc: str
    source_commit: str
    database_path: str
    database_sha256: str
    table_counts: Dict[str, int]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "MemorySnapshotManifest":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**payload)


def create_snapshot_manifest(
    database_path: str | Path,
    *,
    source_commit: str,
    metadata: Optional[Mapping[str, Any]] = None,
) -> MemorySnapshotManifest:
    db_path = Path(database_path).resolve()
    with open_sqlite_readonly(db_path, immutable=False) as connection:
        counts = _table_counts(connection)
    return MemorySnapshotManifest(
        schema_version=1,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        source_commit=str(source_commit),
        database_path=str(db_path),
        database_sha256=sha256_file(db_path),
        table_counts=counts,
        metadata=dict(metadata or {}),
    )


def assert_snapshot_unchanged(manifest: MemorySnapshotManifest) -> None:
    actual = sha256_file(manifest.database_path)
    if actual != manifest.database_sha256:
        raise ReadOnlyMemoryError(
            "frozen memory snapshot changed during calibration/evaluation: "
            f"expected={manifest.database_sha256}, actual={actual}"
        )


class SnapshotGuard(AbstractContextManager["SnapshotGuard"]):
    """Verify the frozen database hash both before and after a run."""

    def __init__(self, manifest: MemorySnapshotManifest) -> None:
        self.manifest = manifest

    def __enter__(self) -> "SnapshotGuard":
        assert_snapshot_unchanged(self.manifest)
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        assert_snapshot_unchanged(self.manifest)
        return False
