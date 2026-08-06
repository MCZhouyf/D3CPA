from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

from dc3pa.observability.g1_labels import label_execution
from dc3pa.observability.g1_steps import step_rows_from_telemetry
from dc3pa.observability.g1_writer import G1EpisodeWriter, write_parquet_atomically
from dc3pa.observability.g1_state_audit import StateWriteObserver
from dc3pa.observability.g1_ledger import LedgerChatModel


CONTEXT = {
    "run_id": "run-1", "episode_id": "episode-1", "task_id": "basic-01-mine_log",
    "task_text_hash": "task-hash", "terminal_type": "mine", "difficulty": "basic",
    "episode_seed": 11001, "policy_tag": "g1_observer_smoke", "commit_hash": "commit",
    "config_hash": "config", "model_config_hash": "model",
}


def _events(status: str = "success", result=None):
    return [
        {"event_type": "action_started", "plan_id": "plan", "step_id": "step", "step_index": 0,
         "action_index": 0, "payload": {"action": {"name": "mine", "args": {"obj": "log", "tool": "wooden pickaxe"}}}},
        {"event_type": "action_finished", "plan_id": "plan", "step_id": "step", "step_index": 0,
         "action_index": 0, "status": status, "payload": {"result": result or {}}},
    ]


def test_g1_step_schema_is_one_row_per_submitted_action_and_logger_is_pure():
    telemetry = _events()
    before = json.loads(json.dumps(telemetry))
    rows = step_rows_from_telemetry(telemetry=telemetry, context=CONTEXT)
    assert telemetry == before
    assert len(rows) == 1
    row = rows[0]
    assert row["step_outcome"] == "success"
    assert row["y_exec"] == 1 and row["label_eligible"] is True
    assert row["p_K_status"] == row["p_L_status"] == row["p_E_status"] == "source_not_connected"
    assert row["a_K"] is None and row["a_E"] is None
    assert row["eval_called"] is False and row["trigger"] is False


def test_g1_labels_cover_outcomes_and_failure_semantics():
    assert label_execution(attempted=True, status="success").y_exec == 1
    assert label_execution(attempted=True, status="skipped_satisfied").label_eligible is False
    assert label_execution(attempted=False, status="").step_outcome == "aborted"
    assert label_execution(attempted=True, status="system_error", result={}).failure_mode == "system_api_error"
    assert label_execution(attempted=True, status="failure", result={"missing_requirements": ["stick"]}).failure_mode == "knowledge_gap"
    assert label_execution(attempted=True, status="failure", result={"reason_code": "declared_target_unreachable"}).failure_mode == "environment_mismatch"
    assert label_execution(attempted=True, status="failure", result={"reason_code": "environment_step_budget_exhausted"}).failure_mode == "budget_exhaustion"


def test_g1_writer_keeps_partial_raw_events_out_of_completed_parquet(tmp_path: Path):
    writer = G1EpisodeWriter(tmp_path, "episode-1")
    writer.write("action_started", {"action": "mine"})
    assert list((tmp_path / "raw_events").glob("*.partial.jsonl"))
    final_raw = writer.finalize()
    assert final_raw.is_file()
    assert ".partial." not in final_raw.name
    assert not list((tmp_path / "raw_events").glob("*.partial.jsonl"))
    rows = step_rows_from_telemetry(telemetry=_events(), context=CONTEXT)
    path = write_parquet_atomically(rows, tmp_path / "steps.parquet")
    assert pq.read_table(path).num_rows == 1
    assert not list(path.parent.glob("steps.parquet.*.partial"))


def test_g1_state_observer_distinguishes_external_reset_without_controller_import():
    calls = []

    class Env:
        def set_inventory(self, items):
            calls.append(list(items))

    env = Env()
    observer = StateWriteObserver()
    observer.attach(env)
    env.set_inventory([])
    assert calls == [[]]
    assert observer.events[0].source == "environment_reset"


def test_g1_ledger_records_logical_call_without_raw_prompt_or_secret(tmp_path: Path):
    class Result:
        usage_metadata = {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}

    class Model:
        def invoke(self, prompt):
            assert prompt == "secret-free prompt"
            return Result()

    path = tmp_path / "ledger.jsonl"
    model = LedgerChatModel(Model(), path, context={"run_id": "r", "task_id": "t", "step_idx": 0, "caller_type": "planner", "model": "glm"})
    model.invoke("secret-free prompt")
    text = path.read_text(encoding="utf-8")
    assert "secret-free prompt" not in text
    records = [json.loads(line) for line in text.splitlines()]
    assert records[-1]["payload"]["token_count_source"] == "api_usage"
    assert records[-1]["payload"]["total_tokens"] == 5


def test_g1_ledger_marks_usage_unavailable_when_relay_omits_usage_metadata(tmp_path: Path):
    class Result:
        usage_metadata = {"prompt_tokens": None, "completion_tokens": None}
        content = "brief response"

    class Model:
        def invoke(self, prompt):
            return Result()

    path = tmp_path / "ledger.jsonl"
    LedgerChatModel(Model(), path, context={"caller_type": "planner"}).invoke("private prompt")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    payload = records[-1]["payload"]
    assert payload["token_count_source"] == "unavailable"
    assert payload["prompt_tokens"] is None
    assert payload["completion_tokens"] is None
    assert payload["total_tokens"] is None


def test_g1_ledger_retries_a_rate_limit_and_keeps_attempt_indices(tmp_path: Path):
    class RateLimitError(Exception):
        pass

    class Result:
        usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}

    class Model:
        calls = 0

        def invoke(self, _prompt):
            self.calls += 1
            if self.calls == 1:
                raise RateLimitError("429")
            return Result()

    path = tmp_path / "ledger.jsonl"
    LedgerChatModel(Model(), path, context={}, min_relay_interval_seconds=0, rate_limit_backoff_seconds=0).invoke("x")
    attempts = [json.loads(line)["payload"] for line in path.read_text(encoding="utf-8").splitlines()
                if json.loads(line)["event_type"] == "llm_relay_attempt"]
    assert [(row["retry_idx"], row["status"]) for row in attempts] == [(0, "failure"), (1, "success")]
