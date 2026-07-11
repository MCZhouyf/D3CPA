import pytest
import numpy as np

from dc3pa.contracts import Plan
from dc3pa.memory import MultimodalMemory, SceneObservation, SuccessfulEpisode
from dc3pa.memory.encoders import HashingTextEncoder


def minimal_plan(task="log"):
    return Plan.from_dict(
        {
            "workflow": [
                {
                    "times": 1,
                    "actions": [
                        {"name": "find", "args": {"obj": task}}
                    ],
                }
            ]
        },
        task=task,
    )


def test_cold_start_retrieval_is_empty(tmp_path):
    with MultimodalMemory(tmp_path, text_encoder=HashingTextEncoder(32)) as memory:
        assert memory.retrieve_scenes("anything") == []


def test_success_record_adds_graph_and_retrievable_scene(tmp_path):
    plan = Plan.from_dict(
        {
            "workflow": [
                {
                    "times": 1,
                    "actions": [
                        {
                            "name": "mine",
                            "args": {"obj": "cobblestone", "tool": "wooden pickaxe"},
                        }
                    ],
                }
            ]
        },
        task="cobblestone",
    )
    with MultimodalMemory(tmp_path, text_encoder=HashingTextEncoder(64)) as memory:
        result = memory.record_success(
            SuccessfulEpisode(
                task_name="cobblestone",
                plan=plan,
                scenes=[
                    SceneObservation(
                        description="stone wall in front of the agent",
                        task_context="mine cobblestone",
                        inventory={"wooden pickaxe": 1},
                        position="ground",
                        image_vector=np.array([1.0, 0.0]),
                    )
                ],
            )
        )
        assert result["edge_count"] == 1
        matches = memory.retrieve_scenes(
            "mine stone", image_vector=np.array([1.0, 0.0]), top_k=1
        )
        assert len(matches) == 1
        assert matches[0].visual_similarity == 1.0
        assert memory.successful_episode_count() == 1


def test_visual_ranking_prefers_closer_vector(tmp_path):
    with MultimodalMemory(tmp_path, text_encoder=None) as memory:
        for task, vector in (("near", [1.0, 0.0]), ("far", [0.0, 1.0])):
            plan = minimal_plan(task)
            memory.record_success(
                SuccessfulEpisode(
                    task_name=task,
                    plan=plan,
                    scenes=[
                        SceneObservation(
                            description=task,
                            task_context=task,
                            inventory={},
                            position="ground",
                            image_vector=np.array(vector),
                        )
                    ],
                )
            )
        matches = memory.retrieve_scenes(
            "", image_vector=np.array([0.9, 0.1]), top_k=2
        )
        assert [match.exemplar.task_name for match in matches] == ["near", "far"]


def test_record_success_rolls_back_database_and_copied_image_on_failure(tmp_path):
    source_image = tmp_path / "source.png"
    source_image.write_bytes(b"not-decoded-because-it-is-only-copied")
    plan = Plan.from_dict(
        {
            "workflow": [
                {
                    "times": 1,
                    "actions": [
                        {
                            "name": "mine",
                            "args": {
                                "obj": "cobblestone",
                                "tool": "wooden pickaxe",
                            },
                        }
                    ],
                }
            ]
        },
        task="cobblestone",
    )
    with MultimodalMemory(tmp_path / "memory") as memory:
        episode = SuccessfulEpisode(
            task_name="cobblestone",
            plan=plan,
            scenes=[
                SceneObservation(
                    description="stone",
                    task_context="mine cobblestone",
                    inventory={"wooden pickaxe": 1},
                    position="ground",
                    image_path=str(source_image),
                    image_vector=np.array([1.0, 0.0]),
                    metadata={"not_json_serializable": object()},
                )
            ],
        )
        with pytest.raises(TypeError):
            memory.record_success(episode)
        assert memory.successful_episode_count() == 0
        assert memory.dependencies.all_edges() == []
        assert memory.exemplars.all() == []
        assert list(memory.images_dir.iterdir()) == []


def test_missing_scene_image_path_is_rejected_without_partial_memory(tmp_path):
    plan = minimal_plan("log")
    with MultimodalMemory(tmp_path / "memory") as memory:
        episode = SuccessfulEpisode(
            task_name="log",
            plan=plan,
            scenes=[
                SceneObservation(
                    description="forest",
                    task_context="find log",
                    inventory={},
                    position="ground",
                    image_path=str(tmp_path / "does-not-exist.png"),
                )
            ],
        )
        with pytest.raises(FileNotFoundError):
            memory.record_success(episode)
        assert memory.successful_episode_count() == 0
        assert memory.dependencies.all_edges() == []
        assert memory.exemplars.all() == []


def test_incompatible_vector_dimensions_are_skipped_not_coerced(tmp_path):
    with MultimodalMemory(tmp_path / "memory") as memory:
        memory.record_success(
            SuccessfulEpisode(
                task_name="log",
                plan=minimal_plan("log"),
                scenes=[
                    SceneObservation(
                        description="forest",
                        task_context="find log",
                        inventory={},
                        position="ground",
                        image_vector=np.array([1.0, 0.0]),
                    )
                ],
            )
        )
        assert memory.retrieve_scenes(
            "", image_vector=np.array([1.0, 0.0, 0.0])
        ) == []


def test_non_finite_vectors_are_rejected(tmp_path):
    with MultimodalMemory(tmp_path / "memory") as memory:
        episode = SuccessfulEpisode(
            task_name="log",
            plan=minimal_plan("log"),
            scenes=[
                SceneObservation(
                    description="forest",
                    task_context="find log",
                    inventory={},
                    position="ground",
                    image_vector=np.array([np.nan, 0.0]),
                )
            ],
        )
        with pytest.raises(ValueError):
            memory.record_success(episode)
        assert memory.successful_episode_count() == 0
