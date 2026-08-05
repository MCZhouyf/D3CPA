"""Non-invasive conversion from existing execution telemetry to G1 step rows."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from .g1_labels import label_execution
from .g1_writer import SCHEMA_VERSION, canonical_json, sha256_json


def _action_name(event: Mapping[str, Any]) -> str:
    payload = event.get("payload") or {}
    action = payload.get("action") or {}
    return str(action.get("name") or action.get("type") or "unknown")


def step_rows_from_telemetry(*, telemetry: Iterable[Mapping[str, Any]], context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Create exactly one row per ``action_started`` Controller event.

    Action finish events supply outcomes.  No Controller object, plan object, or
    environment is modified by this transformation.
    """
    telemetry = list(telemetry)
    starts: list[Mapping[str, Any]] = []
    finishes: dict[tuple[str, int, int, int], Mapping[str, Any]] = {}
    occurrence: defaultdict[tuple[str, int, int], int] = defaultdict(int)
    for event in telemetry:
        key = (str(event.get("step_id", "")), int(event.get("step_index", -1)), int(event.get("action_index", -1)))
        if event.get("event_type") == "action_started":
            occurrence[key] += 1
            starts.append(dict(event, _g1_occurrence=occurrence[key]))
        elif event.get("event_type") == "action_finished":
            index = occurrence[key] or 1
            finishes[(key[0], key[1], key[2], index)] = event
    trace_hash = sha256_json(list(telemetry))
    rows: list[dict[str, Any]] = []
    for step_idx, started in enumerate(starts):
        payload = dict(started.get("payload") or {})
        action = dict(payload.get("action") or {})
        key = (str(started.get("step_id", "")), int(started.get("step_index", -1)), int(started.get("action_index", -1)), int(started["_g1_occurrence"]))
        finished = finishes.get(key)
        result = dict((finished or {}).get("payload", {}).get("result") or {})
        status = str((finished or {}).get("status") or "aborted")
        label = label_execution(attempted=finished is not None, status=status, result=result)
        action_id = f"{key[0]}:{key[2]}:{key[3]}"
        row = {
            "schema_version": SCHEMA_VERSION, "run_id": context["run_id"], "episode_id": context["episode_id"],
            "task_id": context["task_id"], "task_text_hash": context["task_text_hash"], "terminal_type": context["terminal_type"],
            "difficulty": context["difficulty"], "episode_seed": context["episode_seed"], "step_idx": step_idx,
            "policy_tag": context["policy_tag"], "commit_hash": context["commit_hash"], "config_hash": context["config_hash"],
            "model_config_hash": context["model_config_hash"], "memory_hash": "disabled_g0", "calibrator_hash": "not_fitted_g1",
            "plan_id": str(started.get("plan_id", "")), "action_id": action_id, "action": _action_name(started),
            "action_args": canonical_json(action.get("args", {})), "action_normalized": canonical_json(action),
            "subgoal_text": "", "step_outcome": label.step_outcome, "controller_trace_hash": trace_hash,
            "p_K": None, "p_L": None, "p_E": None, "a_K": None, "a_E": None,
            "p_K_status": "source_not_connected", "p_L_status": "source_not_connected", "p_E_status": "source_not_connected",
            "evidence_source_ids": canonical_json({}), "q_calibrated": None, "q_bar": None, "W": None, "tau": None,
            "M_current": None, "trigger": False, "trigger_reason": "disabled_g1", "eval_called": False,
            "eval_changed_action": False, "repair_success": None, "label_eligible": label.label_eligible, "y_exec": label.y_exec,
            "failure_mode": label.failure_mode, "y_plan_fail": label.y_plan_fail, "label_source": label.label_source,
            "label_evidence_refs": canonical_json({"controller_result": result}), "planner_calls": 0, "evaluator_calls": 0,
            "reflexion_calls": 0, "relay_request_attempts": 0, "tokens_in_planner": None, "tokens_out_planner": None,
            "tokens_in_evaluator": None, "tokens_out_evaluator": None, "tokens_in_other": None, "tokens_out_other": None,
            "token_count_source": "unavailable", "wall_ms": None, "llm_wall_ms": None, "environment_wall_ms": None,
            "log_callback_fired": False, "log_callback_event_id": None, "state_change_source": "none",
        }
        rows.append(row)
    return rows
