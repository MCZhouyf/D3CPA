#!/usr/bin/env python3
"""Reconstruct the immutable acquisition-to-V5 Scene lineage sidecar."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.mineclip_memory_v5 import sha256_file  # noqa: E402


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=repr)


def scene_dedup_key(candidate: Mapping[str, Any], image_path: Path) -> str:
    """Use the exact frozen-memory builder key from build_frozen_memory.py."""
    digest = hashlib.sha256()
    digest.update(
        str(candidate.get("local_subgoal", "")).strip().lower().encode("utf-8")
    )
    digest.update(b"\0")
    digest.update(_canonical_json(candidate.get("action", {})).encode("utf-8"))
    digest.update(b"\0")
    digest.update(sha256_file(image_path).encode("ascii"))
    return digest.hexdigest()


def candidate_id(
    candidate: Mapping[str, Any], *, episode_id: str, dedup_key: str
) -> str:
    payload = {
        "episode_id": episode_id,
        "step_id": str(candidate.get("step_id", "")),
        "step_index": int(candidate.get("step_index", -1)),
        "action_index": int(candidate.get("action_index", -1)),
        "dedup_key": dedup_key,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_records(acquisition_root: Path) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for path in sorted((acquisition_root / "episodes").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = payload.get("record")
        if not isinstance(record, Mapping):
            raise ValueError(f"Acquisition payload has no record object: {path}")
        records.append(record)
    if not records:
        raise ValueError("Acquisition root has no episode records")
    return records


def _retained_rows(database: Path) -> dict[str, Mapping[str, Any]]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT exemplar_id, episode_id, task_name, step_id, metadata_json "
            "FROM scene_exemplars ORDER BY created_at, exemplar_id"
        ).fetchall()
    finally:
        connection.close()
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        metadata = json.loads(row["metadata_json"])
        identity = (
            str(row["episode_id"]),
            str(row["step_id"] or ""),
            int(metadata.get("step_index", -1)),
            int(metadata.get("action_index", -1)),
        )
        key = json.dumps(identity, separators=(",", ":"))
        if key in result:
            raise ValueError(f"Duplicate retained Scene identity: {identity}")
        result[key] = {
            "exemplar_id": str(row["exemplar_id"]),
            "task_name": str(row["task_name"]),
        }
    return result


def build_lineage(acquisition_root: Path, database: Path) -> dict[str, Any]:
    records = _load_records(acquisition_root)
    retained = _retained_rows(database)
    successful: dict[str, list[str]] = {}
    lineage: list[dict[str, Any]] = []
    owner_by_dedup_key: dict[str, Mapping[str, Any]] = {}

    for record in records:
        task = str(record.get("task_name", "")).strip()
        episode_id = str(record.get("episode_id", "")).strip()
        if not task or not episode_id:
            raise ValueError("Acquisition record identity is incomplete")
        successful.setdefault(task, []).append(episode_id)
        for candidate in record.get("scene_candidates", ()):
            if not isinstance(candidate, Mapping):
                raise ValueError(f"{episode_id}: Scene candidate is not an object")
            relative_image = Path(str(candidate.get("image_path", "")))
            image_path = (acquisition_root / relative_image).resolve()
            image_path.relative_to(acquisition_root.resolve())
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            dedup_key = scene_dedup_key(candidate, image_path)
            if dedup_key not in owner_by_dedup_key:
                identity = (
                    episode_id,
                    str(candidate.get("step_id", "")),
                    int(candidate.get("step_index", -1)),
                    int(candidate.get("action_index", -1)),
                )
                retained_row = retained.get(json.dumps(identity, separators=(",", ":")))
                if retained_row is None:
                    raise ValueError(
                        f"Valid candidate disappeared without retained lineage: {identity}"
                    )
                owner_by_dedup_key[dedup_key] = retained_row
            owner = owner_by_dedup_key[dedup_key]
            lineage.append(
                {
                    "candidate_id": candidate_id(
                        candidate, episode_id=episode_id, dedup_key=dedup_key
                    ),
                    "deterministic_dedup_key": dedup_key,
                    "source_task": task,
                    "source_episode_id": episode_id,
                    "valid_local_success_candidate": (
                        str(candidate.get("status", "")).strip().lower() == "success"
                    ),
                    "retained_scene_id": str(owner["exemplar_id"]),
                    "retained_scene_owner_task": str(owner["task_name"]),
                }
            )

    if len(owner_by_dedup_key) != len(retained):
        raise ValueError(
            "Retained Scene count differs from reconstructed unique candidate count: "
            f"{len(retained)} != {len(owner_by_dedup_key)}"
        )
    return {
        "draft_only": False,
        "successful_tasks": [
            {"task": task, "successful_episode_ids": sorted(episode_ids)}
            for task, episode_ids in sorted(successful.items())
        ],
        "candidate_lineage": sorted(
            lineage, key=lambda item: (item["source_episode_id"], item["candidate_id"])
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisition-root", required=True, type=Path)
    parser.add_argument("--paper-memory-database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = build_lineage(
        args.acquisition_root.resolve(), args.paper_memory_database.resolve()
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "successful_task_count": len(payload["successful_tasks"]),
        "candidate_count": len(payload["candidate_lineage"]),
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
