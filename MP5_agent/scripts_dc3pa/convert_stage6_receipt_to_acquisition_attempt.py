#!/usr/bin/env python3
"""Convert one Stage6 formal receipt into an immutable acquisition attempt.

The conversion is explicit about whether a failure is scientific or technical.
The caller must supply an approved category; no text classifier guesses it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.acquisition_binding import sha256_file
from dc3pa.experiments.formal_acquisition_execution import (
    SCIENTIFIC_FAILURE_CATEGORIES,
    TECHNICAL_FAILURE_CATEGORIES,
    FormalAcquisitionAttempt,
    deterministic_attempt_id,
)


def load_object(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def as_tuple(value):
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    return tuple(str(item) for item in value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage6-receipt", required=True)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--schedule-entry", required=True)
    parser.add_argument("--attempt-index", type=int, required=True)
    parser.add_argument("--retry-of-attempt-id", default="")
    parser.add_argument(
        "--failure-category",
        default="",
        help=(
            "Required for failed runs. Must be one of the frozen scientific "
            "or technical categories."
        ),
    )
    parser.add_argument("--failure-detail", default="")
    parser.add_argument("--acquisition-record", default="")
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--finished-at", required=True)
    parser.add_argument(
        "--secret-scan-passed",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--inline-rgb-detected",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    stage = load_object(args.stage6_receipt)
    campaign = load_object(args.campaign)
    entry = load_object(args.schedule_entry)

    pipeline_pass = bool(stage.get("pipeline_pass", False))
    task_completed = bool(stage.get("task_completed", False))
    category = args.failure_category.strip()

    if pipeline_pass and task_completed:
        status = "completed_success"
        if category:
            raise ValueError("Successful run cannot have a failure category")
    elif pipeline_pass:
        status = "completed_scientific_failure"
        if category not in SCIENTIFIC_FAILURE_CATEGORIES:
            raise ValueError(
                "A completed task failure requires an approved scientific "
                f"category; got {category!r}"
            )
    else:
        status = "technical_failure"
        if category not in TECHNICAL_FAILURE_CATEGORIES:
            raise ValueError(
                "A pipeline failure requires an approved technical category; "
                f"got {category!r}"
            )

    acquisition_path = args.acquisition_record.strip()
    acquisition_sha = ""
    acquisition_writes = int(stage.get("acquisition_write_count", 0) or 0)
    if status == "completed_success":
        if not acquisition_path:
            raise ValueError("Successful run requires --acquisition-record")
        acquisition_sha = sha256_file(acquisition_path)
        if acquisition_writes != 1:
            raise ValueError(
                "Successful Stage6 receipt must record exactly one acquisition write"
            )
    else:
        if acquisition_path:
            raise ValueError("Failed run cannot bind an acquisition record")
        if acquisition_writes:
            raise ValueError("Failed run wrote acquisition data")

    event_ids = as_tuple(
        stage.get("event_ids", stage.get("bootstrap_event_ids", ()))
    )
    returned = as_tuple(stage.get("returned_model_identities", ()))
    injected = int(
        stage.get("total_injected_logs", stage.get("injected_log_count", 0))
        or 0
    )
    natural_logs = int(
        stage.get(
            "total_naturally_collected_logs",
            stage.get("naturally_collected_log_count", 0),
        )
        or 0
    )
    trigger_count = int(
        stage.get(
            "intervention_trigger_count",
            stage.get("fallback_trigger_count", len(event_ids)),
        )
        or 0
    )

    attempt_id = deterministic_attempt_id(
        str(campaign["campaign_id"]),
        int(entry["episode_index"]),
        args.attempt_index,
    )
    attempt = FormalAcquisitionAttempt(
        attempt_id=attempt_id,
        stage6_receipt_id=str(stage.get("receipt_id", "")),
        campaign_id=str(campaign["campaign_id"]),
        schedule_id=str(campaign["schedule_id"]),
        formal_authorization_id=str(campaign["formal_authorization_id"]),
        execution_tooling_binding_id=str(campaign["execution_tooling_binding_id"]),
        episode_index=int(entry["episode_index"]),
        group_id=str(entry["group_id"]),
        task=str(entry["task"]),
        seed=str(entry["seed"]),
        difficulty=str(entry["difficulty"]),
        method_id=str(entry.get("method_id", "single_chain_reactive_acquisition")),
        attempt_index=args.attempt_index,
        retry_of_attempt_id=args.retry_of_attempt_id,
        source_commit=str(campaign["source_commit"]),
        blueprint_id=str(campaign["blueprint_id"]),
        bootstrap_policy_id=str(campaign["bootstrap_policy_id"]),
        bootstrap_amendment_id=str(campaign["bootstrap_amendment_id"]),
        bootstrap_data_binding_id=str(campaign["bootstrap_data_binding_id"]),
        prompt_hash_bundle_id=str(campaign["prompt_hash_bundle_id"]),
        model_profile_id=str(campaign["model_profile_id"]),
        requested_model=str(stage.get("requested_model", "gpt-5.1")),
        returned_model_identities=returned,
        started_at=args.started_at,
        finished_at=args.finished_at,
        status=status,
        failure_category=category,
        failure_detail=args.failure_detail if status != "completed_success" else "",
        pipeline_pass=pipeline_pass,
        task_completed=task_completed,
        planner_calls=int(stage.get("planner_calls", 0) or 0),
        reflection_calls=int(stage.get("reflection_calls", 0) or 0),
        evaluation_chain_calls=int(
            stage.get("evaluation_chain_calls", 0) or 0
        ),
        controller_execution_count=int(
            stage.get("controller_execution_count", 0) or 0
        ),
        bootstrap_event_ids=event_ids,
        intervention_trigger_count=trigger_count,
        injected_log_count=injected,
        naturally_collected_log_count=natural_logs,
        natural_completion=bool(stage.get("natural_completion", False)),
        bootstrap_assisted_completion=bool(
            stage.get("bootstrap_assisted_completion", False)
        ),
        acquisition_record_path=acquisition_path,
        acquisition_record_sha256=acquisition_sha,
        trace_sha256=str(stage.get("trace_sha256", "")),
        formal_memory_write_count=int(
            stage.get("formal_memory_write_count", 0) or 0
        ),
        acquisition_write_count=acquisition_writes,
        secret_scan_passed=args.secret_scan_passed,
        inline_rgb_detected=args.inline_rgb_detected,
        taskset_amendment_id=str(campaign.get("taskset_amendment_id", "")),
    ).with_id()

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(attempt.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(attempt.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
