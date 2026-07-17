import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np

from scripts_dc3pa.build_scene_lineage_input import build_lineage, scene_dedup_key


def test_builder_reconstructs_exact_candidate_to_retained_scene(tmp_path: Path):
    acquisition = tmp_path / "acquisition"
    episodes = acquisition / "episodes"
    image_dir = acquisition / "images" / "episode-1"
    episodes.mkdir(parents=True)
    image_dir.mkdir(parents=True)
    image = image_dir / "scene.npy"
    np.save(image, np.zeros((4, 4, 3), dtype=np.uint8))
    candidate = {
        "action": {"name": "craft", "args": {"obj": {"planks": 4}}},
        "action_index": 0,
        "episode_id": "episode-1",
        "image_path": "images/episode-1/scene.npy",
        "local_subgoal": "craft planks",
        "status": "success",
        "step_id": "step-1",
        "step_index": 0,
    }
    (episodes / "episode-1.json").write_text(
        json.dumps({
            "record": {
                "episode_id": "episode-1",
                "task_name": "craft planks",
                "scene_candidates": [candidate],
            }
        }),
        encoding="utf-8",
    )
    database = tmp_path / "memory.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE scene_exemplars (exemplar_id TEXT, episode_id TEXT, "
        "task_name TEXT, step_id TEXT, metadata_json TEXT, created_at TEXT)"
    )
    connection.execute(
        "INSERT INTO scene_exemplars VALUES (?,?,?,?,?,?)",
        (
            "scene-1",
            "episode-1",
            "craft planks",
            "step-1",
            json.dumps({"step_index": 0, "action_index": 0}),
            "2026-01-01T00:00:00+00:00",
        ),
    )
    connection.commit()
    connection.close()

    payload = build_lineage(acquisition, database)

    assert len(payload["candidate_lineage"]) == 1
    item = payload["candidate_lineage"][0]
    assert item["retained_scene_id"] == "scene-1"
    assert item["deterministic_dedup_key"] == scene_dedup_key(candidate, image)
    assert len(item["candidate_id"]) == hashlib.sha256().digest_size * 2
