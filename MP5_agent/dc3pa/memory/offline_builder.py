"""Deterministic offline construction orchestration.

This module deliberately uses small callback protocols so it can wrap the existing
DC3PA DependencyExtractor and multimodal stores without duplicating their logic.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, MutableSet, Optional, Protocol, Sequence, Tuple

from .acquisition import AcquisitionStore
from .snapshot import MemorySnapshotManifest, create_snapshot_manifest


EdgeKey = Tuple[str, str]


class DependencyExtractorAdapter(Protocol):
    def __call__(self, record: Mapping[str, Any]) -> Iterable[EdgeKey]:
        ...


class DependencyWriterAdapter(Protocol):
    def __call__(self, source: str, target: str, *, support_count: int) -> None:
        ...


class SceneWriterAdapter(Protocol):
    def __call__(self, candidate: Mapping[str, Any]) -> None:
        ...


@dataclass(frozen=True)
class OfflineBuildStats:
    acquisition_episodes: int
    dependency_candidates: int
    retained_dependencies: int
    scene_candidates: int
    retained_scenes: int


class OfflineMemoryBuilder:
    """Build memory from sorted successful acquisition records only."""

    def __init__(
        self,
        *,
        acquisition_store: AcquisitionStore,
        dependency_extractor: DependencyExtractorAdapter,
        dependency_writer: DependencyWriterAdapter,
        scene_writer: SceneWriterAdapter,
        min_dependency_support: int = 2,
    ) -> None:
        if min_dependency_support <= 0:
            raise ValueError("min_dependency_support must be positive")
        self.acquisition_store = acquisition_store
        self.dependency_extractor = dependency_extractor
        self.dependency_writer = dependency_writer
        self.scene_writer = scene_writer
        self.min_dependency_support = int(min_dependency_support)

    @staticmethod
    def _scene_key(candidate: Mapping[str, Any]) -> str:
        action = candidate.get("action", {})
        material = json.dumps(
            {
                "local_subgoal": candidate.get("local_subgoal", ""),
                "action": action,
                "image_path": candidate.get("image_path", ""),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=repr,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def build(self) -> OfflineBuildStats:
        payloads = list(self.acquisition_store.iter_payloads())
        edge_support: Counter[EdgeKey] = Counter()
        scene_count = 0
        retained_scenes = 0
        seen_scenes: MutableSet[str] = set()

        for payload in payloads:
            record = payload["record"]
            # Count an edge at most once per successful episode, so a repeated
            # action inside one trajectory cannot artificially satisfy support.
            episode_edges = {
                (str(source), str(target))
                for source, target in self.dependency_extractor(record)
            }
            edge_support.update(episode_edges)

            for candidate in record.get("scene_candidates", []):
                scene_count += 1
                key = self._scene_key(candidate)
                if key in seen_scenes:
                    continue
                seen_scenes.add(key)
                self.scene_writer(candidate)
                retained_scenes += 1

        retained_dependencies = 0
        for (source, target), support_count in sorted(edge_support.items()):
            if support_count < self.min_dependency_support:
                continue
            self.dependency_writer(
                source,
                target,
                support_count=int(support_count),
            )
            retained_dependencies += 1

        return OfflineBuildStats(
            acquisition_episodes=len(payloads),
            dependency_candidates=len(edge_support),
            retained_dependencies=retained_dependencies,
            scene_candidates=scene_count,
            retained_scenes=retained_scenes,
        )

    def build_and_manifest(
        self,
        *,
        database_path: str | Path,
        source_commit: str,
        manifest_path: str | Path,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[OfflineBuildStats, MemorySnapshotManifest]:
        stats = self.build()
        merged_metadata: Dict[str, Any] = dict(metadata or {})
        merged_metadata["offline_build_stats"] = {
            "acquisition_episodes": stats.acquisition_episodes,
            "dependency_candidates": stats.dependency_candidates,
            "retained_dependencies": stats.retained_dependencies,
            "scene_candidates": stats.scene_candidates,
            "retained_scenes": stats.retained_scenes,
        }
        manifest = create_snapshot_manifest(
            database_path,
            source_commit=source_commit,
            metadata=merged_metadata,
        )
        manifest.to_json(manifest_path)
        return stats, manifest
