from dc3pa.experiments.fusion_feature_freeze import (
    FusionFeatureExportRecord,
    freeze_fusion_feature_dataset,
)


def feature(record_id, role):
    return FusionFeatureExportRecord(
        feature_record_id=record_id,
        source_decision_record_id=f"source-{record_id}",
        source_decision_record_hash=f"hash-{record_id}",
        role=role,
        group_id=f"group-{record_id}",
        task="craft wooden pressure plate",
        seed="1" if role == "dev_train" else "2",
        decision_index=0,
        hard_feasible=True,
        knowledge_coverage=0.7,
        knowledge_unknown=False,
        confidence_probability=0.6,
        environment_probability=0.8,
        decision_correct=True,
        development_input_release_id="dev-input",
        confidence_calibration_release_id="confidence",
        environment_evidence_release_id="environment",
        paper_memory_v5_release_id="memory-v5",
    ).with_hash()


def test_fusion_feature_release_freezes_features_without_fitting(tmp_path):
    release = freeze_fusion_feature_dataset(
        release_name="fusion-features-v1",
        source_commit="a" * 40,
        development_input_release_id="dev-input",
        collection_audit_id="audit",
        confidence_calibration_release_id="confidence",
        environment_evidence_release_id="environment",
        paper_memory_v5_release_id="memory-v5",
        active_taskset_release_id="taskset",
        train_records=[feature("train", "dev_train")],
        tune_records=[feature("tune", "dev_tune")],
        train_jsonl_path=tmp_path / "train.jsonl",
        tune_jsonl_path=tmp_path / "tune.jsonl",
    )
    assert release.eligible
    assert not release.fusion_fitted
    assert not release.holdout_used
    assert release.feature_order[-1] == "environment_probability"
