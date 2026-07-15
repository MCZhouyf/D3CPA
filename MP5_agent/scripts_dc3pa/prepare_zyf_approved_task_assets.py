#!/usr/bin/env python3
"""Copy and validate the ZYF-approved 50-task assets outside Git."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.task_assets import (
    validate_task_assets,
    verify_author_input_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-input-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Validate schemas only. This can never produce paper eligibility.",
    )
    args = parser.parse_args()

    source = Path(args.approved_input_root).resolve()
    output = Path(args.output_root).resolve()
    verify_author_input_manifest(source)
    if output.exists() and any(output.iterdir()):
        raise SystemExit("Output root must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)

    for name in (
        "final_task_catalog.csv",
        "task_mapping_manifest.json",
        "author_approval_confirmed.json",
    ):
        shutil.copy2(source / name, output / name)
    shutil.copytree(
        source / "creative_task_jsons",
        output / "creative_task_jsons",
        dirs_exist_ok=False,
    )
    shutil.copytree(
        source / "formal_task_specs",
        output / "formal_task_specs",
        dirs_exist_ok=False,
    )

    report, resolutions = validate_task_assets(
        catalog_path=output / "final_task_catalog.csv",
        mapping_manifest_path=output / "task_mapping_manifest.json",
        asset_root=output,
        runtime_registry_entries=None,
        evaluator_loader=None,
    )
    (output / "schema_validation_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    # Schema-only output is intentionally not formal readiness.
    return 0 if args.schema_only else 2


if __name__ == "__main__":
    raise SystemExit(main())
