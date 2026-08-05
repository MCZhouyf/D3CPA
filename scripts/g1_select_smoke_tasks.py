#!/usr/bin/env python3
"""Deterministically select the G1 six-task smoke subset from the frozen catalog."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def _rank(task_id: str) -> str:
    return hashlib.sha256(f"G1_SMOKE_V1|{task_id}".encode("utf-8")).hexdigest()


def select(tasks: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for task in tasks:
        grouped[str(task["terminal_type"])].append(task)
    selected: list[dict] = []
    for terminal_type, count in (("mine", 2), ("craft", 2), ("smelt", 2)):
        candidates = sorted(grouped[terminal_type], key=lambda row: _rank(str(row["task_id"])))
        # Pick distinct difficulties first; hash order is the only tie breaker.
        used: set[str] = set()
        for candidate in candidates:
            if candidate["difficulty"] not in used:
                selected.append(candidate); used.add(candidate["difficulty"])
                if sum(item["terminal_type"] == terminal_type for item in selected) == count:
                    break
        for candidate in candidates:
            if sum(item["terminal_type"] == terminal_type for item in selected) == count:
                break
            if candidate not in selected:
                selected.append(candidate)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--taskset-audit", type=Path, default=Path("runs/g0/taskset_audit.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.taskset_audit.read_text(encoding="utf-8"))
    tasks = list(audit["tasks"])
    selected = select(tasks)
    payload = {
        "schema_version": "g1.v1", "catalog_sha256": audit["source_sha256"],
        "rule": "per terminal type, maximize difficulty coverage; SHA256(G1_SMOKE_V1|task_id) breaks ties",
        "candidates": [{**task, "stable_rank": _rank(task["task_id"])} for task in tasks],
        "selected": [{**task, "stable_rank": _rank(task["task_id"])} for task in selected],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"selected_task_ids": [task["task_id"] for task in selected]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
