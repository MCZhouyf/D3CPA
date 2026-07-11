from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from ..contracts import Plan, utc_now_iso
from ..errors import MemoryInvariantError
from .dependency_store import DependencyEdge, DependencyGraphStore
from .encoders import ImageEncoder, TextEncoder, as_float_vector
from .exemplar_store import ExemplarMatch, SceneExemplar, SceneExemplarStore
from .extractor import DependencyExtractor
from .schema import connect_memory_db


@dataclass(frozen=True)
class SceneObservation:
    description: str
    task_context: str
    inventory: Dict[str, float]
    position: str
    step_id: Optional[str] = None
    image: Any = None
    image_path: Optional[str] = None
    image_vector: Optional[np.ndarray] = None
    text_vector: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SuccessfulEpisode:
    task_name: str
    plan: Plan
    scenes: Sequence[SceneObservation] = field(default_factory=tuple)
    episode_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MultimodalMemory:
    def __init__(
        self,
        root_dir: str | Path,
        image_encoder: Optional[ImageEncoder] = None,
        text_encoder: Optional[TextEncoder] = None,
        dependency_extractor: Optional[DependencyExtractor] = None,
    ):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir = self.root_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root_dir / "memory.sqlite3"
        self.connection = connect_memory_db(self.db_path)
        self.dependencies = DependencyGraphStore(self.db_path, connection=self.connection)
        self.exemplars = SceneExemplarStore(self.db_path, connection=self.connection)
        self.image_encoder = image_encoder
        self.text_encoder = text_encoder
        self.dependency_extractor = dependency_extractor or DependencyExtractor()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "MultimodalMemory":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def successful_episode_count(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM episodes WHERE success=1"
        ).fetchone()
        return int(row["count"])

    def _register_episode(self, episode: SuccessfulEpisode) -> None:
        if episode.plan.task != episode.task_name:
            raise MemoryInvariantError(
                f"Episode task {episode.task_name!r} does not match plan task {episode.plan.task!r}"
            )
        self.connection.execute(
            """
            INSERT INTO episodes(episode_id, task_name, success, created_at, metadata_json)
            VALUES (?, ?, 1, ?, ?)
            """,
            (
                episode.episode_id,
                episode.task_name,
                utc_now_iso(),
                json.dumps(episode.metadata, sort_keys=True),
            ),
        )

    def record_success(self, episode: SuccessfulEpisode) -> Dict[str, Any]:
        """Atomically add graph evidence and scene exemplars from a successful task."""

        created_image_paths: List[Path] = []
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self._register_episode(episode)
            edges = self.dependency_extractor.extract(episode.plan)
            edge_count = self.dependencies.upsert_edges(
                episode.episode_id, edges, commit=False
            )
            exemplar_ids = []
            for scene in episode.scenes:
                exemplar = self._build_exemplar(
                    episode, scene, created_image_paths=created_image_paths
                )
                exemplar_ids.append(self.exemplars.add(exemplar, commit=False))
            self.connection.commit()
            return {
                "episode_id": episode.episode_id,
                "edge_count": edge_count,
                "exemplar_ids": exemplar_ids,
            }
        except Exception:
            self.connection.rollback()
            for image_path in reversed(created_image_paths):
                try:
                    image_path.unlink(missing_ok=True)
                except OSError:
                    # Preserve the original exception. An orphan is safer than hiding
                    # the database failure, and can be found by the Stage 0 audit.
                    pass
            raise

    def _persist_image(
        self,
        episode_id: str,
        scene: SceneObservation,
        created_image_paths: Optional[List[Path]] = None,
    ) -> Optional[str]:
        if scene.image_path:
            source = Path(scene.image_path)
            if not source.is_file():
                raise FileNotFoundError(f"Scene image does not exist: {source}")
            suffix = source.suffix or ".png"
            destination = self.images_dir / f"{episode_id}_{uuid.uuid4().hex}{suffix}"
            shutil.copy2(source, destination)
            if created_image_paths is not None:
                created_image_paths.append(destination)
            return str(destination)
        if scene.image is None:
            return None
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Pillow is required to persist raw scene images") from exc
        array = np.asarray(scene.image)
        destination = self.images_dir / f"{episode_id}_{uuid.uuid4().hex}.png"
        Image.fromarray(array.astype(np.uint8)).save(destination)
        if created_image_paths is not None:
            created_image_paths.append(destination)
        return str(destination)

    def _build_exemplar(
        self,
        episode: SuccessfulEpisode,
        scene: SceneObservation,
        created_image_paths: Optional[List[Path]] = None,
    ) -> SceneExemplar:
        image_vector = scene.image_vector
        if image_vector is None and scene.image is not None and self.image_encoder is not None:
            image_vector = self.image_encoder.encode_image(scene.image)
        if image_vector is not None:
            image_vector = as_float_vector(image_vector)
        text_vector = scene.text_vector
        if text_vector is None and self.text_encoder is not None:
            text_vector = self.text_encoder.encode_text(
                f"{scene.description}\n{scene.task_context}"
            )
        if text_vector is not None:
            text_vector = as_float_vector(text_vector)
        return SceneExemplar(
            episode_id=episode.episode_id,
            task_name=episode.task_name,
            step_id=scene.step_id,
            description=scene.description,
            task_context=scene.task_context,
            image_path=self._persist_image(
                episode.episode_id,
                scene,
                created_image_paths=created_image_paths,
            ),
            image_vector=image_vector,
            text_vector=text_vector,
            inventory=dict(scene.inventory),
            position=scene.position,
            metadata=dict(scene.metadata),
        )

    def retrieve_scenes(
        self,
        task_context: str,
        image: Any = None,
        image_vector: Optional[np.ndarray] = None,
        top_k: int = 5,
        visual_weight: float = 0.7,
        task_name: Optional[str] = None,
    ) -> List[ExemplarMatch]:
        if image_vector is None and image is not None and self.image_encoder is not None:
            image_vector = self.image_encoder.encode_image(image)
        text_vector = (
            self.text_encoder.encode_text(task_context)
            if self.text_encoder is not None
            else None
        )
        return self.exemplars.search(
            image_vector=image_vector,
            text_vector=text_vector,
            top_k=top_k,
            visual_weight=visual_weight,
            task_name=task_name,
        )
