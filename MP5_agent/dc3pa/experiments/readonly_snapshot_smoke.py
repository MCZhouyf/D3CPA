"""Read-only mutation smoke for a frozen memory snapshot."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from dc3pa.memory.snapshot import (
    MemorySnapshotManifest,
    assert_snapshot_unchanged,
    open_sqlite_readonly,
    sha256_file,
)

from .memory_snapshot_release import ReadOnlySnapshotSmoke


def run_readonly_snapshot_smoke(
    snapshot_manifest_path: str | Path,
) -> ReadOnlySnapshotSmoke:
    path = Path(snapshot_manifest_path).resolve()
    manifest = MemorySnapshotManifest.from_json(path)
    errors: list[str] = []

    try:
        assert_snapshot_unchanged(manifest)
        before = manifest.snapshot_root_sha256
    except Exception as exc:
        return ReadOnlySnapshotSmoke(
            snapshot_manifest_sha256=sha256_file(path),
            snapshot_root_sha256_before="",
            snapshot_root_sha256_after="",
            readonly_open_passed=False,
            mutation_attempt_blocked=False,
            database_query_only=False,
            successful_episode_count=0,
            dependency_edge_count=0,
            scene_exemplar_count=0,
            eligible=False,
            errors=(f"snapshot precheck failed: {exc}",),
        ).with_id()

    readonly_open = False
    query_only = False
    mutation_blocked = False
    episodes = edges = exemplars = 0
    try:
        connection = open_sqlite_readonly(manifest.database_path)
        try:
            readonly_open = True
            query_only = bool(
                int(connection.execute("PRAGMA query_only").fetchone()[0])
            )
            episodes = int(
                connection.execute(
                    "SELECT COUNT(*) FROM episodes WHERE success=1"
                ).fetchone()[0]
            )
            edges = int(
                connection.execute(
                    "SELECT COUNT(*) FROM dependency_edges"
                ).fetchone()[0]
            )
            exemplars = int(
                connection.execute(
                    "SELECT COUNT(*) FROM scene_exemplars"
                ).fetchone()[0]
            )
            try:
                connection.execute(
                    "INSERT INTO episodes("
                    "episode_id, task_name, success, created_at, metadata_json"
                    ") VALUES (?, ?, ?, ?, ?)",
                    (
                        "__round510_mutation_probe__",
                        "probe",
                        1,
                        "1970-01-01T00:00:00+00:00",
                        "{}",
                    ),
                )
                connection.commit()
            except sqlite3.Error:
                mutation_blocked = True
            else:
                errors.append("read-only connection unexpectedly accepted a write")
        finally:
            connection.close()
    except Exception as exc:
        errors.append(f"read-only open/query failed: {exc}")

    try:
        assert_snapshot_unchanged(manifest)
        after = manifest.snapshot_root_sha256
    except Exception as exc:
        after = ""
        errors.append(f"snapshot postcheck failed: {exc}")

    if not readonly_open:
        errors.append("read-only database did not open")
    if not query_only:
        errors.append("SQLite query_only was not enabled")
    if not mutation_blocked:
        errors.append("mutation attempt was not blocked")
    if before != after:
        errors.append("snapshot root hash changed during smoke")

    return ReadOnlySnapshotSmoke(
        snapshot_manifest_sha256=sha256_file(path),
        snapshot_root_sha256_before=before,
        snapshot_root_sha256_after=after,
        readonly_open_passed=readonly_open,
        mutation_attempt_blocked=mutation_blocked,
        database_query_only=query_only,
        successful_episode_count=episodes,
        dependency_edge_count=edges,
        scene_exemplar_count=exemplars,
        eligible=not errors,
        errors=tuple(errors),
    ).with_id()
