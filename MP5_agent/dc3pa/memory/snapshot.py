"""Immutable memory snapshot helpers for calibration and final evaluation.

Round 1 protected only ``memory.sqlite3``.  Round 1.1 extends the manifest to
all snapshot assets (for example scene images) and validates that the database
being guarded is the same database opened by the runtime.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.parse import quote


class ReadOnlyMemoryError(RuntimeError):
    pass


def sha256_file(path: str | Path) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_sqlite_readonly(
    path: str | Path, *, immutable: bool = True
) -> sqlite3.Connection:
    db_path = Path(path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    suffix = "&immutable=1" if immutable else ""
    uri = f"file:{quote(str(db_path))}?mode=ro{suffix}"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def checkpoint_and_truncate_wal(path: str | Path) -> None:
    """Checkpoint and remove a SQLite WAL before a snapshot is hashed.

    This function must run after all writer transactions have committed and
    before any immutable read-only connection is opened.
    """

    db_path = Path(path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        connection.commit()
    finally:
        connection.close()

    wal_path = Path(f"{db_path}-wal")
    if wal_path.exists() and wal_path.stat().st_size > 0:
        raise ReadOnlyMemoryError(
            f"SQLite WAL is not empty after checkpoint: {wal_path}"
        )


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


def _should_ignore_asset(path: Path, database_path: Path) -> bool:
    resolved = path.resolve()
    if resolved == database_path.resolve():
        return True
    name = path.name
    if name.endswith("-wal") or name.endswith("-shm") or name.endswith("-journal"):
        return True
    if name in {"snapshot_manifest.json", "manifest.json"}:
        return True
    return False


def collect_asset_hashes(
    root: str | Path,
    *,
    database_path: str | Path,
) -> Dict[str, str]:
    root_path = Path(root).resolve()
    db_path = Path(database_path).resolve()
    if not root_path.is_dir():
        raise FileNotFoundError(root_path)
    assets: Dict[str, str] = {}
    for path in sorted(item for item in root_path.rglob("*") if item.is_file()):
        if _should_ignore_asset(path, db_path):
            continue
        relative = path.resolve().relative_to(root_path).as_posix()
        assets[relative] = sha256_file(path)
    return assets


def snapshot_root_digest(
    *,
    database_sha256: str,
    asset_files: Mapping[str, str],
) -> str:
    digest = hashlib.sha256()
    digest.update(b"database\0")
    digest.update(str(database_sha256).encode("ascii"))
    digest.update(b"\0")
    for relative, file_hash in sorted(asset_files.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


@dataclass(frozen=True)
class MemorySnapshotManifest:
    schema_version: int
    created_at_utc: str
    source_commit: str
    database_path: str
    database_sha256: str
    table_counts: Dict[str, int]
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Added in schema version 2.  Defaults preserve compatibility with Round-1
    # manifests, which guarded the database only.
    snapshot_root: str = ""
    asset_files: Dict[str, str] = field(default_factory=dict)
    snapshot_root_sha256: str = ""
    acquisition_manifest_sha256: str = ""

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "MemorySnapshotManifest":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        # Round-1 schema compatibility.
        payload.setdefault("metadata", {})
        payload.setdefault("snapshot_root", "")
        payload.setdefault("asset_files", {})
        payload.setdefault("snapshot_root_sha256", "")
        payload.setdefault("acquisition_manifest_sha256", "")
        return cls(**payload)


def create_snapshot_manifest(
    database_path: str | Path,
    *,
    source_commit: str,
    metadata: Optional[Mapping[str, Any]] = None,
    snapshot_root: str | Path | None = None,
    acquisition_manifest_path: str | Path | None = None,
    checkpoint_wal: bool = False,
) -> MemorySnapshotManifest:
    db_path = Path(database_path).resolve()
    if checkpoint_wal:
        checkpoint_and_truncate_wal(db_path)
    with open_sqlite_readonly(db_path, immutable=False) as connection:
        counts = _table_counts(connection)

    root_path = Path(snapshot_root).resolve() if snapshot_root else db_path.parent
    assets = collect_asset_hashes(root_path, database_path=db_path)
    db_hash = sha256_file(db_path)
    acquisition_hash = (
        sha256_file(acquisition_manifest_path)
        if acquisition_manifest_path is not None
        else ""
    )
    return MemorySnapshotManifest(
        schema_version=2,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        source_commit=str(source_commit),
        database_path=str(db_path),
        database_sha256=db_hash,
        table_counts=counts,
        metadata=dict(metadata or {}),
        snapshot_root=str(root_path),
        asset_files=assets,
        snapshot_root_sha256=snapshot_root_digest(
            database_sha256=db_hash, asset_files=assets
        ),
        acquisition_manifest_sha256=acquisition_hash,
    )


def resolve_snapshot_database(
    manifest: MemorySnapshotManifest,
    *,
    memory_root: str | Path | None = None,
) -> Path:
    manifest_db = Path(manifest.database_path).resolve()
    if memory_root is None:
        return manifest_db
    expected = (Path(memory_root).resolve() / "memory.sqlite3").resolve()
    if expected != manifest_db:
        raise ReadOnlyMemoryError(
            "snapshot manifest/database mismatch: "
            f"manifest={manifest_db}, runtime={expected}"
        )
    return manifest_db


def _current_asset_hashes(manifest: MemorySnapshotManifest) -> Dict[str, str]:
    if not manifest.snapshot_root:
        return {}
    return collect_asset_hashes(
        manifest.snapshot_root,
        database_path=manifest.database_path,
    )


def assert_snapshot_unchanged(manifest: MemorySnapshotManifest) -> None:
    actual_db = sha256_file(manifest.database_path)
    if actual_db != manifest.database_sha256:
        raise ReadOnlyMemoryError(
            "frozen memory database changed during calibration/evaluation: "
            f"expected={manifest.database_sha256}, actual={actual_db}"
        )

    # Schema-v1 manifests intentionally have no asset inventory.
    if manifest.schema_version < 2 and not manifest.asset_files:
        return

    actual_assets = _current_asset_hashes(manifest)
    if actual_assets != manifest.asset_files:
        expected_names = set(manifest.asset_files)
        actual_names = set(actual_assets)
        added = sorted(actual_names - expected_names)
        removed = sorted(expected_names - actual_names)
        changed = sorted(
            name
            for name in expected_names & actual_names
            if manifest.asset_files[name] != actual_assets[name]
        )
        raise ReadOnlyMemoryError(
            "frozen memory assets changed during calibration/evaluation: "
            f"added={added}, removed={removed}, changed={changed}"
        )

    actual_root = snapshot_root_digest(
        database_sha256=actual_db,
        asset_files=actual_assets,
    )
    if manifest.snapshot_root_sha256 and actual_root != manifest.snapshot_root_sha256:
        raise ReadOnlyMemoryError(
            "frozen memory root digest changed during calibration/evaluation: "
            f"expected={manifest.snapshot_root_sha256}, actual={actual_root}"
        )


class SnapshotGuard(AbstractContextManager["SnapshotGuard"]):
    """Verify the frozen database and all snapshot assets before and after a run."""

    def __init__(self, manifest: MemorySnapshotManifest) -> None:
        self.manifest = manifest

    def __enter__(self) -> "SnapshotGuard":
        assert_snapshot_unchanged(self.manifest)
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        assert_snapshot_unchanged(self.manifest)
        return False
