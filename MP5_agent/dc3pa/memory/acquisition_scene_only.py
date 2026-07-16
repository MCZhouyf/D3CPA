"""Scene-only online acquisition memory.

The acquisition protocol may expose successful Scene Exemplars from earlier
successful episodes while formal dependency edges remain offline-only. This
adapter intentionally returns no dependency edges during online acquisition.
The final frozen memory is rebuilt from the append-only acquisition records.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


class SceneOnlyDependencyExtractor:
    """Drop-in extractor whose online edge set is always empty."""

    def extract(self, plan: Any) -> tuple[Any, ...]:
        return ()


@dataclass(frozen=True)
class SceneOnlyMemoryAudit:
    database_path: str
    episode_count: int
    scene_exemplar_count: int
    dependency_edge_count: int
    eligible: bool
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": self.database_path,
            "episode_count": self.episode_count,
            "scene_exemplar_count": self.scene_exemplar_count,
            "dependency_edge_count": self.dependency_edge_count,
            "eligible": self.eligible,
            "errors": list(self.errors),
        }


def audit_scene_only_memory(database_path: str | Path) -> SceneOnlyMemoryAudit:
    path = Path(database_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    errors: list[str] = []
    connection = sqlite3.connect(str(path))
    try:
        def count(table: str) -> int:
            row = connection.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()
            return int(row[0])

        episodes = count("episodes")
        exemplars = count("scene_exemplars")
        edges = count("dependency_edges")
        if edges:
            errors.append(
                "Online acquisition memory contains dependency edges; "
                "dependency extraction must remain offline."
            )
    finally:
        connection.close()
    return SceneOnlyMemoryAudit(
        database_path=str(path),
        episode_count=episodes,
        scene_exemplar_count=exemplars,
        dependency_edge_count=edges,
        eligible=not errors,
        errors=tuple(errors),
    )
