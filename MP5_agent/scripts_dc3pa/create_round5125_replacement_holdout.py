#!/usr/bin/env python3
"""Create an author-authorized replacement holdout without reusing old seeds."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


DIFFICULTIES = ("basic", "easy", "medium", "hard", "complex")
NAMESPACE = "dc3pa-round5125-replacement-holdout-v1"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _positive_seed(*, source_commit: str, task: str, index: int) -> int:
    payload = f"{NAMESPACE}\0{source_commit}\0{task}\0{index}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % (2**31 - 1) + 1


def build_replacement_assignments(
    reference_design: Mapping[str, Any],
    *,
    source_commit: str,
) -> list[dict[str, Any]]:
    development = reference_design.get("development_assignments")
    if not isinstance(development, list):
        raise ValueError("Reference design has no development assignments")
    holdout = [
        item
        for item in development
        if isinstance(item, Mapping) and item.get("role") == "dev_holdout"
    ]
    task_difficulties: dict[str, str] = {}
    task_counts: Counter[str] = Counter()
    for item in holdout:
        task = str(item.get("task", ""))
        difficulty = str(item.get("difficulty", ""))
        if not task or difficulty not in DIFFICULTIES:
            raise ValueError("Reference holdout task identity is invalid")
        if task in task_difficulties and task_difficulties[task] != difficulty:
            raise ValueError("Reference holdout task has multiple difficulties")
        task_difficulties[task] = difficulty
        task_counts[task] += 1
    difficulty_tasks: dict[str, list[str]] = defaultdict(list)
    for task, difficulty in task_difficulties.items():
        difficulty_tasks[difficulty].append(task)
    if any(len(difficulty_tasks[difficulty]) != 1 for difficulty in DIFFICULTIES):
        raise ValueError("Reference holdout must contain one task per difficulty")
    if set(task_counts.values()) != {3} or len(task_counts) != 5:
        raise ValueError("Reference holdout must contain three seeds for five tasks")

    used_seeds = {
        str(item.get("seed"))
        for item in development
        if isinstance(item, Mapping) and item.get("seed") is not None
    }
    assignments = []
    sequence_index = 0
    for difficulty in DIFFICULTIES:
        task = difficulty_tasks[difficulty][0]
        for index in range(1, 4):
            seed = str(
                _positive_seed(
                    source_commit=source_commit,
                    task=task,
                    index=index,
                )
            )
            if seed in used_seeds:
                raise ValueError("Replacement seed overlaps the frozen design")
            used_seeds.add(seed)
            assignments.append(
                {
                    "difficulty": difficulty,
                    "group_id": (
                        f"replacement-dev-holdout:{difficulty}:{task}:{index}"
                    ),
                    "role": "dev_holdout",
                    "seed": seed,
                    "sequence_index": sequence_index,
                    "task": task,
                }
            )
            sequence_index += 1
    return assignments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-design", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--authorization-text", required=True)
    parser.add_argument("--superseded-assignment-sha256", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    if len(args.superseded_assignment_sha256) != 64:
        raise ValueError("Superseded assignment SHA-256 is invalid")
    output = args.output_root.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Replacement holdout output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    reference = json.loads(args.reference_design.read_text(encoding="utf-8"))
    if not isinstance(reference, Mapping):
        raise ValueError("Reference design must be a JSON object")
    assignments = build_replacement_assignments(
        reference,
        source_commit=args.source_commit,
    )
    authorization = {
        "schema_version": 1,
        "authorization_name": "Round5125ReplacementHoldoutAuthorization",
        "authorization_text": args.authorization_text,
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": args.source_commit,
        "reference_design_id": str(reference.get("design_id", "")),
        "replacement_namespace": NAMESPACE,
        "superseded_assignment_sha256": args.superseded_assignment_sha256,
        "old_assignment_reuse_permitted": False,
        "old_seed_reuse_permitted": False,
        "replacement_assignment_count": 15,
    }
    authorization["authorization_id"] = _sha(authorization)
    assignment_payload = {
        "schema_version": 1,
        "assignment_set_name": "dc3pa-round5125-replacement-dev-holdout-v1",
        "authorization_id": authorization["authorization_id"],
        "reference_design_id": authorization["reference_design_id"],
        "source_commit": args.source_commit,
        "derivation_namespace": NAMESPACE,
        "superseded_assignment_sha256": args.superseded_assignment_sha256,
        "assignments": assignments,
    }
    assignment_payload["assignment_set_id"] = _sha(assignment_payload)

    authorization_path = output / "replacement_holdout_authorization.json"
    assignment_path = output / "replacement_holdout_assignments.json"
    authorization_path.write_text(
        json.dumps(authorization, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assignment_path.write_text(
        json.dumps(assignment_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assignment_path.chmod(0o600)
    replacement_sha = sha256_file(assignment_path)
    if replacement_sha == args.superseded_assignment_sha256:
        raise ValueError("Replacement assignment file equals the superseded set")
    print(
        json.dumps(
            {
                "assignment_count": len(assignments),
                "assignment_set_id": assignment_payload["assignment_set_id"],
                "authorization_id": authorization["authorization_id"],
                "replacement_assignment_sha256": replacement_sha,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
