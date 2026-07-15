from __future__ import annotations

from dataclasses import replace

import pytest

from dc3pa.experiments.blueprint import AuthorApproval
from dc3pa.experiments.author_decisions import AuthorDecisionPackManifest
from tests_dc3pa.round56_helpers import make_blueprint


def test_pack_manifest_id_is_deterministic():
    kwargs = dict(
        pack_name="pack",
        source_commit="commit",
        input_sha256={"a": "1"},
        output_sha256={"b": "2"},
        prompt_hashes={"planner": "3"},
        activation_policy_id="policy",
        final_test_exclusion_id="exclusion",
    )
    assert (
        AuthorDecisionPackManifest(**kwargs).with_id().pack_id
        == AuthorDecisionPackManifest(**kwargs).with_id().pack_id
    )


def test_pending_author_approval_cannot_freeze_blueprint():
    blueprint = make_blueprint()
    pending = replace(
        blueprint,
        author_approval=AuthorApproval(
            approval_record_id="PENDING_AUTHOR_APPROVAL",
            approved_at="PENDING_AUTHOR_APPROVAL",
            approved_blueprint_content_sha256="PENDING_AUTHOR_APPROVAL",
        ),
        blueprint_id="",
    )
    with pytest.raises(ValueError, match="Author approval hash"):
        pending.with_id()
