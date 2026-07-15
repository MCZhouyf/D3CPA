from __future__ import annotations

import inspect

from scripts_dc3pa import preflight_real_development
from dc3pa.reliability.reproducibility_manifest import DevelopmentRunManifest


def _manifest():
    return DevelopmentRunManifest(
        run_name="dev-train",
        role="dev_train",
        source_commit="commit",
        development_protocol_id="protocol",
        activation_policy_id="policy",
        final_test_exclusion_id="exclusion",
        memory_snapshot_sha256="memory",
        confidence_artifact_id="confidence",
        environment_parameter_sha256="environment",
        model_ids={"planner": "model"},
        prompt_hashes={"planner": "prompt"},
        config_hashes={"runtime": "config"},
        budgets={"steps": 40, "calls": 10},
        controller_profile="paper-matched",
    ).with_id()


def test_run_manifest_is_deterministic():
    assert _manifest().run_manifest_id == _manifest().run_manifest_id


def test_preflight_cli_has_no_holdout_argument():
    source = inspect.getsource(preflight_real_development)
    assert "--holdout" not in source
