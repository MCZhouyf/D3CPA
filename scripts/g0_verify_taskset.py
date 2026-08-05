#!/usr/bin/env python3
"""Audit the frozen external 50-task catalog without modifying it."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _terminal_type(spec: dict[str, Any], creative: dict[str, Any]) -> tuple[str, str]:
    operation = str(spec.get("operation", "")).strip().lower()
    if operation in {"mine", "craft", "smelt"}:
        return operation, "formal_spec.operation"
    # Author-approved interpretation: an obtain operation with a physical mining
    # tool and no craft recipe/platform is a mine terminal goal.  This is based on
    # structured goal fields, not a task-name string.
    if (
        operation == "obtain"
        and creative.get("material") is None
        and creative.get("platform") is None
        and creative.get("tool")
        and spec.get("target", {}).get("candidate_item_name") == creative.get("task")
    ):
        return "mine", "author_approved_structured_obtain_with_tool"
    return operation or "unknown", "formal_spec.operation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--spec-dir", type=Path, required=True)
    parser.add_argument("--creative-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = list(csv.DictReader(args.catalog.read_text(encoding="utf-8").splitlines()))
    tasks: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    task_ids: list[str] = []
    missing_fields: list[dict[str, str]] = []
    for ordinal, row in enumerate(rows, start=1):
        task_name = row.get("task", "")
        slug = task_name.replace(" ", "_")
        spec_path = args.spec_dir / f"{slug}.json"
        creative_path = args.creative_dir / f"{slug}.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        creative_rows = json.loads(creative_path.read_text(encoding="utf-8"))
        creative = creative_rows[0] if isinstance(creative_rows, list) and creative_rows else {}
        terminal, basis = _terminal_type(spec, creative)
        task_id = str(spec.get("task_id", ""))
        task_ids.append(task_id)
        for field in ("task_id", "task_name", "difficulty"):
            if not spec.get(field):
                missing_fields.append({"task": task_name, "field": field})
        if terminal not in {"mine", "craft", "smelt"}:
            invalid.append({"task_id": task_id, "task_text": task_name, "terminal_type": terminal})
        tasks.append({
            "task_id": task_id,
            "task_text": task_name,
            "difficulty": row.get("difficulty", ""),
            "terminal_type": terminal,
            "source_location": str(spec_path),
            "inference_basis": basis,
        })
    duplicates = sorted(item for item, count in Counter(task_ids).items() if item and count > 1)
    payload = {
        "source_file": str(args.catalog), "source_sha256": _sha256(args.catalog),
        "task_count": len(tasks), "tasks": tasks,
        "type_counts": dict(sorted(Counter(task["terminal_type"] for task in tasks).items())),
        "invalid_terminal_types": invalid, "duplicate_task_ids": duplicates,
        "missing_fields": missing_fields,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ok = len(tasks) == 50 and not invalid and not duplicates and not missing_fields
    print(json.dumps({"ok": ok, "task_count": len(tasks), "type_counts": payload["type_counts"]}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
