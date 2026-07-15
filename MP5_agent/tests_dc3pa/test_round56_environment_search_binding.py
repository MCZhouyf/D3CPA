from __future__ import annotations

import pytest

from dc3pa.experiments.binding import build_bound_development_protocol
from tests_dc3pa.round56_helpers import make_blueprint


def test_selected_environment_parameters_must_be_preregistered():
    blueprint = make_blueprint()
    with pytest.raises(ValueError):
        build_bound_development_protocol(
            blueprint=blueprint,
            memory_snapshot_sha256="memory",
            confidence_artifact_id="confidence",
            selected_environment_parameters={
                "top_k": 5,
                "text_threshold": 0.5,
                "match_threshold": 0.6,
                "environment_scope": "current_context_only",
            },
            protocol_name="protocol",
            created_from_commit="commit",
        )
