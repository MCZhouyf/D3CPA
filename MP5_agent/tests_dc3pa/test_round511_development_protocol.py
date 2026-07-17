from dc3pa.experiments.development_protocol_v2 import (
    DevelopmentAssignment,
    audit_development_protocol,
)


def test_pressure_plate_three_way_protocol_is_disjoint_and_holdout_sealed():
    assignments = [
        DevelopmentAssignment(
            "g-train", "craft wooden pressure plate", "1", "easy",
            "dev_train", 0
        ),
        DevelopmentAssignment(
            "g-tune", "craft stick", "2", "basic", "dev_tune", 1
        ),
        DevelopmentAssignment(
            "g-holdout", "craft chest", "3", "easy", "dev_holdout", 2
        ),
    ]
    protocol = audit_development_protocol(
        protocol_name="development-v2",
        source_commit="a" * 40,
        active_taskset_release_id="taskset",
        final_exclusion_id="exclusion",
        assignments=assignments,
        final_heldout_tasks=(),
        final_task_seed_pairs=(),
        holdout_sealed_manifest_hash="sealed",
    )
    assert protocol.eligible
    assert protocol.pressure_plate_assignment_count == 1
    assert not protocol.holdout_plaintext_materialized_for_round511
