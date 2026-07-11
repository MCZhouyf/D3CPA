from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import numpy as np

from ..contracts import utc_now_iso
from ..errors import MemoryInvariantError
from .encoders import as_float_vector
from .schema import connect_memory_db


def _serialize_vector(vector: Optional[np.ndarray]) -> tuple[Optional[bytes], Optional[int]]:
    if vector is None:
        return None, None
    normalized = as_float_vector(vector).astype("<f4", copy=False)
    return normalized.tobytes(), int(normalized.size)


def _deserialize_vector(blob: Optional[bytes], dim: Optional[int]) -> Optional[np.ndarray]:
    if blob is None:
        return None
    vector = np.frombuffer(blob, dtype="<f4").copy()
    if dim is not None and vector.size != int(dim):
        raise MemoryInvariantError(
            f"Stored vector dimension mismatch: blob={vector.size}, metadata={dim}"
        )
    return vector


def cosine_similarity(left: Optional[np.ndarray], right: Optional[np.ndarray]) -> Optional[float]:
    if left is None or right is None:
        return None
    left = as_float_vector(left)
    right = as_float_vector(right)
    if left.shape != right.shape:
        return None
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator == 0.0:
        return 0.0
    value = float(np.dot(left, right) / denominator)
    return max(-1.0, min(1.0, value))


def normalized_cosine(left: Optional[np.ndarray], right: Optional[np.ndarray]) -> Optional[float]:
    value = cosine_similarity(left, right)
    return None if value is None else (value + 1.0) / 2.0


@dataclass(frozen=True)
class SceneExemplar:
    episode_id: str
    task_name: str
    description: str
    task_context: str
    inventory: Dict[str, float]
    position: str
    step_id: Optional[str] = None
    image_path: Optional[str] = None
    image_vector: Optional[np.ndarray] = None
    text_vector: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = None
    exemplar_id: str = ""
    created_at: str = ""

    def with_defaults(self) -> "SceneExemplar":
        return SceneExemplar(
            episode_id=self.episode_id,
            task_name=self.task_name,
            description=self.description,
            task_context=self.task_context,
            inventory=dict(self.inventory),
            position=self.position,
            step_id=self.step_id,
            image_path=self.image_path,
            image_vector=self.image_vector,
            text_vector=self.text_vector,
            metadata=dict(self.metadata or {}),
            exemplar_id=self.exemplar_id or uuid.uuid4().hex,
            created_at=self.created_at or utc_now_iso(),
        )


@dataclass(frozen=True)
class ExemplarMatch:
    exemplar: SceneExemplar
    visual_similarity: Optional[float]
    text_similarity: Optional[float]
    combined_score: float


class SceneExemplarStore:
    def __init__(self, db_path: str | Path, connection: sqlite3.Connection | None = None):
        self.db_path = Path(db_path)
        self.connection = connection or connect_memory_db(self.db_path)
        self._owns_connection = connection is None

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def add(self, exemplar: SceneExemplar, commit: bool = True) -> str:
        exemplar = exemplar.with_defaults()
        episode = self.connection.execute(
            "SELECT success FROM episodes WHERE episode_id=?", (exemplar.episode_id,)
        ).fetchone()
        if episode is None:
            raise MemoryInvariantError(f"Unknown episode_id: {exemplar.episode_id}")
        if int(episode["success"]) != 1:
            raise MemoryInvariantError(
                "Scene exemplars may only be stored from successful episodes"
            )
        image_blob, image_dim = _serialize_vector(exemplar.image_vector)
        text_blob, text_dim = _serialize_vector(exemplar.text_vector)
        self.connection.execute(
            """
            INSERT INTO scene_exemplars(
                exemplar_id, episode_id, task_name, step_id, description,
                task_context, image_path, image_vector, text_vector, image_dim,
                text_dim, inventory_json, position, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exemplar.exemplar_id,
                exemplar.episode_id,
                exemplar.task_name,
                exemplar.step_id,
                exemplar.description,
                exemplar.task_context,
                exemplar.image_path,
                image_blob,
                text_blob,
                image_dim,
                text_dim,
                json.dumps(exemplar.inventory, sort_keys=True),
                exemplar.position,
                json.dumps(exemplar.metadata or {}, sort_keys=True),
                exemplar.created_at,
            ),
        )
        if commit:
            self.connection.commit()
        return exemplar.exemplar_id

    def _row_to_exemplar(self, row: sqlite3.Row) -> SceneExemplar:
        return SceneExemplar(
            exemplar_id=row["exemplar_id"],
            episode_id=row["episode_id"],
            task_name=row["task_name"],
            step_id=row["step_id"],
            description=row["description"],
            task_context=row["task_context"],
            image_path=row["image_path"],
            image_vector=_deserialize_vector(row["image_vector"], row["image_dim"]),
            text_vector=_deserialize_vector(row["text_vector"], row["text_dim"]),
            inventory=json.loads(row["inventory_json"]),
            position=row["position"],
            metadata=json.loads(row["metadata_json"]),
            created_at=row["created_at"],
        )

    def all(self, task_name: Optional[str] = None) -> List[SceneExemplar]:
        if task_name is None:
            rows = self.connection.execute(
                "SELECT * FROM scene_exemplars ORDER BY created_at, exemplar_id"
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM scene_exemplars WHERE task_name=? ORDER BY created_at, exemplar_id",
                (task_name,),
            ).fetchall()
        return [self._row_to_exemplar(row) for row in rows]

    def search(
        self,
        image_vector: Optional[np.ndarray],
        text_vector: Optional[np.ndarray],
        top_k: int = 5,
        visual_weight: float = 0.7,
        task_name: Optional[str] = None,
    ) -> List[ExemplarMatch]:
        if top_k <= 0:
            return []
        if not 0.0 <= visual_weight <= 1.0:
            raise ValueError("visual_weight must be in [0, 1]")
        matches: List[ExemplarMatch] = []
        for exemplar in self.all(task_name=task_name):
            visual = normalized_cosine(image_vector, exemplar.image_vector)
            text = normalized_cosine(text_vector, exemplar.text_vector)
            available = []
            if visual is not None:
                available.append((visual_weight, visual))
            if text is not None:
                available.append((1.0 - visual_weight, text))
            if not available:
                continue
            total_weight = sum(weight for weight, _ in available)
            if total_weight == 0.0:
                combined = sum(score for _, score in available) / len(available)
            else:
                combined = sum(weight * score for weight, score in available) / total_weight
            matches.append(
                ExemplarMatch(
                    exemplar=exemplar,
                    visual_similarity=visual,
                    text_similarity=text,
                    combined_score=float(combined),
                )
            )
        matches.sort(key=lambda match: (-match.combined_score, match.exemplar.exemplar_id))
        return matches[:top_k]
