from __future__ import annotations

from types import SimpleNamespace
import json

import pytest

from dc3pa.reliability.development_binding import activation_policy_id
from dc3pa.reliability.development_protocol import load_protocol


def test_legacy_policy_field_is_supported():
    protocol = SimpleNamespace(
        activation_policy_id="",
        activation_policy_sha256="policy",
    )
    assert activation_policy_id(protocol) == "policy"


def test_conflicting_policy_aliases_fail():
    protocol = SimpleNamespace(
        activation_policy_id="new",
        activation_policy_sha256="old",
    )
    with pytest.raises(ValueError):
        activation_policy_id(protocol)


def test_schema_v1_protocol_loads_as_schema_v2_with_single_policy_id(tmp_path):
    path = tmp_path / "protocol.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "protocol_name": "legacy",
                "assignments": [
                    {
                        "group_id": "train",
                        "task": "obtain log",
                        "seed": "dev-1",
                        "role": "dev_train",
                    },
                    {
                        "group_id": "tune",
                        "task": "obtain stone",
                        "seed": "dev-2",
                        "role": "dev_tune",
                    },
                    {
                        "group_id": "holdout",
                        "task": "obtain iron",
                        "seed": "dev-3",
                        "role": "dev_holdout",
                    },
                ],
                "memory_snapshot_sha256": "memory",
                "confidence_artifact_id": "confidence",
                "knowledge_impl": "hard_gate_v2",
                "model_confidence_impl": "ordinal_calibrated",
                "environment_impl": "topk_v2",
                "environment_scope": "current_context_only",
                "environment_parameters": {"top_k": 3},
                "activation_policy_sha256": "policy",
                "created_from_commit": "commit",
            }
        ),
        encoding="utf-8",
    )

    protocol = load_protocol(path).with_id()
    payload = protocol.to_dict()

    assert protocol.schema_version == 2
    assert payload["activation_policy_id"] == "policy"
    assert "activation_policy_sha256" not in payload
