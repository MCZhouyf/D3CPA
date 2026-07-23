from __future__ import annotations

import inspect

import pytest

from dc3pa.experiments import round513_audit as audit


def _row(feature: str = "h", available: int = 0):
    return audit.FeatureAvailabilityRow(
        feature=feature,
        train_available_count=available,
        train_total=10,
        tune_available_count=available,
        tune_total=10,
        task_coverage_count=available,
        task_total=10,
        difficulty_coverage_count=min(available, 5),
        difficulty_total=5,
        missing_reason="missing" if available < 10 else "",
        reconstructable_without_new_llm=True,
        reconstructable_without_minedojo=True,
        required_new_collection=available < 10,
    )


def test_feature_matrix_reports_rates_and_rejects_duplicate_features():
    row = _row(available=5)
    assert row.to_dict()["train_available_rate"] == 0.5
    with pytest.raises(ValueError, match="rows are invalid"):
        audit.FeatureAvailabilityMatrix(
            source_commit="source",
            lineage_audit_id="lineage",
            rows=(row, row),
            no_new_llm_called=True,
            no_minedojo_started=True,
        )


def test_missing_registry_forbids_manual_llm_and_holdout_backfill():
    registry = audit.MissingEvidenceRegistry(
        source_commit="source",
        matrix_id="matrix",
        missing={"same_generation_confidence": "separate provider call"},
        manual_backfill_forbidden=True,
        llm_backfill_forbidden=True,
        future_holdout_backfill_forbidden=True,
    ).with_id()
    assert registry.registry_id


def test_cdt_unidentifiable_audit_cannot_invent_counterfactuals_or_parameters():
    values = dict(
        source_commit="source",
        evaluation_called_rows=0,
        original_action_rows=0,
        revised_action_rows=0,
        action_changed_rows=0,
        revised_execution_result_rows=0,
        original_execution_result_rows=0,
        matched_state_replay_pairs=0,
        evaluation_cost_rows=0,
        downstream_cost_rows=0,
        terminal_failure_rows=0,
        rho_path_a_evidence_count=0,
        rho_path_b_evidence_count=0,
        c_eval_evidence_count=0,
        c_fp_evidence_count=0,
        l_fail_compute_evidence_count=0,
        l_fail_terminal_evidence_count=0,
        decision="CDT not identifiable from historical logs",
    )
    item = audit.CDTIdentifiabilityAudit(**values).with_id()
    assert not item.parameters_estimated
    with pytest.raises(ValueError, match="forbidden evidence"):
        audit.CDTIdentifiabilityAudit(**values, counterfactual_outcomes_inferred=True)


def test_decision_d_requires_new_collection_and_opens_no_protected_phase():
    decision = audit.Round513HistoricalDataDecision(
        source_commit="source",
        compatibility_audit_id="audit",
        decision="D",
        exact_reasons=("same-generation confidence is absent",),
        chrm_reconstruction_permitted=False,
        cdt_historical_identification_permitted=False,
        targeted_new_development_collection_required=True,
    ).with_id()
    assert decision.targeted_new_development_collection_required
    assert not decision.holdout_accessed
    assert not decision.model_fitted


def test_historical_auditor_has_no_provider_minedojo_or_fitting_dependency():
    source = inspect.getsource(audit)
    assert "from openai" not in source
    assert "import minedojo" not in source
    assert "fit_monotonic" not in source
    signature = inspect.signature(audit.build_historical_compatibility_audit)
    assert tuple(signature.parameters) == ("inputs",)
