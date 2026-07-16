import sqlite3

from dc3pa.memory.acquisition_scene_only import (
    SceneOnlyDependencyExtractor,
    audit_scene_only_memory,
)


def create_db(path, edge_count=0):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE episodes(id TEXT)")
    connection.execute("CREATE TABLE scene_exemplars(id TEXT)")
    connection.execute("CREATE TABLE dependency_edges(id TEXT)")
    connection.execute("INSERT INTO episodes VALUES ('e')")
    connection.execute("INSERT INTO scene_exemplars VALUES ('s')")
    for index in range(edge_count):
        connection.execute("INSERT INTO dependency_edges VALUES (?)", (str(index),))
    connection.commit()
    connection.close()


def test_scene_only_extractor_returns_no_edges():
    assert SceneOnlyDependencyExtractor().extract(object()) == ()


def test_scene_only_memory_rejects_online_dependency_edges(tmp_path):
    clean = tmp_path / "clean.sqlite3"
    create_db(clean, edge_count=0)
    assert audit_scene_only_memory(clean).eligible

    dirty = tmp_path / "dirty.sqlite3"
    create_db(dirty, edge_count=1)
    assert not audit_scene_only_memory(dirty).eligible
