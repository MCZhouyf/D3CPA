from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_author_spec_draft_is_not_executable():
    path = Path(__file__).resolve().parents[1] / "dc3pa/configs/round56_author_experiment_spec.DRAFT.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["draft_only"] is True
    assert "REPLACE" in payload["blueprint_name"]
    assert payload["author_approval"]["approved_blueprint_content_sha256"] == ""


def test_builder_refuses_draft_only_spec_before_loading_other_inputs():
    root = Path(__file__).resolve().parents[1]
    draft = root / "dc3pa/configs/round56_author_experiment_spec.DRAFT.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts_dc3pa/build_real_experiment_blueprint.py",
            "--author-spec",
            str(draft),
            "--final-test-exclusion",
            "missing-final.json",
            "--activation-policy",
            "missing-policy.json",
            "--data-sufficiency-policy",
            "missing-sufficiency.json",
            "--output-blueprint",
            "unused.json",
            "--print-content-sha-for-approval",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "draft_only" in result.stderr
