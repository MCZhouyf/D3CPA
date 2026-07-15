from dc3pa.reliability.confidence_observation import (
    ConfidenceObservationCollector,
    ModelConfidenceObservation,
)


def obs(version, step, probability, cache_hit=False):
    return ModelConfidenceObservation(
        plan_id="p",
        plan_version=version,
        step_id=step,
        step_index=int(step[-1]),
        request_hash=f"hash-{version}-{step}",
        implementation="ordinal_v2",
        confidence_level="likely",
        base_probability=0.7,
        decision_probability=probability,
        model_id="m",
        prompt_version="v",
        prompt_sha256="h",
        cache_hit=cache_hit,
    )


def test_latest_observation_replaces_same_step_and_drain_clears_all_versions():
    collector = ConfidenceObservationCollector()
    collector.record(obs(0, "s0", 0.7))
    collector.record(obs(0, "s0", 0.7, cache_hit=True))
    collector.record(obs(1, "s1", 0.7))
    assert len(collector.snapshot()) == 2
    drained = collector.drain_for_execution(
        plan_id="p", plan_version=1, episode_id="episode"
    )
    assert [item.step_id for item in drained] == ["s1"]
    assert drained[0].episode_id == "episode"
    assert collector.snapshot() == ()
