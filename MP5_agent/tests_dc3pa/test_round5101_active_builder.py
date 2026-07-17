import json

from scripts_dc3pa.build_active_pressure_plate_taskset import build_descriptors


def test_active_builder_describes_all_runtime_and_formal_assets(tmp_path):
    root = tmp_path / "active"
    for folder in ("creative_task_jsons", "formal_task_specs"):
        target = root / folder
        target.mkdir(parents=True)
        (target / "craft_wooden_pressure_plate.json").write_text("{}")
        (target / "mine_log.json").write_text("{}")

    descriptors = build_descriptors(root)
    paths = {item.path for item in descriptors}
    assert "creative_task_jsons/craft_wooden_pressure_plate.json" in paths
    assert "formal_task_specs/craft_wooden_pressure_plate.json" in paths
    pressure_spec = next(
        item
        for item in descriptors
        if item.path == "formal_task_specs/craft_wooden_pressure_plate.json"
    )
    assert pressure_spec.required_new_task_presence is True
    acquisition_audit = next(
        item for item in descriptors if item.artifact_kind == "acquisition_audit"
    )
    assert acquisition_audit.required_new_task_presence is False
    json.dumps([item.to_dict() for item in descriptors])
