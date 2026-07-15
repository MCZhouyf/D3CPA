from __future__ import annotations

import json
from dataclasses import replace

from dc3pa.experiments.binding import build_artifact_binding
from dc3pa.experiments.blueprint import sha256_file
from dc3pa.experiments.pack import validate_pack
from dc3pa.reliability.activation_policy import (
    ActivationPolicy,
    save_activation_policy,
)
from tests_dc3pa.round56_helpers import make_blueprint


def test_synthetic_blueprint_is_deterministic():
    assert make_blueprint().blueprint_id == make_blueprint().blueprint_id


def _approve(blueprint):
    content_sha = blueprint.content_sha256_before_approval()
    return replace(
        blueprint,
        author_approval=replace(
            blueprint.author_approval,
            approved_blueprint_content_sha256=content_sha,
        ),
        blueprint_id="",
    ).with_id()


def test_pack_validator_detects_policy_hash_and_binding_mismatch(tmp_path):
    policy = ActivationPolicy(
        policy_name="round56-policy",
        noninferiority_margins={"brier": 0.01, "nll": 0.02, "ece": 0.02},
        primary_metrics=("brier", "nll"),
        calibration_metrics=("ece",),
        bootstrap_replicates=200,
    ).with_id()
    policy_path = tmp_path / "policy.json"
    save_activation_policy(policy_path, policy)
    sufficiency_path = tmp_path / "sufficiency.json"
    sufficiency_path.write_text('{"policy":"synthetic"}\n', encoding="utf-8")

    blueprint = _approve(
        replace(
            make_blueprint(),
            activation_policy_id=policy.policy_id,
            activation_policy_file_sha256="wrong-policy-sha",
            data_sufficiency_policy_file_sha256=sha256_file(sufficiency_path),
            blueprint_id="",
        )
    )
    blueprint_path = tmp_path / "blueprint.json"
    blueprint_path.write_text(
        json.dumps(blueprint.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    binding = build_artifact_binding(
        blueprint=blueprint,
        memory_snapshot_sha256="memory-sha",
        memory_snapshot_manifest_id="memory-manifest",
        confidence_artifact_id="confidence-artifact",
        confidence_artifact_file_sha256="confidence-sha",
        selected_environment_parameters={
            "top_k": 1,
            "text_threshold": 0.3,
            "match_threshold": 0.4,
            "environment_scope": "current_context_only",
        },
        source_commit="commit",
        development_protocol_id="protocol-id",
    )
    binding_path = tmp_path / "binding.json"
    binding_payload = replace(
        binding,
        blueprint_id="different-blueprint",
        binding_id="",
    ).with_id().to_dict()
    binding_path.write_text(
        json.dumps(binding_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = validate_pack(
        blueprint_path=blueprint_path,
        activation_policy_path=policy_path,
        data_sufficiency_policy_path=sufficiency_path,
        binding_path=binding_path,
    )
    assert report.eligible is False
    assert "Activation policy file SHA mismatch" in report.errors
    assert "Artifact binding blueprint ID mismatch" in report.errors
