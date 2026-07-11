#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MP5_ROOT = SCRIPT_DIR.parent
if str(MP5_ROOT) not in sys.path:
    sys.path.insert(0, str(MP5_ROOT))

from dc3pa.contracts import Plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and round-trip an MP5 workflow")
    parser.add_argument("workflow_json")
    parser.add_argument("--task", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = json.loads(Path(args.workflow_json).read_text(encoding="utf-8"))
    plan = Plan.from_dict(payload, task=args.task)
    output_payload = {
        "typed_plan": plan.to_dict(),
        "legacy_roundtrip": plan.to_legacy_workflow(),
    }
    rendered = json.dumps(output_payload, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
