import pytest

from dc3pa.experiments import source_commit_extension as extension


def inputs():
    return {
        "approval": {"parent_source_commit": "parent"},
        "authorization": {
            "source_commit": "parent",
            "acquisition_schedule_id": "schedule",
            "bootstrap_policy_id": "policy",
            "bootstrap_amendment_id": "amendment",
        },
        "schedule": {"schedule_id": "schedule"},
        "policy": {"policy_id": "policy"},
        "amendment": {"amendment_id": "amendment"},
    }


def test_source_extension_uses_git_computed_protected_identities(monkeypatch, tmp_path):
    monkeypatch.setattr(extension, "_group_identity", lambda repo, commit, paths: "same")
    monkeypatch.setattr(extension, "_tree_identity", lambda repo, commit, path: "same")
    report = extension.audit_source_extension(
        repo_root=tmp_path, parent_commit="parent", final_commit="final", **inputs()
    )
    assert report["eligible"]


def test_source_extension_rejects_protected_drift(monkeypatch, tmp_path):
    monkeypatch.setattr(extension, "_group_identity", lambda repo, commit, paths: commit)
    monkeypatch.setattr(extension, "_tree_identity", lambda repo, commit, path: "same")
    with pytest.raises(ValueError, match="changed"):
        extension.audit_source_extension(
            repo_root=tmp_path, parent_commit="parent", final_commit="final", **inputs()
        )
