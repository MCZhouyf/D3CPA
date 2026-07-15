#!/usr/bin/env python3
"""Validate all approved tasks against the real runtime registry/Evaluator.

Codex must integrate the repository-specific registry export and Evaluator
loader before using this command for formal readiness. The CLI deliberately
requires explicit adapter functions and contains no fuzzy fallback.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.task_assets import validate_task_assets


def load_callable(spec: str):
    if ":" not in spec:
        raise ValueError("Callable spec must use module:function")
    module_name, function_name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    value = getattr(module, function_name)
    if not callable(value):
        raise TypeError(f"{spec} is not callable")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-root", required=True)
    parser.add_argument(
        "--registry-exporter",
        required=True,
        help="module:function returning [{'name': ..., 'id': ...}, ...]",
    )
    parser.add_argument(
        "--evaluator-loader",
        required=True,
        help="module:function accepting one formal task-spec Path",
    )
    parser.add_argument(
        "--environment-smoke",
        required=True,
        help="module:function constructing the unchanged Evaluator environment",
    )
    parser.add_argument("--output-runtime-tasks", required=True)
    parser.add_argument("--output-report", required=True)
    parser.add_argument("--output-resolution", required=True)
    args = parser.parse_args()

    root = Path(args.asset_root)
    registry_exporter = load_callable(args.registry_exporter)
    evaluator_loader = load_callable(args.evaluator_loader)
    environment_smoke = load_callable(args.environment_smoke)
    registry_entries = registry_exporter()

    report, resolutions = validate_task_assets(
        catalog_path=root / "final_task_catalog.csv",
        mapping_manifest_path=root / "task_mapping_manifest.json",
        asset_root=root,
        runtime_registry_entries=registry_entries,
        evaluator_loader=evaluator_loader,
        environment_smoke=environment_smoke,
    )

    report_path = Path(args.output_report)
    resolution_path = Path(args.output_resolution)
    for path in (report_path, resolution_path):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    resolution_path.write_text(
        json.dumps(
            {"resolutions": [item.to_dict() for item in resolutions]},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    if report.eligible:
        runtime_root = Path(args.output_runtime_tasks)
        if runtime_root.exists() and any(runtime_root.iterdir()):
            raise FileExistsError(f"Refusing to overwrite {runtime_root}")
        runtime_root.mkdir(parents=True, exist_ok=True)
        mapping = json.loads((root / "task_mapping_manifest.json").read_text())
        for item in mapping["tasks"]:
            formal_path = root / item["formal_spec"]
            payload = evaluator_loader(formal_path)
            output = runtime_root / f"{formal_path.stem}.json"
            output.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    return 0 if report.eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
