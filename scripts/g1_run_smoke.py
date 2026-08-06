#!/usr/bin/env python3
"""Run the frozen G1 smoke matrix without changing formal tasks or policy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _task_path(task_text: str) -> Path:
    stem = task_text.replace(" ", "_")
    path = Path("/external/dc3pa/task_assets_schema/creative_task_jsons") / f"{stem}.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _classify_exit(*, returncode: int, trace_path: Path, ledger_path: Path) -> tuple[bool, bool, str]:
    """Keep environmental/API incidents separate from genuine task failures."""
    if returncode == 0:
        return False, False, "success"
    system_markers = {"unhandled_planning_failure", "environment_reset_unavailable"}
    for path in (trace_path, ledger_path):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            payload = event.get("payload") or {}
            if event.get("event_type") == "llm_relay_attempt" and payload.get("status") == "failure":
                return False, True, "relay_api_failure"
            if event.get("event_type") == "planning_blocked" and payload.get("reason") in system_markers:
                return False, True, str(payload["reason"])
    if returncode not in (0, 1):
        return False, True, f"launcher_exit_{returncode}"
    return True, False, "task_failure"


def _completed_raw_event(run_root: Path, episode_id: str) -> dict | None:
    """Return the final result only for an atomically finalized raw event file."""
    for path in sorted((run_root / "raw_events").glob(f"{episode_id}.*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("event_type") == "episode_result":
                return dict(event.get("payload") or {})
    return None


def _write_status(run_root: Path, record: dict) -> None:
    status_dir = run_root / "episode_status"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / f"{record['episode_id']}.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _run_episode_in_cleanup_group(command: list[str], *, cwd: Path) -> tuple[int, str, str]:
    """Run one MineDojo episode and reclaim its client process group on exit.

    MineDojo may leave its Gradle/Minecraft grandchildren alive after the Python
    launcher has returned.  A dedicated session makes those descendants a
    precise cleanup target without touching the smoke runner or another episode.
    """
    process = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    stdout, stderr = process.communicate()
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    else:
        # Give the normal Minecraft shutdown path a short chance before the
        # guaranteed final cleanup.  The launcher itself has already exited.
        time.sleep(3)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return process.returncode, stdout, stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, default=Path("runs/g1"))
    parser.add_argument("--selection", type=Path, default=Path("runs/g1/g1_task_selection.json"))
    parser.add_argument("--seeds", type=Path, default=Path("runs/g1/g1_seed_manifest.json"))
    parser.add_argument("--cooldown-seconds", type=float, default=30.0)
    args = parser.parse_args()
    root, run_root = args.repo.resolve(), args.run_root.resolve()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))["selected"]
    seeds = json.loads(args.seeds.read_text(encoding="utf-8"))["core_seeds"]
    if len(selection) != 6 or len(seeds) != 2:
        raise ValueError("G1 core smoke must be exactly 6 tasks x 2 seeds")
    metadata_dir = run_root / "episode_metadata"; metadata_dir.mkdir(parents=True, exist_ok=True)
    matrix: list[dict] = []
    for task in selection:
        for seed in seeds:
            episode_id = f"{task['task_id']}--seed-{seed}"
            metadata = {**task, "run_id": "g1-smoke-v1", "episode_id": episode_id,
                        "policy_tag": "g1_observer_smoke", "task_text_hash": hashlib.sha256(task["task_text"].encode()).hexdigest()}
            metadata_path = metadata_dir / f"{episode_id}.json"
            metadata_path.write_text(json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8")
            trace_path = run_root / "launcher_traces" / f"{episode_id}.jsonl"
            ledger_path = run_root / "llm_raw" / f"{episode_id}.jsonl"
            raw_result = _completed_raw_event(run_root, episode_id)
            if raw_result is not None:
                returncode = 0 if raw_result.get("success") else 1
                task_failure, system_error, outcome_kind = _classify_exit(
                    returncode=returncode, trace_path=trace_path, ledger_path=ledger_path
                )
                matrix.append({"episode_id": episode_id, "task_id": task["task_id"], "seed": seed, "exit_code": returncode,
                               "task_failure": task_failure, "system_error": system_error, "outcome_kind": outcome_kind,
                               "log": "resumed_finalized_raw"})
                continue
            command = [sys.executable, "scripts_dc3pa/stage6_run_minecraft.py", "--mode", "reasoning_only",
                       "--task", str(_task_path(task["task_text"])), "--episode-seed", str(seed),
                       "--g1-run-root", str(run_root), "--g1-episode-metadata", str(metadata_path),
                       "--memory-root", str(run_root / "runtime_memory" / episode_id),
                       "--trace", str(trace_path)]
            returncode, stdout, stderr = _run_episode_in_cleanup_group(
                command, cwd=root / "MP5_agent"
            )
            log_path = run_root / "episode_logs" / f"{episode_id}.log"; log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(stdout + "\n--- STDERR ---\n" + stderr, encoding="utf-8")
            task_failure, system_error, outcome_kind = _classify_exit(
                returncode=returncode,
                trace_path=trace_path, ledger_path=ledger_path,
            )
            record = {"episode_id": episode_id, "task_id": task["task_id"], "seed": seed, "exit_code": returncode,
                      "task_failure": task_failure, "system_error": system_error, "outcome_kind": outcome_kind, "log": str(log_path)}
            matrix.append(record)
            _write_status(run_root, record)
            # Uniform pacing only; it is not selected by task/item/result and
            # avoids bursty relay traffic between independent episodes.
            if args.cooldown_seconds > 0:
                time.sleep(args.cooldown_seconds)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "run_matrix.json").write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    parts = sorted((run_root / "episodes").glob("*.steps.parquet"))
    if parts:
        table = pa.concat_tables([pq.read_table(path) for path in parts])
        pq.write_table(table, run_root / "steps.parquet")
    pq.write_table(pa.Table.from_pylist(matrix), run_root / "episodes.parquet")
    ledger_rows = []
    for path in sorted((run_root / "llm_raw").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("event_type") == "llm_relay_attempt":
                ledger_rows.append(dict(event.get("payload") or {}))
    pq.write_table(pa.Table.from_pylist(ledger_rows), run_root / "llm_calls.parquet")
    return 0 if all(row["exit_code"] in (0, 1) for row in matrix) else 2


if __name__ == "__main__":
    raise SystemExit(main())
