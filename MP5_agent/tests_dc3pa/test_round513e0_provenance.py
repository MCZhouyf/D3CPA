import hashlib
import json
from dataclasses import replace

import pytest

from dc3pa.experiments.round513e_provenance import (
    MineCLIPIdentityForensicAudit,
    Round513EPreSmokeIntegrityAuditV2,
    SceneExemplarEvidenceReleaseV5,
    SceneExemplarReleaseForensicAudit,
    audit_mineclip_identity,
    build_blocked_v2_audit,
    canonical_policy_id,
)


def _policy():
    payload = {
        "architecture": "vit",
        "frame_count": 16,
        "frame_strategy": "static_repeat_16",
        "l2_normalize_embeddings": True,
        "output_dim": 512,
        "repository": "https://example.invalid/MineCLIP",
        "repository_commit": "a" * 40,
        "resolution": [160, 256],
        "variant": "attn",
        "pool_type": "attn",
        "mlp_adapter_spec": "adapter",
    }
    payload["policy_id"] = canonical_policy_id(payload)
    return payload


def _mineclip_files(tmp_path):
    checkpoint = tmp_path / "mineclip.ckpt"
    checkpoint.write_bytes(b"immutable-checkpoint")
    policy = _policy()
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    manifest = {
        "policy_id": policy["policy_id"],
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "checkpoint_md5": hashlib.md5(checkpoint.read_bytes()).hexdigest(),
        "manifest_id": "m" * 64,
        "checkpoint_loaded_strictly": True,
        "inference_probe_passed": True,
        "deterministic_repeat_probe_passed": True,
        "image_embedding_dim": 512,
        "text_embedding_dim": 512,
    }
    manifest_path = tmp_path / "checkpoint.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return policy, policy_path, manifest_path, checkpoint


def test_full_policy_canonical_id_is_required_and_short_prefix_is_not_identity(tmp_path):
    policy, policy_path, manifest_path, checkpoint = _mineclip_files(tmp_path)
    assert canonical_policy_id(policy) == policy["policy_id"]
    referenced = tmp_path / "referenced.json"
    referenced.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="does not bind"):
        audit_mineclip_identity(
            source_commit="s" * 40,
            referenced_policy_id=policy["policy_id"][:12],
            referenced_policy_path=referenced,
            actual_policy_path=policy_path,
            checkpoint_manifest_path=manifest_path,
            checkpoint_path=checkpoint,
        )


def test_unresolved_referenced_policy_is_m3_and_cannot_rebind(tmp_path):
    policy, policy_path, manifest_path, checkpoint = _mineclip_files(tmp_path)
    audit = audit_mineclip_identity(
        source_commit="s" * 40,
        referenced_policy_id="f" * 64,
        actual_policy_path=policy_path,
        checkpoint_manifest_path=manifest_path,
        checkpoint_path=checkpoint,
        searched_exact_id_match_count=0,
    )
    assert audit.case == "M3"
    assert audit.classification == "unverifiable_identity"
    assert audit.actual_policy_id == policy["policy_id"]
    assert not audit.referenced_payload_resolved
    assert not audit.automatic_rebind_permitted


def test_byte_equivalent_resolved_reference_is_m1(tmp_path):
    policy, policy_path, manifest_path, checkpoint = _mineclip_files(tmp_path)
    referenced = dict(policy)
    referenced["policy_id"] = "f" * 64
    referenced_path = tmp_path / "referenced.json"
    referenced_path.write_text(json.dumps(referenced), encoding="utf-8")
    audit = audit_mineclip_identity(
        source_commit="s" * 40,
        referenced_policy_id="f" * 64,
        referenced_policy_path=referenced_path,
        actual_policy_path=policy_path,
        checkpoint_manifest_path=manifest_path,
        checkpoint_path=checkpoint,
    )
    assert audit.case == "M1"
    assert audit.canonical_payload_equal
    assert audit.automatic_rebind_permitted


def _scene_record(index):
    return {
        "scene_id": f"scene-{index:03d}",
        "dedup_key": f"dedup-{index:03d}",
        "source_episode_id": f"episode-{index % 40:02d}",
        "source_episode_record_sha256": "e" * 64,
        "source_task": "craft item",
        "owner_task": "craft item",
        "subgoal": "craft prerequisite",
        "action": {"name": "craft", "args": {"obj": "item"}},
        "action_signature": "craft:item",
        "pre_action_image_id": f"image-{index:03d}",
        "pre_action_image_sha256": "i" * 64,
        "source_pre_action_array_sha256": "a" * 64,
        "embedding_row_index": index,
        "image_embedding_sha256": "v" * 64,
        "text_embedding_sha256": "t" * 64,
        "image_embedding_dimension": 512,
        "text_embedding_dimension": 512,
        "image_embedding_finite": True,
        "text_embedding_finite": True,
        "image_embedding_normalized": True,
        "text_embedding_normalized": True,
        "database_row_sha256": "r" * 64,
        "database_table": "scene_exemplars",
        "candidate_id": f"candidate-{index:03d}",
    }


def _scene_release(records):
    return SceneExemplarEvidenceReleaseV5(
        source_commit="s" * 40,
        paper_memory_v5_release_id="p" * 64,
        mineclip_policy_id="m" * 64,
        mineclip_checkpoint_manifest_id="c" * 64,
        snapshot_manifest_sha256="n" * 64,
        snapshot_root_sha256="o" * 64,
        database_sha256="d" * 64,
        asset_manifest_sha256="a" * 64,
        acquisition_manifest_sha256="q" * 64,
        acquisition_root_sha256="u" * 64,
        successful_episode_count=40,
        scene_exemplar_count=144,
        scene_source_episode_count=36,
        dependency_edge_count=27,
        scene_evidence=tuple(records),
    )


def test_aggregate_counts_alone_cannot_create_scene_release():
    with pytest.raises(ValueError, match="Aggregate counts alone"):
        _scene_release(())


def test_scene_release_requires_complete_unique_per_scene_lineage():
    release = _scene_release([_scene_record(index) for index in range(144)]).with_id()
    assert release.release_id
    incomplete = _scene_record(0)
    incomplete.pop("dedup_key")
    with pytest.raises(ValueError, match="mandatory lineage"):
        _scene_release([incomplete] + [_scene_record(index) for index in range(1, 144)])


def test_blocked_m3_v2_preserves_v1_and_cannot_prepare():
    mineclip = MineCLIPIdentityForensicAudit(
        source_commit="s" * 40,
        referenced_policy_id="r" * 64,
        actual_policy_id="a" * 64,
        referenced_payload_resolved=False,
        actual_payload_verified=True,
        canonical_payload_equal=None,
        case="M3",
        classification="unverifiable_identity",
        referenced_source_label=None,
        actual_source_label="paper-memory-v5/mineclip-policy",
        actual_policy_file_sha256="p" * 64,
        actual_policy_canonical_sha256="a" * 64,
        checkpoint_file_sha256="c" * 64,
        checkpoint_file_md5="d" * 32,
        checkpoint_manifest_file_sha256="f" * 64,
        checkpoint_manifest_id="m" * 64,
        repository_commit="g" * 40,
        variant="attn",
        frame_strategy="static_repeat_16",
        output_dimension=512,
        normalized_embeddings=True,
        inference_probe_passed=True,
        deterministic_probe_passed=True,
        automatic_rebind_permitted=False,
        searched_exact_id_match_count=0,
    ).with_id()
    release = _scene_release([_scene_record(index) for index in range(144)]).with_id()
    scene = SceneExemplarReleaseForensicAudit(
        source_commit="s" * 40,
        missing_historical_release_id="h" * 64,
        exact_historical_release_match_count=0,
        case="S2",
        scene_release_reconstruction_eligible=True,
        evidence_release_id=release.release_id,
        paper_memory_v5_release_id="p" * 64,
        mineclip_policy_id="a" * 64,
        scene_count=144,
        unique_scene_count=144,
        complete_lineage_count=144,
        successful_episode_count=40,
        scene_source_episode_count=36,
        dependency_edge_count=27,
        image_asset_count=144,
        normalized_image_embedding_count=144,
        normalized_text_embedding_count=144,
        snapshot_root_sha256_before="s" * 64,
        snapshot_root_sha256_after="s" * 64,
        database_sha256_before="d" * 64,
        database_sha256_after="d" * 64,
        asset_manifest_sha256_before="a" * 64,
        asset_manifest_sha256_after="a" * 64,
        write_count=0,
        errors=(),
    ).with_id()
    v2 = build_blocked_v2_audit(
        source_commit="s" * 40,
        blocked_v1_audit_id="v" * 64,
        blocked_v1_audit_sha256_before="b" * 64,
        blocked_v1_audit_sha256_after="b" * 64,
        mineclip_audit=mineclip,
        scene_audit=scene,
        scene_release=release,
        snapshot_guard_passed=True,
    )
    assert v2.status == "BLOCKED_MINECLIP_POLICY_MISMATCH"
    assert not v2.eligible_for_preparation
    assert not v2.smoke_pool_generated
    assert not v2.gamma_input_generated
    assert not v2.minedojo_started


def test_v2_rejects_mutated_blocked_v1_audit():
    with pytest.raises(ValueError, match="Blocked V1 audit was mutated"):
        Round513EPreSmokeIntegrityAuditV2(
            source_commit="s" * 40,
            blocked_v1_audit_id="v" * 64,
            blocked_v1_audit_sha256_before="a" * 64,
            blocked_v1_audit_sha256_after="b" * 64,
            mineclip_forensic_audit_id="m" * 64,
            mineclip_case="M3",
            scene_forensic_audit_id="e" * 64,
            scene_case="S2",
            scene_evidence_release_id="r" * 64,
            contract_supersession_release_id=None,
            binding_equivalence_audit_id=None,
            snapshot_guard_passed=True,
            status="BLOCKED_MINECLIP_POLICY_MISMATCH",
            eligible_for_preparation=False,
        )
