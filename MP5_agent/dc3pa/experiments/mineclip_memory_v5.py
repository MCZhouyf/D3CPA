"""Rebuild the same Round 5.10 acquisition data into paper-candidate MineCLIP V5.

No MineDojo episode is rerun. The acquisition root, 40 successful records,
dependency support threshold, taskset, and action-key schema remain fixed.
Only the multimodal encoder/deduplication configuration changes from OpenAI
CLIP ViT-B/16 to the official MineCLIP[attn] static-scene profile.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
ROUND510_ACQUISITION_SOURCE_COMMIT = (
    "bb7469681509968b46e717c777ee782602087968"
)
ROUND510_ACQUISITION_AUDIT_ID = (
    "c65611a908a1e00d3ec1330f3f27e489b9c5848e2adc9a6b44685756cd2ea8df"
)
ROUND510_ACQUISITION_ROOT_SHA256 = (
    "01ab1134830a4663d6cae9b747ecfe4c489fdd21bd51a278ede79face4981292"
)
V4_ENGINEERING_RELEASE_ID = (
    "92bf4512d473addb4beec9a7909428215008ca624d6b802c055b00c15ecea5ce"
)
V4_SNAPSHOT_ROOT_SHA256 = (
    "53357cba689cfa6ff94f414a7f5e6c39ce1897c4cc5945f33fd6b8c05ca28e3f"
)
EXPECTED_SUCCESSFUL_EPISODES = 40
EXPECTED_DEPENDENCY_EDGES = 27
EXPECTED_ACTION_KEY_COVERAGE = 1.0
EXPECTED_MIN_DEPENDENCY_SUPPORT = 2


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class MineCLIPV5RebuildContract:
    contract_name: str
    source_commit: str
    acquisition_source_commit: str
    acquisition_audit_id: str
    acquisition_root_sha256: str
    acquisition_manifest_sha256: str
    v4_engineering_release_id: str
    v4_snapshot_root_sha256: str
    active_taskset_release_id: str
    active_taskset_catalog_sha256: str
    mineclip_policy_id: str
    mineclip_checkpoint_manifest_id: str
    mineclip_checkpoint_sha256: str
    mineclip_checkpoint_md5: str
    mineclip_repository_commit: str
    successful_episode_count: int
    min_dependency_support: int
    expected_dependency_edges: int
    expected_action_key_coverage: float
    no_new_minedojo_episodes: bool = True
    same_acquisition_root_required: bool = True
    successful_records_only: bool = True
    offline_dependency_extraction_only: bool = True
    scene_deduplication_recomputed: bool = True
    v4_marked_engineering_only: bool = True
    v5_marked_paper_candidate: bool = True
    schema_version: int = SCHEMA_VERSION
    contract_id: str = ""

    def __post_init__(self) -> None:
        required = (
            self.contract_name,
            self.source_commit,
            self.acquisition_source_commit,
            self.acquisition_audit_id,
            self.acquisition_root_sha256,
            self.acquisition_manifest_sha256,
            self.v4_engineering_release_id,
            self.v4_snapshot_root_sha256,
            self.active_taskset_release_id,
            self.active_taskset_catalog_sha256,
            self.mineclip_policy_id,
            self.mineclip_checkpoint_manifest_id,
            self.mineclip_checkpoint_sha256,
            self.mineclip_checkpoint_md5,
            self.mineclip_repository_commit,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("MineCLIP V5 rebuild contract is incomplete")
        if self.acquisition_source_commit != ROUND510_ACQUISITION_SOURCE_COMMIT:
            raise ValueError("Round 5.10 acquisition source commit mismatch")
        if self.acquisition_audit_id != ROUND510_ACQUISITION_AUDIT_ID:
            raise ValueError("Round 5.10 acquisition audit ID mismatch")
        if self.acquisition_root_sha256 != ROUND510_ACQUISITION_ROOT_SHA256:
            raise ValueError("Round 5.10 acquisition root mismatch")
        if self.v4_engineering_release_id != V4_ENGINEERING_RELEASE_ID:
            raise ValueError("V4 engineering release ID mismatch")
        if self.v4_snapshot_root_sha256 != V4_SNAPSHOT_ROOT_SHA256:
            raise ValueError("V4 snapshot root mismatch")
        if self.successful_episode_count != EXPECTED_SUCCESSFUL_EPISODES:
            raise ValueError("V5 must use the same 40 successful records")
        if self.min_dependency_support != EXPECTED_MIN_DEPENDENCY_SUPPORT:
            raise ValueError("Dependency support threshold changed")
        if self.expected_dependency_edges != EXPECTED_DEPENDENCY_EDGES:
            raise ValueError("Expected structural dependency count changed")
        if self.expected_action_key_coverage != EXPECTED_ACTION_KEY_COVERAGE:
            raise ValueError("Action-key coverage target changed")
        if not all(
            (
                self.no_new_minedojo_episodes,
                self.same_acquisition_root_required,
                self.successful_records_only,
                self.offline_dependency_extraction_only,
                self.scene_deduplication_recomputed,
                self.v4_marked_engineering_only,
                self.v5_marked_paper_candidate,
            )
        ):
            raise ValueError("MineCLIP V5 rebuild safeguards are incomplete")
        expected = self.compute_contract_id()
        if self.contract_id and self.contract_id != expected:
            raise ValueError("MineCLIP V5 rebuild contract hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("contract_id", None)
        return payload

    def compute_contract_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "MineCLIPV5RebuildContract":
        return replace(self, contract_id=self.compute_contract_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.contract_id else self.with_id()
        payload = item.payload_without_id()
        payload["contract_id"] = item.contract_id
        return payload


@dataclass(frozen=True)
class MineCLIPFrozenMemoryRelease:
    release_name: str
    source_commit: str
    rebuild_contract_id: str
    acquisition_root_sha256: str
    acquisition_manifest_sha256: str
    snapshot_manifest_sha256: str
    snapshot_root_sha256: str
    database_sha256: str
    build_stats_sha256: str
    read_only_smoke_id: str
    successful_episode_count: int
    scene_exemplar_count: int
    dependency_edge_count: int
    structured_action_key_coverage: float
    min_dependency_support: int
    image_encoder_identity: str
    text_encoder_identity: str
    eligible: bool
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        if not self.eligible:
            raise ValueError("Cannot freeze an ineligible MineCLIP snapshot")
        if self.successful_episode_count != EXPECTED_SUCCESSFUL_EPISODES:
            raise ValueError("MineCLIP snapshot episode count is not 40")
        if self.dependency_edge_count != EXPECTED_DEPENDENCY_EDGES:
            raise ValueError("MineCLIP snapshot dependency edges changed")
        if self.structured_action_key_coverage != EXPECTED_ACTION_KEY_COVERAGE:
            raise ValueError("MineCLIP snapshot action-key coverage is not 100%")
        if self.min_dependency_support != EXPECTED_MIN_DEPENDENCY_SUPPORT:
            raise ValueError("MineCLIP snapshot dependency support changed")
        if self.scene_exemplar_count <= 0:
            raise ValueError("MineCLIP snapshot has no Scene Exemplars")
        if "mineclip" not in self.image_encoder_identity.lower():
            raise ValueError("MineCLIP image encoder identity is missing")
        if "mineclip" not in self.text_encoder_identity.lower():
            raise ValueError("MineCLIP text encoder identity is missing")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("MineCLIP frozen release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        return payload

    def compute_release_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "MineCLIPFrozenMemoryRelease":
        return replace(self, release_id=self.compute_release_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.release_id else self.with_id()
        payload = item.payload_without_id()
        payload["release_id"] = item.release_id
        return payload


def freeze_mineclip_snapshot_release(
    *,
    release_name: str,
    contract: MineCLIPV5RebuildContract,
    snapshot_manifest_path: str | Path,
    build_stats_path: str | Path,
    read_only_smoke: Mapping[str, Any],
) -> MineCLIPFrozenMemoryRelease:
    snapshot_path = Path(snapshot_manifest_path)
    stats_path = Path(build_stats_path)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    metadata = snapshot.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ValueError("Snapshot metadata is missing")
    expected_metadata = {
        "mineclip_v5_rebuild_contract_id": contract.contract_id,
        "active_taskset_release_id": contract.active_taskset_release_id,
        "mineclip_policy_id": contract.mineclip_policy_id,
        "mineclip_checkpoint_manifest_id": contract.mineclip_checkpoint_manifest_id,
        "mineclip_checkpoint_sha256": contract.mineclip_checkpoint_sha256,
        "mineclip_repository_commit": contract.mineclip_repository_commit,
        "acquisition_root_sha256": contract.acquisition_root_sha256,
        "mineclip_variant": "attn",
        "scene_frame_strategy": "static_repeat_16",
        "v5_paper_candidate": True,
        "no_new_minedojo_episodes": True,
    }
    mismatches = [
        key for key, expected in expected_metadata.items()
        if metadata.get(key) != expected
    ]
    if mismatches:
        raise ValueError(
            "Snapshot metadata mismatch: " + ", ".join(sorted(mismatches))
        )
    snapshot_sha = sha256_file(snapshot_path)
    if read_only_smoke.get("snapshot_manifest_sha256") != snapshot_sha:
        raise ValueError("Read-only smoke does not bind the snapshot manifest")
    if not read_only_smoke.get("eligible", False):
        raise ValueError("Read-only smoke is ineligible")
    counts = snapshot.get("table_counts", {})
    episodes = int(counts.get("episodes", -1))
    scenes = int(counts.get("scene_exemplars", -1))
    edges = int(counts.get("dependency_edges", -1))
    coverage = float(stats.get("structured_action_key_coverage", 0.0))
    if int(stats.get("acquisition_episodes", -1)) != episodes:
        raise ValueError("Snapshot/build episode count mismatch")
    if int(stats.get("stored_scene_exemplars", -1)) != scenes:
        raise ValueError("Snapshot/build Scene Exemplar count mismatch")
    if int(stats.get("retained_dependency_edges", -1)) != edges:
        raise ValueError("Snapshot/build dependency-edge count mismatch")
    if read_only_smoke.get("snapshot_root_sha256_before") != snapshot.get(
        "snapshot_root_sha256"
    ):
        raise ValueError("Read-only smoke does not bind the snapshot root")
    return MineCLIPFrozenMemoryRelease(
        release_name=release_name,
        source_commit=contract.source_commit,
        rebuild_contract_id=contract.contract_id,
        acquisition_root_sha256=contract.acquisition_root_sha256,
        acquisition_manifest_sha256=contract.acquisition_manifest_sha256,
        snapshot_manifest_sha256=snapshot_sha,
        snapshot_root_sha256=str(snapshot["snapshot_root_sha256"]),
        database_sha256=str(snapshot["database_sha256"]),
        build_stats_sha256=sha256_file(stats_path),
        read_only_smoke_id=str(read_only_smoke["smoke_id"]),
        successful_episode_count=episodes,
        scene_exemplar_count=scenes,
        dependency_edge_count=edges,
        structured_action_key_coverage=coverage,
        min_dependency_support=int(stats.get("min_dependency_support", -1)),
        image_encoder_identity=str(metadata.get("image_encoder_identity", "")),
        text_encoder_identity=str(metadata.get("text_encoder_identity", "")),
        eligible=True,
    ).with_id()


@dataclass(frozen=True)
class MemoryV4V5Comparison:
    contract_id: str
    v4_release_id: str
    v5_snapshot_release_id: str
    acquisition_root_sha256_v4: str
    acquisition_root_sha256_v5: str
    successful_episode_count_v4: int
    successful_episode_count_v5: int
    scene_exemplar_count_v4: int
    scene_exemplar_count_v5: int
    dependency_edge_count_v4: int
    dependency_edge_count_v5: int
    action_key_coverage_v4: float
    action_key_coverage_v5: float
    min_dependency_support_v4: int
    min_dependency_support_v5: int
    image_encoder_v4: str
    image_encoder_v5: str
    text_encoder_v4: str
    text_encoder_v5: str
    same_acquisition_data: bool
    structural_dependencies_preserved: bool
    v4_engineering_only: bool
    v5_paper_candidate: bool
    eligible: bool
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    comparison_id: str = ""

    def __post_init__(self) -> None:
        expected = self.compute_comparison_id()
        if self.comparison_id and self.comparison_id != expected:
            raise ValueError("V4/V5 comparison hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("comparison_id", None)
        payload["errors"] = list(self.errors)
        return payload

    def compute_comparison_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "MemoryV4V5Comparison":
        return replace(self, comparison_id=self.compute_comparison_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.comparison_id else self.with_id()
        payload = item.payload_without_id()
        payload["comparison_id"] = item.comparison_id
        return payload


@dataclass(frozen=True)
class PaperMemoryV5Release:
    release_name: str
    source_commit: str
    rebuild_contract_id: str
    active_taskset_release_id: str
    mineclip_policy_id: str
    mineclip_checkpoint_manifest_id: str
    frozen_memory_release_id: str
    snapshot_manifest_sha256: str
    snapshot_root_sha256: str
    database_sha256: str
    read_only_smoke_id: str
    v4_v5_comparison_id: str
    acquisition_audit_id: str
    acquisition_root_sha256: str
    successful_episode_count: int
    scene_exemplar_count: int
    dependency_edge_count: int
    structured_action_key_coverage: float
    min_dependency_support: int
    encoder_name: str
    encoder_variant: str
    frame_strategy: str
    embedding_dim: int
    paper_candidate: bool
    eligible: bool
    schema_version: int = SCHEMA_VERSION
    release_id: str = ""

    def __post_init__(self) -> None:
        if not self.eligible or not self.paper_candidate:
            raise ValueError("Cannot freeze an ineligible paper memory")
        if self.successful_episode_count != EXPECTED_SUCCESSFUL_EPISODES:
            raise ValueError("Paper memory episode count is not 40")
        if self.dependency_edge_count != EXPECTED_DEPENDENCY_EDGES:
            raise ValueError("Paper memory dependency-edge count changed")
        if self.structured_action_key_coverage != EXPECTED_ACTION_KEY_COVERAGE:
            raise ValueError("Paper memory action-key coverage is not 100%")
        if self.min_dependency_support != EXPECTED_MIN_DEPENDENCY_SUPPORT:
            raise ValueError("Paper memory dependency support changed")
        if self.scene_exemplar_count <= 0:
            raise ValueError("Paper memory has no Scene Exemplars")
        if self.encoder_name != "MineCLIP":
            raise ValueError("Paper memory encoder is not MineCLIP")
        if self.encoder_variant != "attn":
            raise ValueError("Paper memory encoder is not MineCLIP[attn]")
        if self.frame_strategy != "static_repeat_16":
            raise ValueError("Paper memory scene strategy mismatch")
        if self.embedding_dim != 512:
            raise ValueError("Paper memory embedding dimension mismatch")
        expected = self.compute_release_id()
        if self.release_id and self.release_id != expected:
            raise ValueError("Paper memory V5 release hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("release_id", None)
        return payload

    def compute_release_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "PaperMemoryV5Release":
        return replace(self, release_id=self.compute_release_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.release_id else self.with_id()
        payload = item.payload_without_id()
        payload["release_id"] = item.release_id
        return payload


def compare_v4_v5(
    *,
    contract: MineCLIPV5RebuildContract,
    v4_release: Mapping[str, Any],
    v5_release: Mapping[str, Any],
    v5_build_stats: Mapping[str, Any],
) -> MemoryV4V5Comparison:
    errors: list[str] = []
    v4_root = str(
        v4_release.get(
            "acquisition_root_sha256",
            ROUND510_ACQUISITION_ROOT_SHA256,
        )
    )
    v5_root = str(v5_release.get("acquisition_root_sha256", ""))
    same_data = (
        v4_root == v5_root == contract.acquisition_root_sha256
    )
    if not same_data:
        errors.append("V4/V5 acquisition roots differ")

    v4_episodes = int(
        v4_release.get(
            "successful_episode_count",
            v4_release.get("successful_episodes_included", 0),
        )
        or 0
    )
    v5_episodes = int(v5_release.get("successful_episode_count", 0) or 0)
    if (
        v4_episodes,
        v5_episodes,
    ) != (
        EXPECTED_SUCCESSFUL_EPISODES,
        EXPECTED_SUCCESSFUL_EPISODES,
    ):
        errors.append("V4/V5 successful episode counts are not both 40")

    v4_edges = int(
        v4_release.get("dependency_edge_count", EXPECTED_DEPENDENCY_EDGES)
        or 0
    )
    v5_edges = int(
        v5_release.get(
            "dependency_edge_count",
            v5_build_stats.get("retained_dependency_edges", 0),
        )
        or 0
    )
    structural = v4_edges == v5_edges == EXPECTED_DEPENDENCY_EDGES
    if not structural:
        errors.append("Offline dependency graph changed during encoder rebuild")

    v4_coverage = float(
        v4_release.get(
            "structured_action_key_coverage",
            EXPECTED_ACTION_KEY_COVERAGE,
        )
    )
    v5_coverage = float(
        v5_release.get(
            "structured_action_key_coverage",
            v5_build_stats.get("structured_action_key_coverage", 0.0),
        )
    )
    if (
        v4_coverage,
        v5_coverage,
    ) != (
        EXPECTED_ACTION_KEY_COVERAGE,
        EXPECTED_ACTION_KEY_COVERAGE,
    ):
        errors.append("V4/V5 action-key coverage is not 100%")

    v4_support = int(
        v4_release.get(
            "min_dependency_support",
            EXPECTED_MIN_DEPENDENCY_SUPPORT,
        )
        or 0
    )
    v5_support = int(
        v5_release.get(
            "min_dependency_support",
            v5_build_stats.get("min_dependency_support", 0),
        )
        or 0
    )
    if (
        v4_support,
        v5_support,
    ) != (
        EXPECTED_MIN_DEPENDENCY_SUPPORT,
        EXPECTED_MIN_DEPENDENCY_SUPPORT,
    ):
        errors.append("V4/V5 dependency support threshold differs")

    v4_scenes = int(v4_release.get("scene_exemplar_count", 144) or 0)
    v5_scenes = int(
        v5_release.get(
            "scene_exemplar_count",
            v5_build_stats.get("stored_scene_exemplars", 0),
        )
        or 0
    )
    if v5_scenes <= 0:
        errors.append("V5 has no Scene Exemplars")

    return MemoryV4V5Comparison(
        contract_id=contract.contract_id,
        v4_release_id=str(
            v4_release.get("release_id", contract.v4_engineering_release_id)
        ),
        v5_snapshot_release_id=str(v5_release.get("release_id", "")),
        acquisition_root_sha256_v4=v4_root,
        acquisition_root_sha256_v5=v5_root,
        successful_episode_count_v4=v4_episodes,
        successful_episode_count_v5=v5_episodes,
        scene_exemplar_count_v4=v4_scenes,
        scene_exemplar_count_v5=v5_scenes,
        dependency_edge_count_v4=v4_edges,
        dependency_edge_count_v5=v5_edges,
        action_key_coverage_v4=v4_coverage,
        action_key_coverage_v5=v5_coverage,
        min_dependency_support_v4=v4_support,
        min_dependency_support_v5=v5_support,
        image_encoder_v4=str(
            v4_release.get("image_encoder_identity", "OpenAI CLIP ViT-B/16")
        ),
        image_encoder_v5=str(v5_release.get("image_encoder_identity", "")),
        text_encoder_v4=str(
            v4_release.get("text_encoder_identity", "OpenAI CLIP ViT-B/16")
        ),
        text_encoder_v5=str(v5_release.get("text_encoder_identity", "")),
        same_acquisition_data=same_data,
        structural_dependencies_preserved=structural,
        v4_engineering_only=True,
        v5_paper_candidate=True,
        eligible=not errors,
        errors=tuple(dict.fromkeys(errors)),
    ).with_id()
