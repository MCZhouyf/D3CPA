#!/usr/bin/env python3
"""Build a frozen DC3PA memory snapshot from Round-1 acquisition records.

This command is intentionally offline: it never opens MineDojo and never calls
an LLM.  It reconstructs successful plans, creates local scene exemplars, removes
low-support dependency edges, checkpoints SQLite WAL, and writes a schema-v2
snapshot manifest covering both the database and scene-image assets.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.contracts import Plan  # noqa: E402
from dc3pa.memory import (  # noqa: E402
    HashingTextEncoder,
    MultimodalMemory,
    RGBHistogramEncoder,
)
from dc3pa.memory.acquisition import AcquisitionStore  # noqa: E402
from dc3pa.memory.multimodal_memory import (  # noqa: E402
    SceneObservation,
    SuccessfulEpisode,
)
from dc3pa.memory.snapshot import (  # noqa: E402
    checkpoint_and_truncate_wal,
    create_snapshot_manifest,
    open_sqlite_readonly,
    sha256_file,
)
from dc3pa.experiments.dry_run import ensure_not_dry_run_artifact_path  # noqa: E402
from dc3pa.reliability.environment_v2 import canonical_action_key  # noqa: E402


def _load_plugin(spec: str, config: Mapping[str, Any]) -> Any:
    if ":" not in spec:
        raise ValueError("plugin must use module:attribute syntax")
    module_name, attribute_name = spec.split(":", 1)
    value = getattr(importlib.import_module(module_name), attribute_name)
    if isinstance(value, type):
        return value(**dict(config))
    if callable(value):
        return value(**dict(config))
    return value


def _build_encoders(args: argparse.Namespace) -> tuple[Any, Any]:
    config = json.loads(args.encoder_config_json or "{}")
    if not isinstance(config, Mapping):
        raise ValueError("--encoder-config-json must decode to an object")
    image_encoder = None
    text_encoder = None
    if args.image_encoder_factory:
        image_encoder = _load_plugin(
            args.image_encoder_factory,
            config.get("image", {}) if isinstance(config.get("image", {}), Mapping) else {},
        )
    if args.text_encoder_factory:
        text_encoder = _load_plugin(
            args.text_encoder_factory,
            config.get("text", {}) if isinstance(config.get("text", {}), Mapping) else {},
        )
    if args.development_encoders:
        if image_encoder is not None or text_encoder is not None:
            raise ValueError(
                "do not combine --development-encoders with explicit encoder plugins"
            )
        image_encoder = RGBHistogramEncoder()
        text_encoder = HashingTextEncoder()
    if args.require_encoders and (image_encoder is None or text_encoder is None):
        raise ValueError("paper snapshots require both image and text encoders")
    return image_encoder, text_encoder


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=repr)


def _scene_key(candidate: Mapping[str, Any], image_path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(str(candidate.get("local_subgoal", "")).strip().lower().encode("utf-8"))
    digest.update(b"\0")
    digest.update(_canonical_json(candidate.get("action", {})).encode("utf-8"))
    digest.update(b"\0")
    digest.update(sha256_file(image_path).encode("ascii"))
    return digest.hexdigest()


def _acquisition_manifest(store: AcquisitionStore, output: Path) -> Path:
    files: Dict[str, str] = {}
    for path in sorted(item for item in store.root.rglob("*") if item.is_file()):
        files[path.relative_to(store.root).as_posix()] = sha256_file(path)
    digest = hashlib.sha256()
    for relative, file_hash in sorted(files.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
    payload = {
        "schema_version": 1,
        "acquisition_root": ".",
        "file_count": len(files),
        "files": files,
        "root_sha256": digest.hexdigest(),
    }
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output


def _load_scene(
    acquisition_root: Path,
    candidate: Mapping[str, Any],
) -> tuple[Path, np.ndarray]:
    relative = str(candidate.get("image_path", ""))
    if not relative:
        raise ValueError("scene candidate has no image_path")
    path = (acquisition_root / relative).resolve()
    try:
        path.relative_to(acquisition_root.resolve())
    except ValueError as exc:
        raise ValueError(f"scene image escapes acquisition root: {path}") from exc
    if not path.is_file():
        raise FileNotFoundError(path)
    return path, np.load(path, allow_pickle=False)


def _delete_low_support_edges(memory: MultimodalMemory, min_support: int) -> int:
    cursor = memory.connection.execute(
        "DELETE FROM dependency_edges WHERE success_count < ?",
        (int(min_support),),
    )
    memory.connection.commit()
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


def build_snapshot(args: argparse.Namespace) -> Dict[str, Any]:
    if args.min_dependency_support <= 0:
        raise ValueError("--min-dependency-support must be positive")

    ensure_not_dry_run_artifact_path(
        args.acquisition_root,
        label="acquisition root",
    )
    acquisition = AcquisitionStore(args.acquisition_root)
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        if not args.reset_output:
            raise FileExistsError(
                f"output directory is not empty: {output_root}; use --reset-output"
            )
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    image_encoder, text_encoder = _build_encoders(args)
    seen_scenes: set[str] = set()
    episodes = 0
    raw_scene_candidates = 0
    retained_scene_candidates = 0
    structured_action_key_scenes = 0

    with MultimodalMemory(
        output_root,
        image_encoder=image_encoder,
        text_encoder=text_encoder,
        readonly=False,
    ) as memory:
        for payload in acquisition.iter_payloads():
            record = payload["record"]
            task_name = str(record["task_name"])
            plan = Plan.from_dict(record["plan"], task=task_name)
            scenes = []
            for candidate in record.get("scene_candidates", []):
                raw_scene_candidates += 1
                image_path, image = _load_scene(acquisition.root, candidate)
                key = _scene_key(candidate, image_path)
                if key in seen_scenes:
                    continue
                seen_scenes.add(key)
                retained_scene_candidates += 1
                local_subgoal = str(candidate.get("local_subgoal", "")).strip()
                action = dict(candidate.get("action", {}))
                action_key = str(
                    candidate.get("metadata", {}).get("action_key")
                    or canonical_action_key(action)
                )
                if action_key:
                    structured_action_key_scenes += 1
                scenes.append(
                    SceneObservation(
                        description=local_subgoal,
                        task_context=_canonical_json(
                            {
                                "local_subgoal": local_subgoal,
                                "action": action,
                                "action_key": action_key,
                            }
                        ),
                        inventory=dict(candidate.get("pre_inventory", {})),
                        position=str(candidate.get("metadata", {}).get("position", "unknown")),
                        step_id=str(candidate.get("step_id", "")) or None,
                        image=image,
                        metadata={
                            "action": action,
                            "action_key": action_key,
                            "local_subgoal": local_subgoal,
                            "step_index": int(candidate.get("step_index", -1)),
                            "action_index": int(candidate.get("action_index", -1)),
                            "source_episode_id": str(record.get("episode_id", "")),
                        },
                    )
                )

            memory.record_success(
                SuccessfulEpisode(
                    episode_id=str(record["episode_id"]),
                    task_name=task_name,
                    plan=plan,
                    scenes=tuple(scenes),
                    metadata={
                        "source": "round11_offline_builder",
                        "seed": str(record.get("seed", "")),
                    },
                )
            )
            episodes += 1

        deleted_edges = _delete_low_support_edges(memory, args.min_dependency_support)
        edge_count = int(
            memory.connection.execute("SELECT COUNT(*) FROM dependency_edges").fetchone()[0]
        )
        exemplar_count = int(
            memory.connection.execute("SELECT COUNT(*) FROM scene_exemplars").fetchone()[0]
        )
        memory.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        memory.connection.commit()

    db_path = output_root / "memory.sqlite3"
    checkpoint_and_truncate_wal(db_path)

    acquisition_manifest_path = _acquisition_manifest(
        acquisition, output_root / "acquisition_manifest.json"
    )
    stats = {
        "acquisition_episodes": episodes,
        "raw_scene_candidates": raw_scene_candidates,
        "retained_scene_candidates": retained_scene_candidates,
        "deleted_low_support_edges": deleted_edges,
        "retained_dependency_edges": edge_count,
        "stored_scene_exemplars": exemplar_count,
        "structured_action_key_scenes": structured_action_key_scenes,
        "structured_action_key_coverage": (
            structured_action_key_scenes / retained_scene_candidates
            if retained_scene_candidates
            else 0.0
        ),
        "min_dependency_support": args.min_dependency_support,
    }
    if (
        args.require_encoders
        and retained_scene_candidates
        and stats["structured_action_key_coverage"] < 0.95
    ):
        raise ValueError(
            "paper snapshot structured action-key coverage is below 95%: "
            f"{stats['structured_action_key_coverage']:.3f}"
        )
    (output_root / "build_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    manifest = create_snapshot_manifest(
        db_path,
        source_commit=args.source_commit,
        metadata={"offline_build_stats": stats},
        snapshot_root=output_root,
        acquisition_manifest_path=acquisition_manifest_path,
        checkpoint_wal=False,
    )
    manifest_path = output_root / "snapshot_manifest.json"
    manifest.to_json(manifest_path)

    # Final smoke test through an immutable read-only connection.
    with open_sqlite_readonly(db_path) as connection:
        connection.execute("SELECT COUNT(*) FROM episodes").fetchone()
        connection.execute("SELECT COUNT(*) FROM dependency_edges").fetchone()
        connection.execute("SELECT COUNT(*) FROM scene_exemplars").fetchone()

    return {
        **stats,
        "output_root": str(output_root),
        "manifest_path": str(manifest_path),
        "snapshot_root_sha256": manifest.snapshot_root_sha256,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--min-dependency-support", type=int, default=2)
    parser.add_argument("--reset-output", action="store_true")
    parser.add_argument("--image-encoder-factory", default="")
    parser.add_argument("--text-encoder-factory", default="")
    parser.add_argument("--encoder-config-json", default="{}")
    parser.add_argument("--development-encoders", action="store_true")
    parser.add_argument("--require-encoders", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_snapshot(args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
