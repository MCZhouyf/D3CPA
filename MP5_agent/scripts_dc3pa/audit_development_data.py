#!/usr/bin/env python3
"""Audit development data before any artifact is fit or activated."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.reliability.data_audit import DataSufficiencyPolicy, audit_role
from dc3pa.reliability.fusion_dataset import load_jsonl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    examples = load_jsonl(Path(args.dataset))
    payload = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    payload["required_metadata_strata"] = {
        key: tuple(value)
        for key, value in payload.get("required_metadata_strata", {}).items()
    }
    policy = DataSufficiencyPolicy(**payload)
    result = audit_role(examples, role=args.role, policy=policy)
    Path(args.output).write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
