import sqlite3

import pytest

from dc3pa.memory.snapshot import (
    ReadOnlyMemoryError,
    SnapshotGuard,
    checkpoint_and_truncate_wal,
    create_snapshot_manifest,
    resolve_snapshot_database,
)


def _make_db(path):
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO items(value) VALUES ('a')")


def test_schema_v2_guard_detects_asset_changes(tmp_path):
    root = tmp_path / "snapshot"
    root.mkdir()
    db = root / "memory.sqlite3"
    _make_db(db)
    (root / "images").mkdir()
    image = root / "images" / "scene.bin"
    image.write_bytes(b"scene-a")
    checkpoint_and_truncate_wal(db)

    manifest = create_snapshot_manifest(
        db,
        source_commit="test",
        snapshot_root=root,
    )
    with SnapshotGuard(manifest):
        pass

    image.write_bytes(b"scene-b")
    with pytest.raises(ReadOnlyMemoryError):
        with SnapshotGuard(manifest):
            pass


def test_runtime_memory_root_must_match_manifest_database(tmp_path):
    root = tmp_path / "snapshot"
    root.mkdir()
    db = root / "memory.sqlite3"
    _make_db(db)
    checkpoint_and_truncate_wal(db)
    manifest = create_snapshot_manifest(db, source_commit="test", snapshot_root=root)
    assert resolve_snapshot_database(manifest, memory_root=root) == db.resolve()
    with pytest.raises(ReadOnlyMemoryError):
        resolve_snapshot_database(manifest, memory_root=tmp_path / "other")
