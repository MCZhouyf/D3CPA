from dc3pa.experiments.round513_readiness import (
    BLOCK_REASON,
    build_blocked_readiness,
)


def test_unapproved_smoke_readiness_is_blocked_without_fabricated_coverage():
    release, smoke, behavior, report, decision = build_blocked_readiness(
        source_commit="a" * 40,
        smoke_design_id="s" * 64,
        authorization_id="u" * 64,
        record_schema_id="r" * 64,
        synthetic_test_count=52,
        full_environment_import_test_count=1,
        full_environment_import_passed=True,
    )
    assert not smoke.executed and smoke.unit_count == 0
    assert not smoke.formal_fitting_eligible_rows
    assert behavior.status == "partial_blocked_pending_smoke"
    assert not behavior.engineering_receipt_comparison_completed
    assert not release.released_for_formal_collection
    assert report.status == decision.state == "BLOCKED"
    assert report.reason == decision.exact_reason == BLOCK_REASON
    assert report.required_field_coverage == report.label_coverage == 0.0
    assert not decision.formal_collection_authorized
