from dc3pa.memory.acquisition import (
    AcquisitionStore,
    LocalSceneCandidate,
    SuccessfulTrajectoryRecord,
)
from dc3pa.memory.offline_builder import OfflineMemoryBuilder


def _record(episode_id, edge, image_path):
    return SuccessfulTrajectoryRecord(
        episode_id=episode_id,
        task_name="task",
        seed=episode_id,
        plan={"edge": list(edge)},
        telemetry=(),
        scene_candidates=(
            LocalSceneCandidate(
                episode_id=episode_id,
                task_name="task",
                plan_id="p",
                plan_version=1,
                step_id="s",
                step_index=0,
                action_index=0,
                local_subgoal="obtain item",
                action={"type": "craft", "object": edge[1]},
                image_path=image_path,
            ),
        ),
    )


def test_offline_builder_filters_edges_by_cross_episode_support(tmp_path):
    store = AcquisitionStore(tmp_path / "acq")
    store.commit_success(_record("e1", ("stick", "pickaxe"), "a.npy"))
    store.commit_success(_record("e2", ("stick", "pickaxe"), "b.npy"))
    store.commit_success(_record("e3", ("coal", "torch"), "c.npy"))

    edges = []
    scenes = []

    def extract(record):
        return [tuple(record["plan"]["edge"])]

    builder = OfflineMemoryBuilder(
        acquisition_store=store,
        dependency_extractor=extract,
        dependency_writer=lambda source, target, support_count: edges.append(
            (source, target, support_count)
        ),
        scene_writer=scenes.append,
        min_dependency_support=2,
    )
    stats = builder.build()
    assert edges == [("stick", "pickaxe", 2)]
    assert stats.acquisition_episodes == 3
    assert stats.retained_dependencies == 1
    assert stats.retained_scenes == 3
