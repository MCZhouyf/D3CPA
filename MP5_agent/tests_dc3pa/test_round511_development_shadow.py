from pathlib import Path

import numpy as np

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.experiments.development_shadow import (
    Round511RunBinding,
    Round511ShadowCollector,
)
from dc3pa.integration.execution_observer import make_execution_event
from dc3pa.memory import HashingTextEncoder, MultimodalMemory, RGBHistogramEncoder
from dc3pa.reliability import ModelConfidenceObservation, ReliabilityContext


def _binding() -> Round511RunBinding:
    return Round511RunBinding(
        collection_id="collection",
        development_input_release_id="input-release",
        development_protocol_id="protocol",
        role="dev_train",
        group_id="dev_train:basic:craft button:1",
        task="craft button",
        seed="123",
        difficulty="basic",
        run_id="run-1",
        source_commit="a" * 40,
        paper_memory_v5_release_id="memory-release",
        snapshot_root_sha256="root",
        bootstrap_policy_id="bootstrap",
        prompt_hash_bundle_id="prompts",
    )


def test_shadow_collector_maps_existing_confidence_and_never_writes(tmp_path: Path):
    memory_root = tmp_path / "memory"
    with MultimodalMemory(memory_root):
        pass
    plan = Plan(
        task="button",
        plan_id="plan",
        version=1,
        steps=[
            PlanStep(
                step_id="step",
                actions=[
                    Action(
                        "craft",
                        {
                            "obj": {"button": 1},
                            "materials": {"planks": 1},
                            "platform": None,
                        },
                    )
                ],
            )
        ],
    )
    observation = ModelConfidenceObservation(
        plan_id="plan",
        plan_version=1,
        step_id="step",
        step_index=0,
        request_hash="request",
        implementation="ordinal_v2",
        confidence_level="likely",
        base_probability=0.7,
        decision_probability=0.7,
        model_id="gpt-5.1",
        prompt_version="ordinal-v1",
    )
    with MultimodalMemory(
        memory_root,
        image_encoder=RGBHistogramEncoder(),
        text_encoder=HashingTextEncoder(),
        readonly=True,
    ) as memory:
        collector = Round511ShadowCollector(memory=memory, binding=_binding())
        collector.prepare_attempt(
            plan=plan,
            state=AgentState(task="button", inventory={"planks": 1}),
            context=ReliabilityContext(
                image=np.zeros((8, 8, 3), dtype=np.uint8),
                metadata={"environment_step_index": 0},
            ),
            episode_id="episode",
            attempt=1,
        )
        collector.finalize_attempt(
            plan=plan,
            episode_id="episode",
            execution_telemetry=(
                make_execution_event(
                    "step_finished",
                    plan_id="plan",
                    plan_version=1,
                    step_id="step",
                    step_index=0,
                    status="success",
                ),
            ),
            confidence_observations=(observation.to_dict(),),
            task_completed=True,
            attempt=1,
        )
        records = collector.build_records(
            task_completed=True,
            planner_calls=1,
            reflection_calls=0,
            evaluation_chain_calls=0,
            controller_calls=1,
            bootstrap_event_count=0,
            injected_log_count=0,
            input_tokens=10,
            output_tokens=2,
            reasoning_tokens=1,
            latency_ms=12.0,
            returned_model_identities=("provider-model",),
            snapshot_root_sha256_after="root",
            formal_memory_write_count=0,
            acquisition_write_count=0,
        )

    assert len(records) == 1
    assert records[0].confidence_level == "high"
    assert records[0].decision_correct
    assert records[0].environment_raw_state == "unknown"
    assert records[0].formal_memory_write_count == 0
    assert records[0].acquisition_write_count == 0
