from __future__ import annotations

import csv
import json

from dc3pa.experiments.task_assets import EXPECTED_DIFFICULTIES, load_catalog


def test_catalog_requires_fifty_and_ten_per_difficulty(tmp_path):
    catalog_path = tmp_path / "catalog.csv"
    mapping_path = tmp_path / "mapping.json"
    tasks = []
    with catalog_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["task", "difficulty", "minimum_subgoals"])
        index = 0
        for difficulty in EXPECTED_DIFFICULTIES:
            for local in range(10):
                name = f"{difficulty} task {local}"
                writer.writerow([name, difficulty, local + 1])
                tasks.append(
                    {
                        "task_name": name,
                        "creative_file": f"creative/{index}.json",
                        "formal_spec": f"formal/{index}.json",
                    }
                )
                index += 1
    mapping_path.write_text(
        json.dumps({"tasks": tasks}), encoding="utf-8"
    )
    catalog = load_catalog(catalog_path, mapping_path)
    assert len(catalog) == 50
    assert {
        difficulty: sum(item.difficulty == difficulty for item in catalog)
        for difficulty in EXPECTED_DIFFICULTIES
    } == {difficulty: 10 for difficulty in EXPECTED_DIFFICULTIES}
