import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from dc3pa.experiments.round513e2h import (
    ADAPTER_VERSION,
    AtomicDecisionStoreV4_1_2_R1,
    CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2_R1,
    CHRMLiteEngineeringSmokeRuntimeReleaseV4_1_2_R1,
    ContractCompatibilityEntry,
    PolicyCandidate,
    ProcessCleanupPolicyV4_1_2_R1,
    ProcessCleanupPolicyProvenanceAudit,
    Round513E2AuthorizationSupersessionDecision,
    Round513E2ContractCompatibilityReleaseR1,
    SmokeAssignmentScientificPayloadEquivalenceAudit,
    SmokeAssignmentV4_1_2_R1,
    TechnicalRetryAndCleanupDecisionInput,
    TechnicalRetryPolicyV4_1_2_R1,
    TechnicalRetryPolicyProvenanceAudit,
    TrackERunBindingV4_1_2_R1,
    TrackEExecutionManifestV4_1_2_R1,
    canonical_sha256,
    dataclass_schema_id,
    file_sha256,
    legacy_scientific_payload,
    load_versioned_contract,
    ordered_scientific_payload_root,
    require_execution_manifest_prerequisites,
    validate_all_before_environment_launch,
    validate_track_e_r1_artifacts,
)


EXTERNAL = (
    Path(os.environ["DC3PA_EXTERNAL_ROOT"])
    if "DC3PA_EXTERNAL_ROOT" in os.environ
    else Path(Path.cwd().anchor) / "external" / "dc3pa"
)
V41 = EXTERNAL / "round513cd/contracts-7e6e03f"
V412 = EXTERNAL / "round513e1r/1a98c30/authoritative-smoke-prep/v4_1_2_contracts"
SMOKE = EXTERNAL / "round513e1r/1a98c30/authoritative-smoke-prep"
SOURCE = "1a98c30a53f480ee3d63b4c1b1d9662e91e5cea0"


def _payload(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _synthetic_retrieval(version):
    payload = {
        "compatible_rule": "same canonical action signature",
        "full_library_max_shortcut_permitted": False,
        "gamma_policy": "external_authorized",
        "incompatible_rule": "different canonical action signature",
        "mineclip_policy_id": "1" * 64,
        "minimum_count_per_side": 3,
        "online_llm_calls": 0,
        "paper_memory_v5_release_id": "2" * 64,
        "scene_exemplar_release_id": "3" * 64,
        "schema_version": 1,
        "source_commit": "4" * 40,
        "tie_break": "score_desc_exemplar_id_asc",
        "top_k_per_side": 3,
        "undercovered_state": "unknown",
    }
    if version != "4.1":
        payload["contract_version"] = version
    payload["policy_id"] = canonical_sha256(payload)
    return payload


@pytest.mark.parametrize("version", ["4.1", "4.1.2"])
def test_synthetic_versioned_loader_validates_raw_before_normalizing(tmp_path, version):
    payload = _synthetic_retrieval(version)
    path = tmp_path / f"retrieval-{version}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    adapted = load_versioned_contract(
        path,
        contract_type="bilateral_retrieval_policy",
        expected_contract_id=payload["policy_id"],
        expected_file_sha256=file_sha256(path),
    )
    assert adapted.contract_version == version
    assert adapted.raw_contract_payload == payload
    assert "contract_version" not in adapted.normalized_runtime_view
    tampered = dict(payload, unknown=True)
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="fields do not match"):
        load_versioned_contract(
            path,
            contract_type="bilateral_retrieval_policy",
            expected_contract_id=payload["policy_id"],
            expected_file_sha256=file_sha256(path),
        )


@pytest.mark.parametrize(
    "path,contract_type,id_field,version",
    [
        (V41 / "chrmlite_bilateral_retrieval_policy_v4_1.json", "bilateral_retrieval_policy", "policy_id", "4.1"),
        (V41 / "chrmlite_decision_record_schema_v4_1.json", "decision_record_schema", "schema_id", "4.1"),
        (V412 / "chrmlite_bilateral_retrieval_policy_v4_1_2.json", "bilateral_retrieval_policy", "policy_id", "4.1.2"),
        (V412 / "chrmlite_decision_record_schema_v4_1_2.json", "decision_record_schema", "schema_id", "4.1.2"),
        (V412 / "chrmlite_instrumentation_release_v4_1_2.json", "instrumentation_release", "release_id", "4.1.2"),
    ],
)
@pytest.mark.minedojo
def test_versioned_contract_round_trip_preserves_raw_identity(path, contract_type, id_field, version):
    payload = _payload(path)
    adapted = load_versioned_contract(
        path,
        contract_type=contract_type,
        expected_contract_id=payload[id_field],
        expected_file_sha256=file_sha256(path),
    )
    assert adapted.contract_version == version
    assert adapted.raw_contract_payload == payload
    assert adapted.raw_contract_id == payload[id_field]
    assert adapted.raw_file_sha256 == file_sha256(path)
    assert adapted.authoring_source_commit == payload["source_commit"]
    if version == "4.1.2":
        assert adapted.raw_contract_payload["contract_version"] == "4.1.2"
        assert "contract_version" not in adapted.normalized_runtime_view
    assert adapted.adapter_id == adapted.compute_id()


@pytest.mark.minedojo
def test_raw_hash_is_validated_before_adaptation(tmp_path):
    original = V412 / "chrmlite_bilateral_retrieval_policy_v4_1_2.json"
    payload = _payload(original)
    payload.pop("contract_version")
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical ID mismatch"):
        load_versioned_contract(
            changed,
            contract_type="bilateral_retrieval_policy",
            expected_contract_id=payload["policy_id"],
            expected_file_sha256=file_sha256(changed),
        )


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda p: p.update(contract_version="9.9"), "Unsupported contract version"),
        (lambda p: p.update(unapproved_field=True), "fields do not match"),
    ],
)
@pytest.mark.minedojo
def test_unknown_version_and_fields_fail_closed(tmp_path, mutation, error):
    payload = _payload(V412 / "chrmlite_bilateral_retrieval_policy_v4_1_2.json")
    mutation(payload)
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        load_versioned_contract(
            path,
            contract_type="bilateral_retrieval_policy",
            expected_contract_id=payload["policy_id"],
            expected_file_sha256=file_sha256(path),
        )


@pytest.mark.minedojo
def test_adapter_is_deterministic_and_authoring_source_is_not_execution_source():
    path = V41 / "chrmlite_bilateral_retrieval_policy_v4_1.json"
    payload = _payload(path)
    first = load_versioned_contract(path, contract_type="bilateral_retrieval_policy", expected_contract_id=payload["policy_id"], expected_file_sha256=file_sha256(path))
    second = load_versioned_contract(path, contract_type="bilateral_retrieval_policy", expected_contract_id=payload["policy_id"], expected_file_sha256=file_sha256(path))
    release = Round513E2ContractCompatibilityReleaseR1(
        source_commit=SOURCE,
        scientific_method_version="V4.1.2",
        runtime_binding_revision="R1",
        entries=(ContractCompatibilityEntry(
            contract_type=first.contract_type,
            filename=path.name,
            contract_id=first.raw_contract_id,
            file_sha256=first.raw_file_sha256,
            contract_version=first.contract_version,
            authoring_source_commit=first.authoring_source_commit,
            runtime_adapter_version=ADAPTER_VERSION,
            allowed_execution_source_commits=(SOURCE,),
        ),),
    ).with_id()
    assert first == second
    assert first.authoring_source_commit != SOURCE
    release.require_compatible(first, SOURCE)
    with pytest.raises(PermissionError):
        release.require_compatible(first, "0" * 40)


def _binding(**changes):
    values = {
        name: "a" * 64
        for name in TrackERunBindingV4_1_2_R1.__dataclass_fields__
        if name not in {
            "schema_version", "binding_id", "engineering_only",
            "scientific_method_version", "runtime_binding_revision",
        }
    }
    values.update(
        execution_source_commit=SOURCE,
        gamma_candidate="0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f",
        gamma_cov_text="1.0",
        gamma_minus_text="-0.01040883",
        gamma_plus_text="0.00744657",
        collection_mode="chrmlite_estimation_collection_v41",
        output_root="external-output-token",
    )
    values.update(changes)
    return TrackERunBindingV4_1_2_R1(**values).with_id()


def test_run_binding_requires_every_field_and_exact_gamma_strings():
    binding = _binding()
    assert binding.binding_id == binding.compute_id()
    with pytest.raises(TypeError):
        values = binding.payload_without_id()
        values.pop("controller_id")
        TrackERunBindingV4_1_2_R1(**values)
    with pytest.raises(ValueError, match="exact decimal"):
        _binding(gamma_minus_text="-1.040883e-2")


@pytest.mark.minedojo
def test_full_r1_preflight_validates_lineage_and_controller_evaluator_budget(tmp_path):
    paths = {
        "planner_schema": V41 / "chrmlite_planner_output_schema_v4_1.json",
        "rule_registry": V41 / "chrmlite_rule_type_registry_v4_1.json",
        "bilateral_retrieval_policy": V412 / "chrmlite_bilateral_retrieval_policy_v4_1_2.json",
        "decision_record_schema": V412 / "chrmlite_decision_record_schema_v4_1_2.json",
        "step_outcome_registry": V41 / "chrmlite_step_outcome_registry_v4_1.json",
        "instrumentation_release": V412 / "chrmlite_instrumentation_release_v4_1_2.json",
        "support_policy": V41 / "chrmlite_support_and_degradation_policy.json",
    }
    id_fields = {
        "planner_schema": "schema_id", "rule_registry": "registry_id",
        "bilateral_retrieval_policy": "policy_id", "decision_record_schema": "schema_id",
        "step_outcome_registry": "registry_id", "instrumentation_release": "release_id",
        "support_policy": "policy_id",
    }
    adapters = {
        name: load_versioned_contract(
            path,
            contract_type=name,
            expected_contract_id=_payload(path)[id_fields[name]],
            expected_file_sha256=file_sha256(path),
        )
        for name, path in paths.items()
    }
    compatibility = Round513E2ContractCompatibilityReleaseR1(
        source_commit=SOURCE,
        scientific_method_version="V4.1.2",
        runtime_binding_revision="R1",
        entries=tuple(
            ContractCompatibilityEntry(
                contract_type=name,
                filename=paths[name].name,
                contract_id=item.raw_contract_id,
                file_sha256=item.raw_file_sha256,
                contract_version=item.contract_version,
                authoring_source_commit=item.authoring_source_commit,
                runtime_adapter_version=ADAPTER_VERSION,
                allowed_execution_source_commits=(SOURCE,),
            )
            for name, item in adapters.items()
        ),
    ).with_id()
    runtime = CHRMLiteEngineeringSmokeRuntimeReleaseV4_1_2_R1(
        source_commit=SOURCE,
        compatibility_release_id=compatibility.release_id,
        technical_retry_policy_id="a" * 64,
        process_cleanup_policy_id="a" * 64,
        source_hardening_audit_id="5" * 64,
        run_binding_schema_id=dataclass_schema_id(
            TrackERunBindingV4_1_2_R1,
            invariants={
                "scientific_method_version": "V4.1.2",
                "runtime_binding_revision": "R1",
                "engineering_only": True,
                "gamma_candidate": "B",
            },
        ),
        assignment_schema_id="2" * 64,
        decision_store_revision="orthogonal-disposition-r1",
        preflight_before_environment=True,
        controller_evaluator_budget_validation=True,
    ).with_id()
    outcome = adapters["step_outcome_registry"].raw_contract_payload
    output = str((tmp_path / "output").resolve())
    binding = _binding(
        compatibility_release_id=compatibility.release_id,
        runtime_release_id=runtime.release_id,
        planner_schema_id=adapters["planner_schema"].raw_contract_id,
        rule_registry_id=adapters["rule_registry"].raw_contract_id,
        bilateral_policy_id=adapters["bilateral_retrieval_policy"].raw_contract_id,
        decision_record_schema_id=adapters["decision_record_schema"].raw_contract_id,
        step_outcome_registry_id=adapters["step_outcome_registry"].raw_contract_id,
        instrumentation_release_id=adapters["instrumentation_release"].raw_contract_id,
        controller_id=outcome["controller_contract_id"],
        evaluator_id=outcome["evaluator_contract_id"],
        budget_profile_id=outcome["execution_budget_profile_id"],
        output_root=output,
    )
    manifest = TrackEExecutionManifestV4_1_2_R1(
        execution_source_commit=binding.execution_source_commit,
        run_binding_id=binding.binding_id,
        compatibility_release_id=binding.compatibility_release_id,
        runtime_release_id=binding.runtime_release_id,
        authorization_receipt_id=binding.authorization_receipt_id,
        authorization_input_id=binding.authorization_input_id,
        authorization_input_file_sha256=binding.authorization_input_file_sha256,
        approval_statement_sha256=binding.approval_statement_sha256,
        smoke_assignment_seal_id=binding.smoke_assignment_seal_id,
        ordered_assignment_root=binding.ordered_assignment_root,
        technical_retry_policy_id=binding.technical_retry_policy_id,
        process_cleanup_policy_id=binding.process_cleanup_policy_id,
        output_root=binding.output_root,
        gamma_candidate=binding.gamma_candidate,
        gamma_cov_text=binding.gamma_cov_text,
        gamma_minus_text=binding.gamma_minus_text,
        gamma_plus_text=binding.gamma_plus_text,
        environment_execution_permitted=True,
    ).with_id()
    validate_track_e_r1_artifacts(
        binding=binding,
        compatibility=compatibility,
        runtime_release=runtime,
        execution_manifest=manifest,
        adapters=adapters,
        cli_output_root=output,
    )
    bad_binding = _binding(
        **{
            **binding.payload_without_id(),
            "controller_id": "f" * 64,
        }
    )
    with pytest.raises(ValueError, match="Controller/Evaluator/Budget"):
        validate_track_e_r1_artifacts(
            binding=bad_binding,
            compatibility=compatibility,
            runtime_release=runtime,
            execution_manifest=manifest,
            adapters=adapters,
            cli_output_root=output,
        )


def test_old_authorization_supersession_is_pre_execution_only():
    item = Round513E2AuthorizationSupersessionDecision(
        source_commit=SOURCE,
        old_authorization_input_id="1" * 64,
        old_authorization_input_file_sha256="2" * 64,
        old_approval_statement_sha256="3" * 64,
        old_assignment_seal_id="4" * 64,
        old_execution_source_sha=SOURCE,
    ).with_id()
    assert item.status == "superseded_before_execution_due_to_source_hardening"
    with pytest.raises(ValueError):
        replace(item, execution_started=True, decision_id="")


@pytest.mark.minedojo
def test_nine_assignments_preserve_scientific_payload_and_make_all_eligibility_explicit():
    old = _payload(SMOKE / "chrmlite_engineering_smoke_assignments_v4_1_2.json")
    new = [SmokeAssignmentV4_1_2_R1.from_legacy(item, source_commit=SOURCE) for item in old["assignments"]]
    old_root = ordered_scientific_payload_root(old["assignments"])
    new_root = canonical_sha256([
        {"order": index, **item.scientific_payload()} for index, item in enumerate(new)
    ])
    assert len(new) == 9 and old_root == new_root
    for item in new:
        payload = item.to_dict()
        assert payload["engineering_only"] is True
        for field in (
            "formal_fitting_eligible", "channel_calibration_eligible",
            "CHRM_fitting_eligible", "CDT_identification_eligible",
            "holdout_eligible", "final_evaluation_eligible",
        ):
            assert field in payload and payload[field] is False
    audit = SmokeAssignmentScientificPayloadEquivalenceAudit(
        source_commit=SOURCE,
        old_assignments_id=old["assignments_id"],
        new_assignments_id=canonical_sha256([item.to_dict() for item in new]),
        old_ordered_scientific_payload_root=old_root,
        new_ordered_scientific_payload_root=new_root,
        assignment_count=9,
        tasks_changed=0,
        seeds_changed=0,
        order_changed=0,
        status="EQUIVALENT",
    ).with_id()
    assert audit.audit_id


@dataclass(frozen=True)
class _Pre:
    record_id: str

    def to_dict(self):
        return {"record_id": self.record_id}


@dataclass(frozen=True)
class _Record:
    pre: _Pre
    state: str
    engineering_only: bool = True
    formal_fitting_eligible: bool = False
    record_hash: str = ""

    @property
    def label(self):
        return SimpleNamespace(state=self.state)

    def compute_hash(self):
        return canonical_sha256({"record_id": self.pre.record_id, "state": self.state})

    def with_hash(self):
        return replace(self, record_hash=self.compute_hash())

    def to_dict(self):
        return {
            "record_id": self.pre.record_id,
            "state": self.state,
            "engineering_only": self.engineering_only,
            "formal_fitting_eligible": self.formal_fitting_eligible,
            "record_hash": self.record_hash or self.compute_hash(),
        }


@pytest.mark.parametrize(
    "state,disposition",
    [
        ("success", "accepted_scientific"),
        ("scientific_failure", "accepted_scientific"),
        ("ambiguous_unobservable", "audit_only_ambiguous"),
        ("technical_failure", "technical_quarantine"),
    ],
)
def test_decision_store_has_orthogonal_dispositions_and_is_idempotent(tmp_path, state, disposition):
    store = AtomicDecisionStoreV4_1_2_R1(tmp_path / state)
    pre = _Pre(canonical_sha256({"state": state}))
    assert store.persist_pre(pre) == "created"
    record = _Record(pre, state)
    first = store.join_post(record)
    second = store.join_post(record)
    assert first == second and first.parent.name == disposition
    payload = _payload(first)
    assert payload["record_disposition"] == disposition
    assert payload["engineering_only"] is True
    assert payload["formal_fitting_eligible"] is False
    assert store.should_execute(pre.record_id) is False


def test_execution_manifest_prerequisites_and_preflight_block_environment_launch():
    with pytest.raises(ValueError, match="authorization_receipt_id"):
        require_execution_manifest_prerequisites(
            authorization_receipt_id="",
            technical_retry_policy_id="",
            process_cleanup_policy_id="",
        )
    launches = []
    with pytest.raises(ValueError, match="blocked"):
        validate_all_before_environment_launch(
            (lambda: (_ for _ in ()).throw(ValueError("blocked")),),
            lambda: launches.append(True),
        )
    assert launches == []


def test_stage6_r1_preflight_rejects_incomplete_release_set_before_legacy_import(
    monkeypatch, tmp_path
):
    import scripts_dc3pa.stage6_run_minecraft as launcher

    task = tmp_path / "task.json"
    task.write_text(json.dumps([{"task": "log", "quantity": 1}]), encoding="utf-8")
    binding = tmp_path / "binding.json"
    binding.write_text(json.dumps(_binding(task="log", terminal_task="log").to_dict()), encoding="utf-8")
    imported = []
    monkeypatch.setattr(launcher.importlib, "import_module", lambda name: imported.append(name))
    with pytest.raises(SystemExit, match="2"):
        launcher.main([
            "--mode", "chrmlite_estimation_collection_v41",
            "--openai_key", "test-key", "--gpt_model_name", "test-model",
            "--task", str(task),
            "--round513-track-e-binding", str(binding),
            "--round513-contract-root", str(tmp_path / "contracts"),
            "--round513-track-e-output-root", str(tmp_path / "output"),
        ])
    assert imported == []


def test_incomplete_policy_provenance_requires_author_decision():
    candidate = PolicyCandidate(
        candidate_id="retry-v1",
        source_scope="Round 5.10 acquisition",
        source_file_sha256="1" * 64,
        completeness="incomplete_for_E2",
        scientific_validity_impact="bounded technical retries but no E2 cleanup binding",
        engineering_cost="two retries per entry",
    )
    retry = TechnicalRetryPolicyProvenanceAudit(
        source_commit=SOURCE,
        candidates=(candidate,),
        unique_complete_forward_policy_found=False,
        missing_required_fields=("total_max_attempts", "backoff", "cleanup_policy_id"),
        conclusion="AUTHOR_DECISION_REQUIRED",
    ).with_id()
    cleanup = ProcessCleanupPolicyProvenanceAudit(
        source_commit=SOURCE,
        candidates=(candidate,),
        unique_complete_forward_policy_found=False,
        missing_required_fields=("ports", "locks", "sessions", "unrelated_process_safety"),
        unrelated_process_kill_risk=True,
        conclusion="AUTHOR_DECISION_REQUIRED",
    ).with_id()
    decision = TechnicalRetryAndCleanupDecisionInput(
        source_commit=SOURCE,
        retry_provenance_audit_id=retry.audit_id,
        cleanup_provenance_audit_id=cleanup.audit_id,
        retry_candidates=({"candidate": "A", "maximum_retries": 0},),
        cleanup_candidates=({"candidate": "scoped_cleanup"},),
        required_author_fields=("maximum_attempts_per_category", "total_max_attempts", "backoff", "cleanup_scope"),
    ).with_id()
    assert decision.status == "pending_ZYF_decision"
    assert decision.minedojo_execution_permitted is False


def test_author_approved_retry_and_cleanup_policies_are_exact_and_fail_closed():
    retry = TechnicalRetryPolicyV4_1_2_R1(
        source_commit=SOURCE,
        decision_input_id="1" * 64,
        decision_input_file_sha256="2" * 64,
        approval_statement_sha256="3" * 64,
        retry_candidate="T1_one_retry",
        allowed_technical_failure_categories=(
            "environment_start_failure", "seed_application_failure",
            "provider_transport_failure", "provider_empty_response",
        ),
        maximum_attempts_per_technical_category=2,
        total_maximum_attempts=2,
        backoff_seconds=30,
        scientific_success_retries=0,
        scientific_failure_retries=0,
        pre_action_proof_required=True,
        attempt_isolation_required=True,
        technical_partial_record_disposition="technical_quarantine",
        unclassified_technical_failure_policy="stop_immediately",
    ).with_id()
    cleanup = ProcessCleanupPolicyV4_1_2_R1(
        source_commit=SOURCE,
        decision_input_id="1" * 64,
        decision_input_file_sha256="2" * 64,
        approval_statement_sha256="3" * 64,
        cleanup_candidate="C1_scoped_process_group_cleanup",
        cleanup_grace_seconds=20,
        campaign_owned_ports=("ledger ports",),
        campaign_owned_lock_patterns=("ledger locks",),
        campaign_owned_display_sessions=("ledger displays",),
        required_target_checks=(
            "MineDojo", "Minecraft", "Mineflayer", "bridge",
            "ports", "lock_files", "display_sessions",
        ),
        launch_ownership_ledger_required=True,
        unrelated_process_kill_permitted=False,
        residual_process_policy="stop_if_campaign_owned_residual_remains",
        output_directory_policy="exclusive_per_attempt_then_atomic_disposition",
    ).with_id()
    assert retry.policy_id and cleanup.policy_id
    with pytest.raises(ValueError, match="Scientific outcomes"):
        replace(retry, scientific_failure_retries=1, policy_id="")
    with pytest.raises(ValueError, match="non-invasive"):
        replace(cleanup, unrelated_process_kill_permitted=True, policy_id="")


def test_pending_r1_authorization_cannot_open_execution_boundary():
    excluded = {
        "schema_version", "authorization_input_id", "declarations",
        "reauthorization_status", "minedojo_execution_permitted",
        "formal_development_permitted", "holdout_final_round6_permitted",
        "approved_by", "gamma_cov_text", "gamma_minus_text", "gamma_plus_text",
    }
    values = {
        name: "1" * 64
        for name in CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2_R1.__dataclass_fields__
        if name not in excluded
    }
    values.update(
        gamma_candidate="0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f",
        gamma_cov_text="1.0",
        gamma_minus_text="-0.01040883",
        gamma_plus_text="0.00744657",
        declarations=tuple(f"declaration-{index}" for index in range(12)),
    )
    authorization = CHRMLiteEngineeringSmokeAuthorizationInputV4_1_2_R1(
        **values
    ).with_id()
    assert authorization.reauthorization_status == "pending"
    with pytest.raises(ValueError, match="forbidden execution"):
        replace(authorization, minedojo_execution_permitted=True, authorization_input_id="")


def test_policy_approval_rejects_unresolved_template():
    from scripts_dc3pa.freeze_round513e2h_reauthorization import (
        _validate_policy_approval,
    )

    with pytest.raises(ValueError, match="unresolved placeholders"):
        _validate_policy_approval(
            "retry_candidate=<T0_no_retry|T1_one_retry>; approved_by=ZYF"
        )
