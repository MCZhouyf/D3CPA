#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.source_commit_extension import audit_source_extension


def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT.parent))
    parser.add_argument("--parent-commit", required=True)
    parser.add_argument("--final-commit", required=True)
    for name in ("approval", "authorization", "schedule", "policy", "amendment", "output"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    report = audit_source_extension(
        repo_root=args.repo_root,
        parent_commit=args.parent_commit,
        final_commit=args.final_commit,
        approval=load(args.approval),
        authorization=load(args.authorization),
        schedule=load(args.schedule),
        policy=load(args.policy),
        amendment=load(args.amendment),
    )
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
