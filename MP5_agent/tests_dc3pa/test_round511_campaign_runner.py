from argparse import Namespace
from pathlib import Path
import re

import pytest

from scripts_dc3pa.run_round511_development_campaign import (
    _stage6_command,
    _validate_assignments,
)


def _assignment(role="dev_train"):
    return {
        "role": role,
        "task": "craft button",
        "seed": "123",
        "group_id": f"{role}:basic:craft button:123",
        "difficulty": "basic",
        "sequence_index": 0,
    }


def test_mounted_assignments_refuse_holdout_and_superseded_task():
    with pytest.raises(ValueError, match="protected holdout"):
        _validate_assignments({"assignments": [_assignment("dev_holdout")]})

    item = _assignment()
    item["task"] = "mine sand"
    with pytest.raises(ValueError, match="superseded mine sand"):
        _validate_assignments({"assignments": [item]})


def test_stage6_command_never_mounts_blueprint_or_credentials(tmp_path: Path):
    task_root = tmp_path / "tasks"
    task_root.mkdir()
    (task_root / "craft_button.json").write_text("[]\n", encoding="utf-8")
    spec_root = tmp_path / "specs"
    spec_root.mkdir()
    (spec_root / "craft_button.json").write_text("{}\n", encoding="utf-8")
    args = Namespace(
        python=Path("/usr/bin/python3"),
        task_root=task_root,
        formal_task_spec_root=spec_root,
        stage6_config=Path("stage6.json"),
        memory_root=Path("memory"),
        mineclip_checkpoint=Path("mineclip.ckpt"),
        mineclip_device="cuda",
        bootstrap_policy=Path("policy.json"),
        bootstrap_amendment=Path("amendment.json"),
        bootstrap_binding_train=Path("train-binding.json"),
        bootstrap_binding_tune=Path("tune-binding.json"),
    )
    command = _stage6_command(
        args=args,
        assignment=_assignment(),
        run_binding=tmp_path / "run.json",
        records=tmp_path / "records.jsonl",
        trace=tmp_path / "trace.jsonl",
        receipt=tmp_path / "receipt.json",
        bootstrap_output=tmp_path / "bootstrap",
    )

    rendered = " ".join(command)
    assert "--real-experiment-blueprint" not in command
    assert "--formal-task-spec" in command
    assert "dev_holdout" not in rendered
    assert "OPENAI_API_KEY" not in rendered
    assert re.search(r"sk-[A-Za-z0-9]{10,}", rendered) is None
