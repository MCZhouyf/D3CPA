import json

import pytest

from dc3pa.errors import MemoryInvariantError
from dc3pa.memory import MultimodalMemory
from dc3pa.memory.legacy_import import import_legacy_workflows


def test_import_legacy_workflows_builds_dependencies_without_fake_scenes(tmp_path):
    source = tmp_path / "workflows.json"
    source.write_text(
        json.dumps(
            {
                "cobblestone": {
                    "successful_workflow": [
                        {
                            "times": "1",
                            "actions": [
                                {
                                    "name": "mine",
                                    "args": {"obj": "cobblestone", "tool": "wooden pickaxe"},
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    with MultimodalMemory(tmp_path / "memory") as memory:
        results = import_legacy_workflows(
            memory, source, confirmed_success=True
        )
        assert len(results) == 1
        assert memory.dependencies.prerequisites_for("cobblestone")
        assert memory.exemplars.all() == []


def test_import_requires_explicit_success_confirmation(tmp_path):
    source = tmp_path / "unknown-workflows.json"
    source.write_text('{"log": []}', encoding="utf-8")
    with MultimodalMemory(tmp_path / "memory") as memory:
        with pytest.raises(MemoryInvariantError):
            import_legacy_workflows(memory, source)
        assert memory.successful_episode_count() == 0
