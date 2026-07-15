from __future__ import annotations

from types import SimpleNamespace

from dc3pa.reliability.development_binding import (
    CollectionOutcome,
    DatasetBindingExpectation,
    DevelopmentCollectionManifest,
    environment_parameter_sha256,
    validate_dataset_binding,
)
from dc3pa.reliability.final_test_exclusion import (
    FinalEvaluationTask,
    FinalTestExclusionManifest,
)
from dc3pa.reliability.fusion_dataset import FusionExample
from dc3pa.reliability.fusion_features import FEATURE_SCHEMA_VERSION


class _Protocol:
    protocol_id = "protocol"
    memory_snapshot_sha256 = "memory"
    confidence_artifact_id = "confidence"
    knowledge_impl = "hard_gate_v2"
    model_confidence_impl = "ordinal_calibrated"
    environment_impl = "topk_v2"
    environment_scope = "current_context_only"
    environment_parameters = {"top_k": 3}
    assignments = (
        SimpleNamespace(
            group_id="group-1",
            task="obtain log",
            seed="dev-1",
            role="dev_train",
            goal_status="experience_covered",
        ),
    )

    def assignment_map(self):
        return {item.group_id: item for item in self.assignments}

    def groups_for(self, role):
        return frozenset(
            item.group_id for item in self.assignments if item.role == role
        )

    def compute_protocol_id(self):
        return self.protocol_id


def _exclusion():
    return FinalTestExclusionManifest(
        manifest_name="final",
        tasks=(
            FinalEvaluationTask(
                task="obtain log",
                difficulty="basic",
                goal_status="experience_covered",
                test_seeds=("test-1",),
            ),
        ),
        created_from_commit="commit",
    ).with_id()


def _example(provenance):
    return FusionExample(
        episode_id="episode",
        task="obtain log",
        seed="dev-1",
        plan_id="plan",
        plan_version=1,
        step_id="step",
        step_index=0,
        group_id="group-1",
        split="train",
        label=1,
        features={
            "knowledge": 0.5,
            "model": 0.5,
            "environment": 0.5,
            "environment_coverage": 0.5,
        },
        confidence_artifact_id="confidence",
        memory_snapshot_sha256="memory",
        metadata={"provenance": provenance},
    )


def _expectation(exclusion):
    return DatasetBindingExpectation(
        role="dev_train",
        protocol_id="protocol",
        final_test_exclusion_id=exclusion.manifest_id,
        memory_snapshot_sha256="memory",
        confidence_artifact_id="confidence",
        knowledge_impl="hard_gate_v2",
        model_confidence_impl="ordinal_calibrated",
        environment_impl="topk_v2",
        environment_scope="current_context_only",
        environment_parameter_sha256=environment_parameter_sha256({"top_k": 3}),
        source_commit="commit",
    )


def _collection(exclusion):
    return DevelopmentCollectionManifest(
        manifest_name="train",
        protocol_id="protocol",
        final_test_exclusion_id=exclusion.manifest_id,
        role="dev_train",
        outcomes=(
            CollectionOutcome(
                group_id="group-1",
                role="dev_train",
                task="obtain log",
                seed="dev-1",
                status="included",
                usable_example_count=1,
            ),
        ),
        source_commit="commit",
    ).with_id()


def test_dataset_must_match_protocol_and_provenance():
    exclusion = _exclusion()
    expectation = _expectation(exclusion)
    provenance = {
        "development_protocol_id": "protocol",
        "final_test_exclusion_id": exclusion.manifest_id,
        "memory_snapshot_sha256": "memory",
        "confidence_artifact_id": "confidence",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "knowledge_impl": "hard_gate_v2",
        "model_confidence_impl": "ordinal_calibrated",
        "environment_impl": "topk_v2",
        "environment_scope": "current_context_only",
        "environment_parameter_sha256": environment_parameter_sha256({"top_k": 3}),
        "source_commit": "commit",
    }
    report = validate_dataset_binding(
        [_example(provenance)],
        protocol=_Protocol(),
        final_exclusion=exclusion,
        collection=_collection(exclusion),
        expectation=expectation,
    )
    assert report.eligible


def test_unregistered_group_is_rejected():
    exclusion = _exclusion()
    example = _example({})
    object.__setattr__(example, "group_id", "extra")
    report = validate_dataset_binding(
        [example],
        protocol=_Protocol(),
        final_exclusion=exclusion,
        collection=_collection(exclusion),
        expectation=_expectation(exclusion),
    )
    assert not report.eligible
    assert any("Unexpected group" in error for error in report.errors)
