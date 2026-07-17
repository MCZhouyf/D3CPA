from dc3pa.experiments.development_analysis_policy import Round511AnalysisPolicy
from dc3pa.experiments.environment_parameter_selection import EnvironmentCandidate


def test_analysis_policy_is_frozen_before_collection_and_opens_no_holdout():
    candidate = EnvironmentCandidate(
        top_k=3,
        minimum_similarity=0.4,
        minimum_coverage=0.3,
        mismatch_compatibility_threshold=0.3,
        match_compatibility_threshold=0.7,
    ).with_id()
    policy = Round511AnalysisPolicy(
        policy_name="round511",
        confidence_levels=("very_low","low","medium","high","very_high"),
        confidence_alpha=1.0,
        confidence_method="symmetric_laplace_then_weighted_pav",
        environment_alpha=1.0,
        environment_candidates=(candidate,),
        environment_selection_objective=(
            "min_tune_brier_then_logloss_then_unknown_rate_then_id"
        ),
        environment_top_k=3,
        fusion_feature_order=(
            "knowledge_coverage",
            "knowledge_unknown",
            "confidence_probability",
            "environment_probability",
        ),
        fusion_fitting_permitted=False,
        holdout_use_permitted=False,
        final_evaluation_use_permitted=False,
        outcome_adaptive_changes_permitted=False,
        policy_frozen_before_collection=True,
    ).with_id()
    assert policy.policy_id
    assert not policy.holdout_use_permitted
