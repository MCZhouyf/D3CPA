#!/usr/bin/env python3
"""Freeze the committed Controller revision manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.controller_revision import (
    ControllerRevisionManifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = json.loads(
        Path(args.manifest_input).read_text(encoding="utf-8")
    )
    for name in (
        "natural_fix_ids",
        "natural_fix_test_ids",
        "fallback_allowed_scopes",
        "fallback_forbidden_scopes",
    ):
        payload[name] = tuple(payload.get(name, ()))
    item = ControllerRevisionManifest(**payload).with_id()

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(item.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(item.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
