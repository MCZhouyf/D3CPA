from dc3pa.experiments.scene_lineage_audit import (
    SuccessfulTaskEvidence,
    SceneCandidateLineage,
    audit_scene_lineage,
)


def test_scene_lineage_explains_task_owned_cross_task_and_no_candidate():
    successful = [
        SuccessfulTaskEvidence("task-a", ("episode-a",)),
        SuccessfulTaskEvidence("task-b", ("episode-b",)),
        SuccessfulTaskEvidence("task-c", ("episode-c",)),
    ]
    lineage = [
        SceneCandidateLineage(
            "candidate-a", "dedup-a", "task-a", "episode-a", True, "scene-a", "task-a"
        ),
        SceneCandidateLineage(
            "candidate-b", "dedup-a", "task-b", "episode-b", True, "scene-a", "task-a"
        ),
        SceneCandidateLineage(
            "candidate-c", "dedup-c", "task-c", "episode-c", False, "", ""
        ),
    ]
    report = audit_scene_lineage(
        paper_memory_release_id="memory",
        acquisition_audit_id="audit",
        successful_tasks=successful,
        candidate_lineage=lineage,
    )
    assert report.eligible
    assert report.task_owned_scene_count == 1
    assert report.cross_task_dedup_count == 1
    assert report.no_valid_scene_candidate_count == 1
    assert not report.snapshot_modified
