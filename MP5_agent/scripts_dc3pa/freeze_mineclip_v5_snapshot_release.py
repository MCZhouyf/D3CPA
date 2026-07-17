#!/usr/bin/env python3
"""Freeze the sealed, read-only MineCLIP V5 engineering snapshot release."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.mineclip_memory_v5 import (  # noqa: E402
    MineCLIPV5RebuildContract,
    freeze_mineclip_snapshot_release,
)


def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "release-name",
        "contract",
        "snapshot-manifest",
        "build-stats",
        "readonly-smoke",
        "output",
    ):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    item = freeze_mineclip_snapshot_release(
        release_name=args.release_name,
        contract=MineCLIPV5RebuildContract(**load(args.contract)),
        snapshot_manifest_path=args.snapshot_manifest,
        build_stats_path=args.build_stats,
        read_only_smoke=load(args.readonly_smoke),
    )
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(item.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(item.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
