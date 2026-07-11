from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episodes (
    episode_id TEXT PRIMARY KEY,
    task_name TEXT NOT NULL,
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dependency_edges (
    prerequisite TEXT NOT NULL,
    target TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 1.0,
    confidence REAL NOT NULL DEFAULT 1.0,
    success_count INTEGER NOT NULL DEFAULT 1,
    first_episode_id TEXT,
    last_episode_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (prerequisite, target, relation_type),
    FOREIGN KEY (first_episode_id) REFERENCES episodes(episode_id),
    FOREIGN KEY (last_episode_id) REFERENCES episodes(episode_id)
);

CREATE TABLE IF NOT EXISTS scene_exemplars (
    exemplar_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    task_name TEXT NOT NULL,
    step_id TEXT,
    description TEXT NOT NULL,
    task_context TEXT NOT NULL,
    image_path TEXT,
    image_vector BLOB,
    text_vector BLOB,
    image_dim INTEGER,
    text_dim INTEGER,
    inventory_json TEXT NOT NULL,
    position TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
);

CREATE INDEX IF NOT EXISTS idx_dependency_target
    ON dependency_edges(target);
CREATE INDEX IF NOT EXISTS idx_exemplar_task
    ON scene_exemplars(task_name);
"""


def connect_memory_db(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.executescript(_SCHEMA)
    current = connection.execute(
        "SELECT value FROM metadata WHERE key='schema_version'"
    ).fetchone()
    if current is None:
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        connection.commit()
    elif int(current["value"]) != SCHEMA_VERSION:
        connection.close()
        raise RuntimeError(
            f"Unsupported memory schema {current['value']}; expected {SCHEMA_VERSION}"
        )
    return connection
