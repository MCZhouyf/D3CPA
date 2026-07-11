from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from ..contracts import normalize_item_name, utc_now_iso
from ..errors import MemoryInvariantError
from .schema import connect_memory_db


@dataclass(frozen=True)
class DependencyEdge:
    prerequisite: str
    target: str
    relation_type: str
    quantity: float = 1.0
    confidence: float = 1.0
    success_count: int = 1
    first_episode_id: Optional[str] = None
    last_episode_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DependencyGraphStore:
    def __init__(self, db_path: str | Path, connection: sqlite3.Connection | None = None):
        self.db_path = Path(db_path)
        self.connection = connection or connect_memory_db(self.db_path)
        self._owns_connection = connection is None

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def upsert_edges(
        self, episode_id: str, edges: Iterable[DependencyEdge], commit: bool = True
    ) -> int:
        episode = self.connection.execute(
            "SELECT success FROM episodes WHERE episode_id=?", (episode_id,)
        ).fetchone()
        if episode is None:
            raise MemoryInvariantError(f"Unknown episode_id: {episode_id}")
        if int(episode["success"]) != 1:
            raise MemoryInvariantError(
                "Dependency knowledge may only be learned from successful episodes"
            )
        now = utc_now_iso()
        count = 0
        for edge in edges:
            prerequisite = normalize_item_name(edge.prerequisite)
            target = normalize_item_name(edge.target)
            relation_type = edge.relation_type.strip().lower()
            if not prerequisite or not target or prerequisite == target:
                continue
            if edge.quantity <= 0:
                raise MemoryInvariantError("Dependency quantity must be positive")
            if not 0.0 <= edge.confidence <= 1.0:
                raise MemoryInvariantError("Dependency confidence must be in [0, 1]")
            self.connection.execute(
                """
                INSERT INTO dependency_edges(
                    prerequisite, target, relation_type, quantity, confidence,
                    success_count, first_episode_id, last_episode_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(prerequisite, target, relation_type) DO UPDATE SET
                    quantity = MAX(dependency_edges.quantity, excluded.quantity),
                    confidence = MIN(1.0,
                        (dependency_edges.confidence * dependency_edges.success_count + excluded.confidence)
                        / (dependency_edges.success_count + 1)
                    ),
                    success_count = dependency_edges.success_count + 1,
                    last_episode_id = excluded.last_episode_id,
                    updated_at = excluded.updated_at
                """,
                (
                    prerequisite,
                    target,
                    relation_type,
                    float(edge.quantity),
                    float(edge.confidence),
                    episode_id,
                    episode_id,
                    now,
                    now,
                ),
            )
            count += 1
        if commit:
            self.connection.commit()
        return count

    def prerequisites_for(self, target: str) -> List[DependencyEdge]:
        target = normalize_item_name(target)
        rows = self.connection.execute(
            """
            SELECT prerequisite, target, relation_type, quantity, confidence,
                   success_count, first_episode_id, last_episode_id
            FROM dependency_edges
            WHERE target=?
            ORDER BY relation_type, prerequisite
            """,
            (target,),
        ).fetchall()
        return [DependencyEdge(**dict(row)) for row in rows]

    def unsatisfied_prerequisites(
        self, target: str, inventory: Mapping[str, float]
    ) -> List[DependencyEdge]:
        normalized_inventory = {
            normalize_item_name(item): float(quantity)
            for item, quantity in inventory.items()
        }
        return [
            edge
            for edge in self.prerequisites_for(target)
            if normalized_inventory.get(edge.prerequisite, 0.0) < edge.quantity
        ]

    def all_edges(self) -> List[DependencyEdge]:
        rows = self.connection.execute(
            """
            SELECT prerequisite, target, relation_type, quantity, confidence,
                   success_count, first_episode_id, last_episode_id
            FROM dependency_edges
            ORDER BY target, relation_type, prerequisite
            """
        ).fetchall()
        return [DependencyEdge(**dict(row)) for row in rows]

    def export_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                [edge.to_dict() for edge in self.all_edges()],
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
