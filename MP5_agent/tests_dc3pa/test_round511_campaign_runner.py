from argparse import Namespace
from pathlib import Path
import re
import signal
import subprocess

import pytest

from scripts_dc3pa.run_round511_development_campaign import (
    DEVELOPMENT_MAX_EXPLORE_STEPS,
    _load_existing_attempt_summary,
    _run_stage6_process,
    _stage6_command,
    _stage6_environment,
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
        provider_model_alias_policy=Path("alias-policy.json"),
        provider_model_alias_approval=Path("alias-approval.json"),
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
    assert "--provider-model-alias-policy" in command
    assert "--provider-model-alias-approval" in command
    assert "dev_holdout" not in rendered
    assert "OPENAI_API_KEY" not in rendered
    assert re.search(r"sk-[A-Za-z0-9]{10,}", rendered) is None


def test_stage6_environment_binds_frozen_exploration_budget():
    env = _stage6_environment(
        seed="1439023989",
        base={"DC3PA_MAX_EXPLORE_STEPS": "10000", "UNRELATED": "kept"},
    )

    assert DEVELOPMENT_MAX_EXPLORE_STEPS == 60
    assert env["DC3PA_MAX_EXPLORE_STEPS"] == "60"
    assert env["PYTHONHASHSEED"] == "1439023989"
    assert env["DC3PA_WORLD_SEED"] == "1439023989"
    assert env["DC3PA_SIM_SEED"] == "1439023989"
    assert env["MP5_DISABLE_MEMORY"] == "1"
    assert env["DC3PA_LEGACY_TASK_HACKS"] == "0"
    assert env["UNRELATED"] == "kept"


def test_stage6_timeout_interrupts_the_complete_process_group(
    monkeypatch, tmp_path: Path
):
    calls = []

    class FakeProcess:
        pid = 4321

        def __init__(self):
            self.wait_count = 0

        def wait(self, timeout=None):
            self.wait_count += 1
            if self.wait_count == 1:
                raise subprocess.TimeoutExpired(["stage6"], timeout)
            return -signal.SIGINT

    process = FakeProcess()

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return process

    signals = []
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("os.killpg", lambda pid, sig: signals.append((pid, sig)))

    result = _run_stage6_process(
        ["stage6"],
        cwd=tmp_path,
        env={"TOKEN": "redacted"},
        output=None,
        timeout_seconds=1,
    )

    assert result == 124
    assert calls[0][1]["start_new_session"] is True
    assert signals == [(4321, signal.SIGINT)]


def test_existing_failed_attempt_summary_is_resume_safe(tmp_path: Path):
    summary = tmp_path / "attempt_summary.json"
    summary.write_text(
        '{"accepted": false, "attempt": 2, "run_id": "run-2"}\n',
        encoding="utf-8",
    )

    payload = _load_existing_attempt_summary(summary, run_id="run-2", attempt=2)

    assert payload is not None
    assert payload["accepted"] is False
    with pytest.raises(ValueError, match="run ID mismatch"):
        _load_existing_attempt_summary(summary, run_id="different", attempt=2)
    with pytest.raises(ValueError, match="index mismatch"):
        _load_existing_attempt_summary(summary, run_id="run-2", attempt=3)
