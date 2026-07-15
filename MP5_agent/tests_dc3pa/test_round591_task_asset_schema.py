from __future__ import annotations

import csv
import json

from dc3pa.experiments.task_assets import (
    EXPECTED_DIFFICULTIES,
    validate_task_assets,
)


def test_schema_only_validation_never_grants_formal_readiness(tmp_path):
    asset_root = tmp_path / "assets"
    creative = asset_root / "creative"
    formal = asset_root / "formal"
    creative.mkdir(parents=True)
    formal.mkdir(parents=True)
    catalog_path = asset_root / "catalog.csv"
    mapping_path = asset_root / "mapping.json"
    mappings = []
    with catalog_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["task", "difficulty", "minimum_subgoals"])
        index = 0
        for difficulty in EXPECTED_DIFFICULTIES:
            for local in range(10):
                task_name = f"{difficulty} task {local}"
                creative_rel = f"creative/{index}.json"
                formal_rel = f"formal/{index}.json"
                writer.writerow([task_name, difficulty, local + 1])
                mappings.append(
                    {
                        "task_name": task_name,
                        "creative_file": creative_rel,
                        "formal_spec": formal_rel,
                    }
                )
                (asset_root / creative_rel).write_text(
                    json.dumps(
                        [
                            {
                                "task": f"item {index}",
                                "quantity": 1,
                                "material": None,
                                "tool": None,
                                "platform": None,
                            }
                        ]
                    ),
                    encoding="utf-8",
                )
                (asset_root / formal_rel).write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "task_id": f"task-{index}",
                            "task_name": task_name,
                            "difficulty": difficulty,
                            "minimum_subgoals": local + 1,
                            "operation": "obtain",
                            "target": {
                                "candidate_item_name": f"item {index}",
                                "quantity": 1,
                            },
                            "success_condition": {
                                "candidate_type": "inventory_contains",
                                "candidate_item_name": f"item {index}",
                                "quantity": 1,
                                "must_be_resolved_against_current_evaluator": True,
                            },
                            "creative_task_file": creative_rel,
                            "registry_validation_required": True,
                            "source": {"test": True},
                        }
                    ),
                    encoding="utf-8",
                )
                index += 1
    mapping_path.write_text(
        json.dumps({"tasks": mappings}), encoding="utf-8"
    )
    report, resolutions = validate_task_assets(
        catalog_path=catalog_path,
        mapping_manifest_path=mapping_path,
        asset_root=asset_root,
        runtime_registry_entries=None,
        evaluator_loader=None,
    )
    assert report.task_count == 50
    assert report.creative_schema_valid
    assert report.formal_schema_valid
    assert not report.eligible
    assert not resolutions

    runtime_entries = [
        {"name": f"item {index}", "id": f"minecraft:item_{index}"}
        for index in range(50)
    ]
    report, resolutions = validate_task_assets(
        catalog_path=catalog_path,
        mapping_manifest_path=mapping_path,
        asset_root=asset_root,
        runtime_registry_entries=runtime_entries,
        evaluator_loader=lambda path: json.loads(
            (asset_root / json.loads(path.read_text())["creative_task_file"]).read_text()
        ),
        environment_smoke=lambda path: {"started": True},
        source_commit="4113559efa1458126b10b6bd61976aa9f4c75b8c",
    )
    assert report.eligible
    assert report.evaluator_load_count == 50
    assert report.environment_construction_count == 50
    assert report.runtime_task_tree_sha256
    assert len(resolutions) == 50
    assert report.source_commit == "4113559efa1458126b10b6bd61976aa9f4c75b8c"
