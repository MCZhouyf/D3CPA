import pytest

from dc3pa.contracts import Plan
from dc3pa.errors import MemoryInvariantError
from dc3pa.memory.dependency_store import DependencyEdge, DependencyGraphStore
from dc3pa.memory.extractor import DependencyExtractor
from dc3pa.memory.schema import connect_memory_db


def crafting_plan():
    return Plan.from_dict(
        {
            "workflow": [
                {
                    "times": 1,
                    "actions": [
                        {
                            "name": "craft",
                            "args": {
                                "obj": {"wooden pickaxe": 1},
                                "materials": {"planks": 3, "stick": 2},
                                "platform": "crafting table",
                            },
                        }
                    ],
                },
                {
                    "times": 1,
                    "actions": [
                        {
                            "name": "mine",
                            "args": {"obj": "cobblestone", "tool": "wooden pickaxe"},
                        }
                    ],
                },
            ]
        },
        task="cobblestone",
    )


def test_extractor_learns_explicit_material_platform_and_tool_edges():
    edges = DependencyExtractor().extract(crafting_plan())
    triples = {(e.prerequisite, e.target, e.relation_type) for e in edges}
    assert ("planks", "wooden pickaxe", "material") in triples
    assert ("stick", "wooden pickaxe", "material") in triples
    assert ("crafting table", "wooden pickaxe", "platform") in triples
    assert ("wooden pickaxe", "cobblestone", "tool") in triples


def test_store_requires_successful_episode(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    connection = connect_memory_db(db_path)
    connection.execute(
        "INSERT INTO episodes VALUES (?, ?, ?, ?, ?)",
        ("failed", "x", 0, "now", "{}"),
    )
    connection.commit()
    store = DependencyGraphStore(db_path, connection=connection)
    with pytest.raises(MemoryInvariantError):
        store.upsert_edges("failed", [DependencyEdge("a", "b", "material")])
    connection.close()


def test_edge_evidence_accumulates(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    connection = connect_memory_db(db_path)
    for episode in ("e1", "e2"):
        connection.execute(
            "INSERT INTO episodes VALUES (?, ?, ?, ?, ?)",
            (episode, "x", 1, "now", "{}"),
        )
    connection.commit()
    store = DependencyGraphStore(db_path, connection=connection)
    edge = DependencyEdge("wooden pickaxe", "cobblestone", "tool")
    store.upsert_edges("e1", [edge])
    store.upsert_edges("e2", [edge])
    learned = store.prerequisites_for("cobblestone")
    assert len(learned) == 1
    assert learned[0].success_count == 2
    assert store.unsatisfied_prerequisites("cobblestone", {})
    assert not store.unsatisfied_prerequisites("cobblestone", {"wooden_pickaxe": 1})
    connection.close()


def test_mining_dependency_preserves_explicit_ore_item_name():
    plan = Plan.from_dict(
        {
            "workflow": [
                {
                    "times": 1,
                    "actions": [
                        {
                            "name": "mine",
                            "args": {"obj": "iron ore", "tool": "stone pickaxe"},
                        }
                    ],
                }
            ]
        },
        task="iron ore",
    )
    edges = DependencyExtractor().extract(plan)
    assert [(edge.prerequisite, edge.target, edge.relation_type) for edge in edges] == [
        ("stone pickaxe", "iron ore", "tool")
    ]


def test_scene_store_requires_successful_episode(tmp_path):
    from dc3pa.memory.exemplar_store import SceneExemplar, SceneExemplarStore

    db_path = tmp_path / "memory.sqlite3"
    connection = connect_memory_db(db_path)
    connection.execute(
        "INSERT INTO episodes VALUES (?, ?, ?, ?, ?)",
        ("failed-scene", "x", 0, "now", "{}"),
    )
    connection.commit()
    store = SceneExemplarStore(db_path, connection=connection)
    with pytest.raises(MemoryInvariantError):
        store.add(
            SceneExemplar(
                episode_id="failed-scene",
                task_name="x",
                description="bad",
                task_context="bad",
                inventory={},
                position="unknown",
            )
        )
    assert store.all() == []
    connection.close()
