from __future__ import annotations

from dc3pa.reliability.development_binding import environment_parameter_sha256
from dc3pa.reliability.fusion_dataset import FusionExample


def test_environment_parameter_hash_is_order_independent():
    assert environment_parameter_sha256({"top_k": 3, "threshold": 0.5}) == (
        environment_parameter_sha256({"threshold": 0.5, "top_k": 3})
    )


def test_fusion_example_has_dedicated_provenance_round_trip():
    example = FusionExample(
        episode_id="episode",
        task="obtain log",
        seed="dev-1",
        plan_id="plan",
        plan_version=1,
        step_id="step",
        step_index=0,
        group_id="group",
        split="train",
        label=1,
        features={
            "knowledge": 0.5,
            "model": 0.5,
            "environment": 0.5,
            "environment_coverage": 0.5,
        },
        provenance={"development_protocol_id": "protocol"},
    )

    payload = example.to_dict()
    loaded = FusionExample.from_dict(payload)

    assert payload["provenance"]["development_protocol_id"] == "protocol"
    assert loaded.provenance["development_protocol_id"] == "protocol"
