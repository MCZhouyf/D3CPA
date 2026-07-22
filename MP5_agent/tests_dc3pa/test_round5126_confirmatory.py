from __future__ import annotations

import hashlib
import inspect
import json
import threading
from collections import Counter
from dataclasses import replace

import pytest

from dc3pa.experiments.round5124_holdout_evaluator import evaluate_locked_holdout
from dc3pa.experiments.round5126_confirmatory import (
    ASSIGNMENT_COUNT,
    FROZEN_EXECUTION_BUDGET,
    FROZEN_STRATA,
    PROTECTED_ARTIFACTS,
    REQUIRED_AUTHORIZATION_STATEMENTS,
    ArtifactComparison,
    ConfirmatoryPreflightReceipt,
    FinalConfirmatoryHoldoutRuntimeRelease,
    FreshHoldoutSeedNamespace,
    HoldoutPreflightRepairBinding,
    LockedConfirmatoryHoldoutExecutionManifest,
    PriorHoldoutEntry,
    PriorHoldoutExclusionRegistry,
    ReplacementHoldoutAuthorization,
    ReplacementHoldoutDesign,
    accepted_decision_rows,
    assert_evaluator_has_no_fitter_import,
    atomic_claim_then_read_bundle,
    consume_fresh_single_use_ledger,
    create_fresh_single_use_ledger,
    generate_fresh_assignments,
    next_confirmatory_attempt,
)


AMENDMENT = "a" * 64


def _comparisons(*, changed: str | None = None):
    result = {}
    for name in PROTECTED_ARTIFACTS:
        result[name] = ArtifactComparison(
            before_id=f"{name}-id",
            before_sha256=f"{name}-sha",
            after_id=f"{name}-id" if name != changed else f"{name}-new-id",
            after_sha256=f"{name}-sha" if name != changed else f"{name}-new-sha",
            authorized_amendment_sha256=AMENDMENT if name == changed else "",
        )
    return result


def _binding(*, changed: str | None = None):
    return HoldoutPreflightRepairBinding(
        comparison_base_sha="db72ed2" + "0" * 33,
        effective_source_sha="104e5f1" + "0" * 33,
        protected_artifacts=_comparisons(changed=changed),
        allowed_source_changes=("50-task preflight validation",),
        technical_retry_baseline_amendment_sha256=AMENDMENT,
        candidate_unchanged=True,
        activation_policy_unchanged=True,
        component_releases_unchanged=True,
        paper_memory_v5_unchanged=True,
        task_catalog_unchanged=True,
        controller_behavior_unchanged=True,
        evaluator_unchanged=True,
        prompt_bundle_unchanged=True,
        execution_budget_unchanged=True,
        only_preflight_path_or_authorized_retry_baseline_changed=True,
    ).with_id()


def _design():
    return ReplacementHoldoutDesign(
        task_pool_id="task-pool",
        task_pool_sha256="task-pool-sha",
        assignment_count=ASSIGNMENT_COUNT,
        strata=FROZEN_STRATA,
        selection_rule="one_frozen_task_per_stratum_three_seeds",
        observational_outcomes_available=False,
    ).with_id()


def _namespace(secret: bytes = b"round5126-secret"):
    return FreshHoldoutSeedNamespace(
        namespace_id="round5126-fresh",
        salt_commitment_sha256=hashlib.sha256(secret).hexdigest(),
        seed_domain_start=1_900_000_000,
        seed_domain_size=1_000_000,
        prior_domain_audit_id="disjoint-domain-audit",
    )


def _authorization(design=None, namespace=None, *, status="approved"):
    design = design or _design()
    namespace = namespace or _namespace()
    return ReplacementHoldoutAuthorization(
        approved_by="ZYF",
        approved_at="2026-07-22T00:00:00+00:00",
        approval_status=status,
        approved_source_sha="source-sha",
        preflight_repair_binding_id="binding-id",
        runtime_release_id="runtime-id",
        exclusion_registry_id="registry-id",
        design_id=design.design_id,
        namespace_id=namespace.namespace_id,
        namespace_commitment_sha256=namespace.salt_commitment_sha256,
        bound_artifact_ids={name: f"{name}-id" for name in PROTECTED_ARTIFACTS},
        bound_artifact_sha256={
            name: f"{name}-sha" for name in PROTECTED_ARTIFACTS
        },
        statements=REQUIRED_AUTHORIZATION_STATEMENTS,
    ).with_id()


def _preflight():
    item = ConfirmatoryPreflightReceipt(
        source_and_artifacts_passed=True,
        active_taskset_passed=True,
        sealed_metadata_passed=True,
        runtime_task_files_checked=50,
        formal_task_files_checked=50,
        assignments_read=False,
        assignments_decrypted=False,
        ledger_claimed=False,
        minedojo_started=False,
    )
    return replace(item, receipt_id=item.compute_receipt_id())


def _claim(ledger, reader):
    return atomic_claim_then_read_bundle(
        ledger,
        preflight=_preflight(),
        manifest_id="manifest",
        seal_id="seal",
        authorization_id="authorization",
        source_sha="source",
        candidate_sha256="candidate-sha",
        activation_policy_sha256="activation-sha",
        runtime_release_id="runtime",
        taskset_tree_sha256="taskset-tree",
        paper_memory_root_sha256="memory-root",
        claim_nonce="nonce",
        bundle_reader=reader,
    )


def test_preflight_binding_accepts_only_the_approved_retry_amendment():
    assert _binding().binding_id
    assert _binding(changed="technical_retry_policy").binding_id
    with pytest.raises(ValueError, match="protected scientific artifact"):
        _binding(changed="monotonic_fusion_candidate")


def test_runtime_release_preserves_every_frozen_artifact_and_budget():
    release = FinalConfirmatoryHoldoutRuntimeRelease(
        source_commit="source",
        preflight_repair_binding_id="binding",
        protected_artifact_ids={name: f"{name}-id" for name in PROTECTED_ARTIFACTS},
        protected_artifact_sha256={name: f"{name}-sha" for name in PROTECTED_ARTIFACTS},
        execution_budget=FROZEN_EXECUTION_BUDGET,
        memory_readonly=True,
        evaluation_chain_enabled=False,
        fusion_shadow_only=True,
        formal_memory_writes_permitted=False,
        acquisition_writes_permitted=False,
    ).with_id()
    assert release.release_id
    with pytest.raises(ValueError, match="budget changed"):
        replace(
            release,
            execution_budget={**FROZEN_EXECUTION_BUDGET, "max_explore_steps": 360},
            release_id="",
        )


def test_locked_execution_manifest_requires_clean_green_frozen_source():
    manifest = LockedConfirmatoryHoldoutExecutionManifest(
        source_commit="source",
        authorization_id="authorization",
        preflight_repair_binding_id="binding",
        runtime_release_id="runtime",
        candidate_artifact_id="candidate",
        candidate_artifact_sha256="candidate-sha",
        activation_policy_id="activation",
        activation_policy_sha256="activation-sha",
        assignment_seal_id="seal",
        ledger_id="ledger",
        paper_memory_v5_root_sha256="memory-root",
        active_taskset_catalog_sha256="catalog-sha",
        active_taskset_tree_sha256="tree-sha",
        prompt_bundle_id="prompts",
        controller_id="controller",
        evaluator_id="evaluator",
        evaluator_sha256="evaluator-sha",
        bootstrap_policy_id="bootstrap",
        technical_retry_policy_id="retry-policy",
        execution_budget=FROZEN_EXECUTION_BUDGET,
        github_actions_run_url="https://github.com/example/actions/runs/1",
        source_worktree_clean=True,
        github_actions_green=True,
        holdout_outcomes_absent=True,
    ).with_id()
    assert manifest.manifest_id
    with pytest.raises(ValueError, match="preconditions"):
        replace(manifest, github_actions_green=False, manifest_id="")


def test_prior_holdout_registry_keeps_observational_and_retired_sets_distinct():
    common = {
        "assignment_manifest_id": "manifest",
        "assignment_manifest_sha256": "manifest-sha",
        "seal_id": "seal",
        "seal_sha256": "seal-sha",
        "ledger_id": "ledger",
        "assignment_count": 15,
        "formal_activation_use_forbidden": True,
        "candidate_policy_tuning_forbidden": True,
        "assignment_reuse_forbidden": True,
        "ledger_reopen_forbidden": True,
    }
    registry = PriorHoldoutExclusionRegistry(
        observational=PriorHoldoutEntry(
            set_id="observational",
            status="observational_only",
            ledger_state="claimed",
            outcomes_observed=True,
            **common,
        ),
        failed_prelaunch=PriorHoldoutEntry(
            set_id="failed-prelaunch",
            status="permanently_retired",
            ledger_state="failed_prelaunch",
            outcomes_observed=False,
            **common,
        ),
    ).with_id()
    assert registry.registry_id
    assert registry.observational.set_id != registry.failed_prelaunch.set_id


def test_draft_authorization_cannot_be_constructed_or_generate_assignments():
    with pytest.raises(ValueError, match="explicit ZYF approval"):
        _authorization(status="DRAFT")
    authorization = replace(_authorization(), authorization_id="")
    with pytest.raises(ValueError, match="hash-bound author authorization"):
        generate_fresh_assignments(
            authorization=authorization,
            design=_design(),
            namespace=_namespace(),
            namespace_secret=b"round5126-secret",
            task_by_stratum={name: f"task-{name}" for name in FROZEN_STRATA},
            excluded_task_seed_pairs=frozenset(),
            excluded_seed_values=frozenset(),
        )


def test_generator_has_no_outcome_input_and_preserves_count_strata_and_order():
    assert not any(
        "outcome" in name or "label" in name
        for name in inspect.signature(generate_fresh_assignments).parameters
    )
    secret = b"round5126-secret"
    design = _design()
    namespace = _namespace(secret)
    authorization = _authorization(design, namespace)
    kwargs = {
        "authorization": authorization,
        "design": design,
        "namespace": namespace,
        "namespace_secret": secret,
        "task_by_stratum": {name: f"task-{name}" for name in FROZEN_STRATA},
        "excluded_task_seed_pairs": frozenset(),
        "excluded_seed_values": frozenset({1, 2, 3}),
    }
    first = generate_fresh_assignments(**kwargs)
    second = generate_fresh_assignments(**kwargs)
    assert first == second
    assert len(first) == ASSIGNMENT_COUNT
    assert Counter(item["difficulty"] for item in first) == FROZEN_STRATA
    assert [item["sequence_index"] for item in first] == list(range(15))
    assert len({(item["task"], item["seed"]) for item in first}) == 15


def test_namespace_overlap_and_pair_overlap_fail_closed():
    secret = b"round5126-secret"
    design = _design()
    namespace = _namespace(secret)
    authorization = _authorization(design, namespace)
    base = dict(
        authorization=authorization,
        design=design,
        namespace=namespace,
        namespace_secret=secret,
        task_by_stratum={name: f"task-{name}" for name in FROZEN_STRATA},
        excluded_task_seed_pairs=frozenset(),
        excluded_seed_values=frozenset(),
    )
    assignments = generate_fresh_assignments(**base)
    with pytest.raises(ValueError, match="historical seed domain"):
        generate_fresh_assignments(
            **{**base, "excluded_seed_values": frozenset({1_900_000_000})}
        )
    pair = (assignments[0]["task"], assignments[0]["seed"])
    with pytest.raises(ValueError, match="prior task-seed pair"):
        generate_fresh_assignments(
            **{**base, "excluded_task_seed_pairs": frozenset({pair})}
        )


def test_claim_is_persisted_before_read_and_bad_binding_never_reads(tmp_path):
    ledger = tmp_path / "ledger.json"
    create_fresh_single_use_ledger(
        ledger,
        manifest_id="manifest",
        seal_id="seal",
        authorization_id="authorization",
    )
    read = False

    def reader():
        nonlocal read
        read = True
        assert json.loads(ledger.read_text(encoding="utf-8"))["state"] == "claimed"
        return "bundle"

    with pytest.raises(ValueError, match="binding mismatch"):
        atomic_claim_then_read_bundle(
            ledger,
            preflight=_preflight(),
            manifest_id="wrong",
            seal_id="seal",
            authorization_id="authorization",
            source_sha="source",
            candidate_sha256="candidate-sha",
            activation_policy_sha256="activation-sha",
            runtime_release_id="runtime",
            taskset_tree_sha256="taskset-tree",
            paper_memory_root_sha256="memory-root",
            claim_nonce="nonce",
            bundle_reader=reader,
        )
    assert not read
    assert json.loads(ledger.read_text(encoding="utf-8"))["state"] == "sealed_unopened"
    claimed, bundle = _claim(ledger, reader)
    assert claimed["claim_count"] == 1
    assert bundle == "bundle"


def test_concurrent_double_claim_and_reopen_after_consumption_are_rejected(tmp_path):
    ledger = tmp_path / "ledger.json"
    create_fresh_single_use_ledger(
        ledger,
        manifest_id="manifest",
        seal_id="seal",
        authorization_id="authorization",
    )
    barrier = threading.Barrier(2)
    results = []

    def contender():
        barrier.wait()
        try:
            _claim(ledger, lambda: "bundle")
            results.append("claimed")
        except ValueError:
            results.append("rejected")

    threads = [threading.Thread(target=contender) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert Counter(results) == {"claimed": 1, "rejected": 1}

    consumed = consume_fresh_single_use_ledger(
        ledger,
        campaign_summary_sha256="summary-sha",
        assignment_count=15,
        pending_count=0,
        unresolved_technical_failures=0,
        retry_limit_violations=0,
        unclassified_technical_failures=0,
        failed_attempt_decision_contamination=0,
        duplicate_accepted_decision_ids=0,
        memory_writes=0,
        acquisition_writes=0,
        evaluation_chain_calls=0,
        one_runtime_profile=True,
        one_paper_memory_v5_root=True,
    )
    assert consumed["state"] == "consumed"
    with pytest.raises(ValueError, match="already been opened"):
        _claim(ledger, lambda: "bundle")


def test_frozen_attempt_rules_and_quarantine_filter():
    assert next_confirmatory_attempt(
        completed_attempt_indices=(),
        last_status=None,
        last_failure_category=None,
    ) == 0
    assert next_confirmatory_attempt(
        completed_attempt_indices=(0,),
        last_status="technical_failure",
        last_failure_category="provider_transport_failure",
    ) == 1
    with pytest.raises(ValueError, match="Scientific completion is final"):
        next_confirmatory_attempt(
            completed_attempt_indices=(0,),
            last_status="completed_scientific_failure",
            last_failure_category=None,
        )
    with pytest.raises(ValueError, match="Unclassified technical"):
        next_confirmatory_attempt(
            completed_attempt_indices=(0,),
            last_status="technical_failure",
            last_failure_category="unknown",
        )
    with pytest.raises(RuntimeError, match="Attempt 3"):
        next_confirmatory_attempt(
            completed_attempt_indices=(0, 1, 2),
            last_status="technical_failure",
            last_failure_category="provider_transport_failure",
        )
    rows = (
        {"attempt_id": "failed", "attempt_disposition": "quarantined_technical"},
        {"attempt_id": "accepted", "attempt_disposition": "accepted_scientific"},
    )
    assert accepted_decision_rows(rows, accepted_attempt_id="accepted") == (rows[1],)


def test_locked_evaluator_is_physically_isolated_from_fitting_and_observations():
    assert_evaluator_has_no_fitter_import(evaluate_locked_holdout)
    source = inspect.getsource(inspect.getmodule(evaluate_locked_holdout))
    assert "observational" not in source
    assert "dev_train" not in source
    assert "dev_tune" not in source
