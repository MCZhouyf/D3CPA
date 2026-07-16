import json

import pytest

from dc3pa.experiments.provider_model_alias import (
    ProviderModelAliasPolicy,
    load_provider_model_alias_policy,
    sha256_file,
)


def policy(approval_sha="a" * 64):
    return ProviderModelAliasPolicy(
        policy_name="test-alias-policy",
        approved_by="ZYF",
        approved_at="2026-07-16T03:33:22Z",
        approval_record_sha256=approval_sha,
    ).with_id()


def test_policy_accepts_nonempty_alias_and_preserves_scope_boundary():
    item = policy()

    item.assert_activation_allowed(
        scope="natural_readiness",
        requested_model="gpt-5.1",
    )
    assert item.accepts_returned_model("gpt-4o")
    assert not item.accepts_returned_model("")
    with pytest.raises(ValueError, match="forbidden"):
        item.assert_activation_allowed(
            scope="unknown_scope",
            requested_model="gpt-5.1",
        )


def test_policy_load_fails_when_approval_record_hash_differs(tmp_path):
    approval = tmp_path / "approval.json"
    approval.write_text('{"approved_by":"ZYF"}\n', encoding="utf-8")
    item = policy("b" * 64)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(item.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert sha256_file(approval) != item.approval_record_sha256
    with pytest.raises(ValueError, match="approval record SHA256 mismatch"):
        load_provider_model_alias_policy(
            policy_path,
            approval_record=approval,
        )


def test_unfrozen_policy_is_rejected(tmp_path):
    item = policy().to_dict()
    item["policy_id"] = ""
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(item), encoding="utf-8")

    with pytest.raises(ValueError, match="must be frozen"):
        load_provider_model_alias_policy(policy_path)
