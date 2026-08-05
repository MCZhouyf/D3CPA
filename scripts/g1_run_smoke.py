#!/usr/bin/env python3
"""Run the frozen G1 smoke matrix without changing formal tasks or policy."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, default=Path("runs/g1"))
    parser.add_argument("--selection", type=Path, default=Path("runs/g1/g1_task_selection.json"))
    parser.add_argument("--seeds", type=Path, default=Path("runs/g1/g1_seed_manifest.json"))
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
            command = [sys.executable, "scripts_dc3pa/stage6_run_minecraft.py", "--mode", "reasoning_only",
                       "--task", str(_task_path(task["task_text"])), "--episode-seed", str(seed),
                       "--g1-run-root", str(run_root), "--g1-episode-metadata", str(metadata_path),
                       "--trace", str(run_root / "launcher_traces" / f"{episode_id}.jsonl")]
            result = subprocess.run(command, cwd=root / "MP5_agent", text=True, capture_output=True)
            log_path = run_root / "episode_logs" / f"{episode_id}.log"; log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(result.stdout + "\n--- STDERR ---\n" + result.stderr, encoding="utf-8")
            matrix.append({"episode_id": episode_id, "task_id": task["task_id"], "seed": seed, "exit_code": result.returncode,
                           "task_failure": bool(result.returncode == 1), "system_error": bool(result.returncode not in (0, 1)), "log": str(log_path)})
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
