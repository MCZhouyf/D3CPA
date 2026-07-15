from __future__ import annotations

from dc3pa.experiments.task_assets import resolve_registry_names


def test_registry_resolution_is_exact_and_fail_closed():
    entries = [
        {"name": "bucket", "id": "minecraft:bucket"},
        {"name": "log", "id": "minecraft:oak_log"},
    ]
    result = resolve_registry_names(["bucket", "unknown"], entries)
    assert result[0].status == "resolved"
    assert result[0].resolved_runtime_id == "minecraft:bucket"
    assert result[1].status == "unresolved"


def test_duplicate_normalized_registry_name_is_ambiguous():
    result = resolve_registry_names(
        ["bucket"],
        [
            {"name": "bucket", "id": "a"},
            {"name": "bucket", "id": "b"},
        ],
    )
    assert result[0].status == "ambiguous"


def test_repository_loader_uses_current_stage6_task_schema(tmp_path):
    import json
    from dc3pa.integration.round591_tasks import load_formal_task_spec

    creative = tmp_path / "creative_task_jsons"
    formal = tmp_path / "formal_task_specs"
    creative.mkdir()
    formal.mkdir()
    (creative / "bucket.json").write_text(
        json.dumps([{
            "task": "bucket", "quantity": 1,
            "material": {"iron ingot": 3},
            "tool": None, "platform": "crafting table",
        }]),
        encoding="utf-8",
    )
    descriptor = {
        "schema_version": 1,
        "task_id": "hard-bucket",
        "task_name": "craft bucket",
        "difficulty": "hard",
        "minimum_subgoals": 10,
        "operation": "craft",
        "target": {"candidate_item_name": "bucket", "quantity": 1},
        "success_condition": {
            "candidate_type": "inventory_contains",
            "candidate_item_name": "bucket",
            "quantity": 1,
            "must_be_resolved_against_current_evaluator": True,
        },
        "creative_task_file": "creative_task_jsons/bucket.json",
        "registry_validation_required": True,
        "source": {"author_team": "ZYF"},
    }
    path = formal / "bucket.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")

    assert load_formal_task_spec(path)[0]["task"] == "bucket"
