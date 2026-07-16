from dataclasses import replace

from dc3pa.experiments.formal_bootstrap_approval import (
    FormalBootstrapApprovalBinding,
    sha256_file,
    validate_formal_bootstrap_blueprint,
)
from dc3pa.experiments.formal_bootstrap_authorization import ZYF_APPROVAL_SHA256
from tests_dc3pa.round56_helpers import make_blueprint


def _binding(blueprint, controller, evaluator):
    return FormalBootstrapApprovalBinding(
        binding_name="formal-bootstrap",
        source_commit=blueprint.source_commit,
        blueprint_id=blueprint.blueprint_id,
        approved_blueprint_content_sha256=blueprint.content_sha256_before_approval(),
        zyf_approval_sha256=ZYF_APPROVAL_SHA256,
        formal_log_bootstrap_policy_id="policy",
        formal_bootstrap_amendment_id="amendment",
        previous_preacquisition_gate_id=(
            "27f2bc9cd18a33c21b68fbd6a85cfdf8e7560005c63319381c1debcaa9f34a4d"
        ),
        final_taskset_release_id="taskset",
        semantic_migration_report_id="migration",
        controller_source_sha256=sha256_file(controller),
        evaluator_source_sha256=sha256_file(evaluator),
        task_catalog_sha256="catalog",
        final_seeds_sha256="seeds",
        prompt_hashes=blueprint.prompt_hashes,
        requested_model="gpt-5.1",
        returned_identity_policy="record_and_require_epoch_stability",
        requested_returned_equality_required=False,
        all_formal_methods_use_bootstrap=True,
        all_formal_scopes_use_bootstrap=True,
        memory_records_bootstrap_metadata=True,
        development_records_bootstrap_metadata=True,
        final_results_report_natural_and_assisted_separately=True,
        prompts_changed=False,
        controller_success_logic_changed=False,
        evaluator_success_logic_changed=False,
        task_catalog_changed=False,
        final_seeds_changed=False,
        holdout_opened=False,
    ).with_id()


def test_formal_blueprint_validation_binds_runtime_sources(tmp_path):
    controller = tmp_path / "controller.py"
    evaluator = tmp_path / "evaluator.py"
    controller.write_text("controller-v1\n", encoding="utf-8")
    evaluator.write_text("evaluator-v1\n", encoding="utf-8")
    blueprint = make_blueprint()
    blueprint = replace(
        blueprint,
        author_approval=replace(
            blueprint.author_approval,
            approval_record_id="DC3PA-ZYF-FORMAL-LOG-BOOTSTRAP-005",
        ),
        blueprint_id="",
    )
    blueprint = replace(
        blueprint,
        author_approval=replace(
            blueprint.author_approval,
            approved_blueprint_content_sha256=(
                blueprint.content_sha256_before_approval()
            ),
        ),
    ).with_id()
    binding = _binding(blueprint, controller, evaluator)
    report = validate_formal_bootstrap_blueprint(
        blueprint=blueprint,
        binding=binding,
        policy={"policy_id": "policy"},
        amendment={
            "amendment_id": "amendment",
            "formal_log_bootstrap_policy_id": "policy",
        },
        controller_source=controller,
        evaluator_source=evaluator,
    )
    assert report.eligible

    controller.write_text("controller-v2\n", encoding="utf-8")
    report = validate_formal_bootstrap_blueprint(
        blueprint=blueprint,
        binding=binding,
        policy={"policy_id": "policy"},
        amendment={
            "amendment_id": "amendment",
            "formal_log_bootstrap_policy_id": "policy",
        },
        controller_source=controller,
        evaluator_source=evaluator,
    )
    assert not report.eligible
    assert "Controller source mismatch" in report.errors
